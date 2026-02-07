"""Comando de Desactivación (0x44) - Desarmar central ou partición.

Este comando desativa/desarma a central de alarma ou uma partición específica.

Estructura do comando:
    - Código: 0x44
    - Contenido: 0 ou 1 byte
        - NULL (vazio): Desativa a central completa (todas las particiones)
        - 0x41: Desativa partición A
        - 0x42: Desativa partición B
        - 0x43: Desativa partición C
        - 0x44: Desativa partición D

Exemplos da documentação:
    Desactivación completa com contraseña 4 dígitos:
        Envío: 08 E9 21 31 32 33 34 44 21 5E
        Resposta: 02 E9 FE EA (ACK)
    
    Desactivación partición A com contraseña 4 dígitos (1234):
        09 E9 21 31 32 33 34 44 41 21 1E
"""

from typing import Self

from ...const import CommandCode, PartitionCode
from .base import Command


class DeactivationCommand(Command):
    """Comando para desarmar/desarmar a central de alarma.
    
    Attributes:
        partition: Partición a ser desativada (None = todas).
    """

    def __init__(
        self,
        password: str,
        partition: PartitionCode | None = None,
    ) -> None:
        """Inicializa el comando de desactivación.
        
        Args:
            password: Contraseña do usuario (4-6 dígitos).
            partition: Partición específica ou None para desarmar todas.
        """
        super().__init__(password)
        self._partition = partition

    @property
    def code(self) -> int:
        """Código do comando de desactivación (0x44)."""
        return CommandCode.DEACTIVATION

    @property
    def partition(self) -> PartitionCode | None:
        """Partición a ser desativada."""
        return self._partition

    def build_content(self) -> bytes:
        """Construye o contenido do comando.
        
        Returns:
            Bytes vazios para desarmar todas las particiones,
            ou byte da partición específica.
        """
        if self._partition is None or self._partition == PartitionCode.ALL:
            return bytes()
        return bytes([self._partition])

    @classmethod
    def disarm_all(cls, password: str) -> Self:
        """Cria comando para desarmar todas las particiones.
        
        Args:
            password: Contraseña do usuario.
            
        Returns:
            Instancia de DeactivationCommand.
        """
        return cls(password, partition=None)

    @classmethod
    def disarm_partition_a(cls, password: str) -> Self:
        """Cria comando para desarmar partición A.
        
        Args:
            password: Contraseña do usuario.
            
        Returns:
            Instancia de DeactivationCommand.
        """
        return cls(password, partition=PartitionCode.PARTITION_A)

    @classmethod
    def disarm_partition_b(cls, password: str) -> Self:
        """Cria comando para desarmar partición B.
        
        Args:
            password: Contraseña do usuario.
            
        Returns:
            Instancia de DeactivationCommand.
        """
        return cls(password, partition=PartitionCode.PARTITION_B)

    @classmethod
    def disarm_partition_c(cls, password: str) -> Self:
        """Cria comando para desarmar partición C.
        
        Args:
            password: Contraseña do usuario.
            
        Returns:
            Instancia de DeactivationCommand.
        """
        return cls(password, partition=PartitionCode.PARTITION_C)

    @classmethod
    def disarm_partition_d(cls, password: str) -> Self:
        """Cria comando para desarmar partición D.
        
        Args:
            password: Contraseña do usuario.
            
        Returns:
            Instancia de DeactivationCommand.
        """
        return cls(password, partition=PartitionCode.PARTITION_D)

    def __repr__(self) -> str:
        partition_str = self._partition.name if self._partition else "ALL"
        return f"DeactivationCommand(password='****', partition={partition_str})"



