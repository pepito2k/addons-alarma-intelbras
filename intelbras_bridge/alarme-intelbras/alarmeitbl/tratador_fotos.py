#!/usr/bin/env python3

import os
from .myeventloop import Timeout, Log
from .obtiene_fotos import *

# Tratador de fotos obtidas via eventos 0xb5. Desacoplado do tratador 
# principal pois usa conexiones separadas, e as fotos ficam armazenadas
# por tempo indeterminado na central, no sendo atreladas à conexión com
# o Receptor IP.
#
# En una implementação futura os índices das fotos poderiam ser até
# armazenados num banco de dados local, para que no se percam quando
# o programa é reiniciado.

class TratadorDeFotos:
    def __init__(self, gancho, folder, caddr, cport, senha, tam_senha):
        self.gancho = gancho
        self.folder = folder
        self.caddr = caddr
        self.cport = cport
        self.senha = senha
        self.tam_senha = tam_senha
        self.cola = [] # [dirección IP, indice, nr. foto, intentos restantes]
        self.task = None

    # Recebe nova foto de algum Tratador para a cola
    def enfileirar(self, ip_addr_cli, indice, nrfoto):
        if self.tam_senha <= 0:
            return
        self.cola.append([ip_addr_cli, indice, nrfoto, 10])
        if not self.task:
            # Fotos de sensor 8000 demoram para gravar (NAK 0x28 = foto no gravada)
            self.task = Timeout.new("trata_foto", 20, self.obtiene_foto)

    # Reduz tempo de timeout (caso de uso: comando CLI)
    def imediato(self):
        self.task.reset(0.1)

    def obtiene_foto(self, task):
        if not self.cola:
            self.task = None
            return

        ip_addr_cli, indice, nrfoto, intentos = self.cola[0]

        # Usar dirección da central detectada ou manualmente especificado?
        ip_addr = ip_addr_cli
        if self.caddr != "auto":
            ip_addr = self.caddr

        Log.info("tratador de fotos: obtendo %s:%d:%d intentos %d" % \
                      (ip_addr, indice, nrfoto, intentos))

        ObtemFotosDeEvento(ip_addr, self.cport, indice, nrfoto, \
                            self.senha, self.tam_senha, self, self.folder)

    def msg_para_gancho_archivo(self, archivo):
        p = os.popen(self.gancho + " " + archivo, 'w')
        p.close()

    # observer chamado quando ObtemFotosDeEvento finaliza
    def resultado_foto(self, indice, nrfoto, status, archivo):
        if status == 0:
            Log.info("Fotos indice %d:%d: sucesso" % (indice, nrfoto))
            Log.info("Arquivo de foto %s" % archivo)
            if self.gancho:
                self.msg_para_gancho_archivo(archivo)
            del self.cola[0]
        elif status == 2:
            Log.info("Fotos indice %d:%d: erro fatal" % (indice, nrfoto))
            del self.cola[0]
        else:
            self.cola[0][3] -= 1
            if self.cola[0][3] <= 0:
                Log.info("Fotos indice %d:%d: intentos esgotadas" % (indice, nrfoto))
                del self.cola[0]
            else:
                Log.info("Fotos indice %d:%d: erro temporario" % (indice, nrfoto))

        self.task.restart()
