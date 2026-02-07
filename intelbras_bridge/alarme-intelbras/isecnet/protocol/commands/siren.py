"""Comandos de Controle de Sirene (0x43 e 0x63).

Este módulo implementa los comandos para ligar e apagar a sirene da central.

Comandos:
    - 0x43: Liga a sirene
    - 0x63: Desliga a sirene

Estructura dos comandos:
    Ambos são frames curtos sem contenido adicional além do comando.
    El frame ISECMobile contém apenas: delimitador, contraseña, comando, delimitador.

Exemplos da documentação:
    Ligar sirene com contraseña 1234:
        08 E9 21 31 32 33 34 43 21 59
    
    Desligar sirene com contraseña 1234:
        0A E9 21 31 32 33 34 63 21 79
"""

from typing import Self

from ...const import CommandCode
from .base import Command


class SirenCommand(Command):
    """Comando para controlar a sirene da central.
    
    Attributes:
        turn_on: Si True, liga a sirene (0x43). Si False, apaga (0x63).
    """

    def __init__(
        self,
        password: str,
        turn_on: bool,
    ) -> None:
        """Inicializa el comando de controle de sirene.
        
        Args:
            password: Contraseña do usuario (4-6 dígitos).
            turn_on: Si True, liga a sirene. Si False, apaga.
        """
        super().__init__(password)
        self._turn_on = turn_on

    @property
    def code(self) -> int:
        """Código do comando de sirene."""
        return CommandCode.SIREN_ON if self._turn_on else CommandCode.SIREN_OFF

    @property
    def turn_on(self) -> bool:
        """Si o comando liga a sirene."""
        return self._turn_on

    def build_content(self) -> bytes:
        """Construye o contenido do comando.
        
        Os comandos de sirene no têm contenido adicional além do comando em si.
        El contenido é vazio, pois o comando já está no código.
        
        Returns:
            Bytes vazios (o comando está no código, no no contenido).
        """
        return bytes()

    @classmethod
    def turn_on_siren(cls, password: str) -> Self:
        """Cria comando para ligar a sirene.
        
        Args:
            password: Contraseña do usuario.
            
        Returns:
            Instancia de SirenCommand para ligar.
        """
        return cls(password, turn_on=True)

    @classmethod
    def turn_off_siren(cls, password: str) -> Self:
        """Cria comando para apagar a sirene.
        
        Args:
            password: Contraseña do usuario.
            
        Returns:
            Instancia de SirenCommand para apagar.
        """
        return cls(password, turn_on=False)

    def __repr__(self) -> str:
        action_str = "ON" if self._turn_on else "OFF"
        return f"SirenCommand(password='****', action={action_str})"

