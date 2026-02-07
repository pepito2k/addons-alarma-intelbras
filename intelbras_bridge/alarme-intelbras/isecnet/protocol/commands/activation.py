"""Comando de Activación (0x41) - Armar central ou partición.

Este comando ativa/arma a central de alarma ou uma partición específica.

Estructura do comando:
    - Código: 0x41
    - Contenido: 0 ou 1 byte
        - NULL (vazio): Ativa a central completa (todas las particiones)
        - 0x41: Ativa partición A
        - 0x42: Ativa partición B
        - 0x43: Ativa partición C
        - 0x44: Ativa partición D
        - 0x50: Ativa no modo Stay

Ejemplo de la documentación:
    Activación completa:
        Envío: 08 E9 21 31 32 33 34 41 21 5B
        Resposta: 02 E9 FE EA (ACK)
    
    Activación partición B com contraseña 6 dígitos:
        09 E9 21 31 32 33 34 41 42 21 18
"""

from typing import Self

from ...const import CommandCode, PartitionCode
from .base import Command


class ActivationCommand(Command):
    """Comando para ativar/armar a central de alarma.
    
    Attributes:
        partition: Partición a ser ativada (None = todas).
    """

    def __init__(
        self,
        password: str,
        partition: PartitionCode | None = None,
    ) -> None:
        """Inicializa el comando de activación.
        
        Args:
            password: Contraseña do usuario (4-6 dígitos).
            partition: Partición específica ou None para ativar todas.
        """
        super().__init__(password)
        self._partition = partition

    @property
    def code(self) -> int:
        """Código do comando de activación (0x41)."""
        return CommandCode.ACTIVATION

    @property
    def partition(self) -> PartitionCode | None:
        """Partición a ser ativada."""
        return self._partition

    def build_content(self) -> bytes:
        """Construye o contenido do comando.
        
        Returns:
            Bytes vazios para ativar todas las particiones,
            ou byte da partición específica.
        """
        if self._partition is None or self._partition == PartitionCode.ALL:
            return bytes()
        return bytes([self._partition])

    @classmethod
    def arm_all(cls, password: str) -> Self:
        """Cria comando para armar todas las particiones.
        
        Args:
            password: Contraseña do usuario.
            
        Returns:
            Instancia de ActivationCommand.
        """
        return cls(password, partition=None)

    @classmethod
    def arm_partition_a(cls, password: str) -> Self:
        """Cria comando para armar partición A.
        
        Args:
            password: Contraseña do usuario.
            
        Returns:
            Instancia de ActivationCommand.
        """
        return cls(password, partition=PartitionCode.PARTITION_A)

    @classmethod
    def arm_partition_b(cls, password: str) -> Self:
        """Cria comando para armar partición B.
        
        Args:
            password: Contraseña do usuario.
            
        Returns:
            Instancia de ActivationCommand.
        """
        return cls(password, partition=PartitionCode.PARTITION_B)

    @classmethod
    def arm_partition_c(cls, password: str) -> Self:
        """Cria comando para armar partición C.
        
        Args:
            password: Contraseña do usuario.
            
        Returns:
            Instancia de ActivationCommand.
        """
        return cls(password, partition=PartitionCode.PARTITION_C)

    @classmethod
    def arm_partition_d(cls, password: str) -> Self:
        """Cria comando para armar partición D.
        
        Args:
            password: Contraseña do usuario.
            
        Returns:
            Instancia de ActivationCommand.
        """
        return cls(password, partition=PartitionCode.PARTITION_D)

    @classmethod
    def arm_stay(cls, password: str) -> Self:
        """Cria comando para armar no modo Stay.
        
        Args:
            password: Contraseña do usuario.
            
        Returns:
            Instancia de ActivationCommand.
        """
        return cls(password, partition=PartitionCode.STAY_MODE)

    def __repr__(self) -> str:
        partition_str = self._partition.name if self._partition else "ALL"
        return f"ActivationCommand(password='****', partition={partition_str})"



