#!/usr/bin/env python3

import time
from .utils_proto import *
from .comandos import ComandarCentral

# Agente que obtiene fotos de um evento de sensor com câmera

class ObtemFotosDeEvento(ComandarCentral):
    def __init__(self, ip_addr, cport, indice, nrfoto, senha, tam_senha, observer, folder):
        extra = [indice, nrfoto]
        super().__init__(observer, ip_addr, cport, senha, tam_senha, extra)
        self.log_info("Iniciando obtención de foto %d:%d" % (indice, nrfoto))
        self.indice = indice
        self.nrfoto = nrfoto
        self.archivo = ""
        self.folder = folder

        # Se destruído com esse status, reporta erro fatal
        self.status = 2

        self.tratador = None

    # override completo
    def destroyed_callback(self):
        # Informa observador sobre status final da tarefa
        self.observer.resultado_foto(self.indice, self.nrfoto, \
                                     self.status, self.archivo)

    def envia_comando_in(self):
        self.fragmento_corrente = 1 # Fragmento 1 sempre existe
        self.jpeg_corrente = []
        self.obtiene_fragmento_foto()

    def obtiene_fragmento_foto(self):
        self.log_debug("Conexión foto: obteniendo fragmento %d" % self.fragmento_corrente)
        payload = self.be16(self.indice) + [ self.nrfoto, self.fragmento_corrente ]
        self.envia_comando(0x0bb0, payload, self.resposta_comando_in)

    def resposta_comando_in(self, payload):
        if len(payload) < 6:
            self.log_info("Conexión foto: resp frag muy corta")
            self.destroy()
            return

        self.log_debug("Conexión foto: respuesta fragmento %d" % self.fragmento_corrente)

        indice = self.parse_be16(payload[0:2])
        foto = payload[2]
        nr_fotos = payload[3]
        fragmento = payload[4]
        nr_fragmentos = payload[5]
        fragmento_jpeg = payload[6:]

        if indice != self.indice:
            self.log_info("Conexión foto: índice inválido")
            self.destroy()
            return

        if foto != self.nrfoto:
            self.log_info("Conexión foto: nr foto inválida")
            self.destroy()
            return

        if fragmento != self.fragmento_corrente:
            self.log_info("Conexión foto: frag corriente inválido")
            self.destroy()
            return

        self.jpeg_corrente += fragmento_jpeg

        if fragmento < nr_fragmentos:
            self.fragmento_corrente += 1
            self.obtiene_fragmento_foto()
            return

        self.log_info("Conexión foto: guardando imagen")
        self.archivo = self.folder + "/" + \
                "imagen.%d.%d.%.6f.jpeg" % (indice, foto, time.time())
        f = open(self.archivo, "wb")
        f.write(bytearray(self.jpeg_corrente))
        f.close()

        self.despedida()

    # Motivos NAK (nem todos se aplicam a download de fotos):
    # 00    Mensagem Ok (Por que NAK então? ACK = cmd 0xf0fe)
    # 01    Error de checksum (daqui para baixo, todos são erros)
    # 02    Número de bytes da mensaje
    # 03    Número de bytes do parámetro (payload)
    # 04    Parâmetro inexistente
    # 05    Indice parámetro
    # 06    Valor máximo
    # 07    Valor mínimo
    # 08    Quantidade de campos
    # 09    Nibble 0-9
    # 0a    Nibble 1-a
    # 0b    Nibble 0-f
    # 0c    Nibble 1-f-ex-b-c
    # 0d    ASCII
    # 0e    29 de fevereiro
    # 0f    Dia inválido
    # 10    Mês inválido
    # 11    Ano inválido
    # 12    Hora inválida
    # 13    Minuto inválido
    # 14    Segundo inválido
    # 15    Tipo de comando inválido
    # 16    Tecla especial
    # 17    Número de dígitos
    # 18    Número de dígitos senha
    # 19    Senha incorrecta (mas reportado na resposta da autenticação, no por NAK)
    # 1a    Partición inexistente
    # 1b    Usuário sem permissão na partición
    # 1c    Sin permissão programar
    # 1d    Buffer de recepção cheio
    # 1e    Sin permissão para desarmar
    # 1f    Necessária autenticação prévia
    # 20    Sin zonas habilitadas
    # 21    Sin permissão para comando
    # 22    Sin particiones definidas
    # 23    Evento sem foto associada
    # 24    Índice foto inválido
    # 25    Fragmento foto inválido
    # 26    Sistema no particionado
    # 27    Zonas abertas
    # 28    Ainda gravando foto / transferindo do sensor (tente mais tarde)
    # 29    Acesso mobile desabilitado
    # 2a    Operación no permitida
    # 2b    Memória RF vazia
    # 2c    Memória RF ocupada
    # 2d    Senha repetida
    # 2e    Falla ativação/desactivación
    # 2f    Sin permissão arme stay
    # 30    Desative a central
    # 31    Reset bloqueado
    # 32    Teclado bloqueado
    # 33    Recebimento de foto falhou
    # 34    No conectado ao servidor
    # 35    Taclado sem permissão
    # 36    Partición sem zonas stay
    # 37    Sin permissão bypass
    # 38    Firmware corrompido
    # fe    Comando inválido
    # ff    Error no especificado (no documentado mas observado se checksum ou tamanho pacote errado)
