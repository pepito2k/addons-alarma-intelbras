"""Clase base para comandos ISECMobile.

Esta clase define a interface que todos los comandos devem implementar,
permitindo uma arquitetura extensível para adicionar novos comandos.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..isecmobile import ISECMobileFrame
    from ..isecnet import ISECNetFrame


class Command(ABC):
    """Clase base abstrata para comandos ISECMobile.
    
    Subclases devem implementar:
        - code: Código do comando
        - build_mobile_frame: Construir o frame ISECMobile
    """

    def __init__(self, password: str) -> None:
        """Inicializa el comando com a contraseña do usuario.
        
        Args:
            password: Contraseña do usuario para autenticação (4-6 dígitos).
        """
        self._password = password

    @property
    @abstractmethod
    def code(self) -> int:
        """Código do comando (ex: 0x41 para activación)."""
        ...

    @property
    def password(self) -> str:
        """Contraseña do usuario."""
        return self._password

    @abstractmethod
    def build_content(self) -> bytes:
        """Construye o contenido específico do comando.
        
        Returns:
            Bytes do contenido do comando (pode ser vazio).
        """
        ...

    def build_mobile_frame(self) -> "ISECMobileFrame":
        """Construye o frame ISECMobile para este comando.
        
        Returns:
            Instancia de ISECMobileFrame.
        """
        from ..isecmobile import ISECMobileFrame
        
        return ISECMobileFrame.create(
            password=self._password,
            command=self.code,
            content=self.build_content(),
        )

    def build_net_frame(self) -> "ISECNetFrame":
        """Construye o frame ISECNet completo para este comando.
        
        Returns:
            Instancia de ISECNetFrame pronta para transmisión.
        """
        from ..isecnet import ISECNetFrame
        
        mobile_frame = self.build_mobile_frame()
        return ISECNetFrame.create_mobile_frame(mobile_frame.build())

    def build(self) -> bytes:
        """Construye los bytes finais prontos para envio via socket.
        
        Returns:
            Bytes do pacote completo (ISECNet com ISECMobile encapsulado).
        """
        return self.build_net_frame().build()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(password='****', code=0x{self.code:02X})"



