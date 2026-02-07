"""Comando de Controle PGM (0x50) - Ligar/Desligar salidas programáveis.

Este comando controla as salidas PGM (Programmable Gate Module) da central.

Estructura do comando:
    - Código: 0x50
    - Contenido: 2 bytes
        - Byte 1 (Sub Comando):
            - 0x4C ('L'): Liga a PGM
            - 0x44 ('D'): Desliga a PGM
        - Byte 2 (Dirección de Saída):
            - 0x31: PGM 1
            - 0x32: PGM 2
            - ...
            - 0x42: PGM 18
            - 0x43: PGM 19

Exemplos da documentação:
    Ligar PGM 1 com contraseña 1234:
        0A E9 21 31 32 33 34 50 4C 31 21 35
    
    Desligar PGM 1 com contraseña 1234:
        0A E9 21 31 32 33 34 50 44 32 21 3E
"""

from typing import Self

from ...const import CommandCode, PGMAction, PGMOutput
from .base import Command


class PGMCommand(Command):
    """Comando para controlar salidas PGM da central.
    
    Attributes:
        action: Ação a executar (ligar/apagar).
        output: Número da PGM a controlar (1-19).
    """

    def __init__(
        self,
        password: str,
        action: PGMAction,
        output: int | PGMOutput,
    ) -> None:
        """Inicializa el comando de controle PGM.
        
        Args:
            password: Contraseña do usuario (4-6 dígitos).
            action: Ação a executar (TURN_ON ou TURN_OFF).
            output: Número da PGM (1-19) ou PGMOutput enum.
        """
        super().__init__(password)
        self._action = action
        
        # Convierte número para enum se necesario
        if isinstance(output, PGMOutput):
            self._output = output
        else:
            self._output = PGMOutput.from_number(output)

    @property
    def code(self) -> int:
        """Código do comando de controle PGM (0x50)."""
        return CommandCode.PGM_CONTROL

    @property
    def action(self) -> PGMAction:
        """Ação a executar."""
        return self._action

    @property
    def output(self) -> PGMOutput:
        """Saída PGM a controlar."""
        return self._output

    @property
    def output_number(self) -> int:
        """Número da PGM (1-19)."""
        return self._output.value - 0x30

    def build_content(self) -> bytes:
        """Construye o contenido do comando.
        
        Returns:
            2 bytes: [sub_comando, dirección_salida]
        """
        return bytes([self._action.value, self._output.value])

    @classmethod
    def turn_on(cls, password: str, pgm_number: int) -> Self:
        """Cria comando para ligar uma PGM.
        
        Args:
            password: Contraseña do usuario.
            pgm_number: Número da PGM (1-19).
            
        Returns:
            Instancia de PGMCommand.
        """
        return cls(password, PGMAction.TURN_ON, pgm_number)

    @classmethod
    def turn_off(cls, password: str, pgm_number: int) -> Self:
        """Cria comando para apagar uma PGM.
        
        Args:
            password: Contraseña do usuario.
            pgm_number: Número da PGM (1-19).
            
        Returns:
            Instancia de PGMCommand.
        """
        return cls(password, PGMAction.TURN_OFF, pgm_number)

    def __repr__(self) -> str:
        action_str = "ON" if self._action == PGMAction.TURN_ON else "OFF"
        return f"PGMCommand(password='****', action={action_str}, pgm={self.output_number})"

