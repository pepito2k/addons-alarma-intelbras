"""Frame ISECNet - Capa de transporte do protocolo.

O frame ISECNet encapsula los comandos ISECMobile para transmisión via TCP.

Estructura do frame:
| Campo      | Bytes | Descripción                           |
|------------|-------|-------------------------------------|
| Nº Bytes   | 1     | Tamaño total do pacote             |
| Comando    | 1     | 0xE9 para ISECMobile                |
| Contenido   | N     | Frame ISECMobile                    |
| Checksum   | 1     | XOR de todos bytes ^ 0xFF           |

Ejemplo de la documentación:
    Envío: 08 E9 21 31 32 33 34 41 21 5B
    - 08: 8 bytes no pacote
    - E9: Comando ISECMobile
    - 21 31 32 33 34 41 21: Frame ISECMobile
    - 5B: Checksum
"""

from dataclasses import dataclass
from typing import Self

from ..const import ISECNET_COMMAND_MOBILE, ISECNET_COMMAND_HEARTBEAT, ResponseCode
from .checksum import Checksum


class ISECNetError(Exception):
    """Error de análisis o validación de frame ISECNet."""
    pass


@dataclass
class ISECNetFrame:
    """Representa un frame do protocolo ISECNet.
    
    Attributes:
        command: Código do comando (generalmente 0xE9 para ISECMobile).
        content: Contenido/payload do frame (frame ISECMobile).
    """
    
    command: int
    content: bytes

    @classmethod
    def create_mobile_frame(cls, isecmobile_content: bytes) -> Self:
        """Crea un frame ISECNet para encapsular contenido ISECMobile.
        
        Args:
            isecmobile_content: Bytes do frame ISECMobile.
            
        Returns:
            Instancia de ISECNetFrame configurada.
        """
        return cls(command=ISECNET_COMMAND_MOBILE, content=isecmobile_content)

    def build(self) -> bytes:
        """Construye o frame completo pronto para transmisión.
        
        El frame inclui: tamaño, comando, contenido e checksum.
        
        El campo "Nº de bytes" indica quantos bytes seguem após ele,
        excluindo o checksum (ou seja: comando + contenido).
        
        Returns:
            Bytes do frame completo.
            
        Example:
            >>> frame = ISECNetFrame.create_mobile_frame(bytes([0x21, 0x31, 0x32, 0x33, 0x34, 0x41, 0x21]))
            >>> frame.build().hex(' ')
            '08 e9 21 31 32 33 34 41 21 5b'
        """
        # Nº de bytes = comando (1) + contenido (N)
        # No incluye o próprio byte de tamaño nem o checksum
        size = 1 + len(self.content)  # command + content
        
        # Monta o frame sin checksum
        frame_without_checksum = bytes([size, self.command]) + self.content
        
        # Adiciona checksum
        return Checksum.append(frame_without_checksum)

    @classmethod
    def parse(cls, data: bytes | bytearray) -> Self:
        """Realiza el análisis de bytes recibidos em um frame ISECNet.
        
        El campo "Nº de bytes" indica quantos bytes seguem após ele,
        excluindo o checksum. Tamaño total = 1 (size) + size + 1 (checksum).
        
        Args:
            data: Bytes do frame completo (incluindo checksum).
            
        Returns:
            Instancia de ISECNetFrame analizada.
            
        Raises:
            ISECNetError: Si o frame for inválido.
        """
        if len(data) < 3:
            raise ISECNetError(f"Frame demasiado corto: {len(data)} bytes (mínimo 3)")
        
        size = data[0]
        expected_total = size + 2  # size byte + content indicated by size + checksum
        
        if len(data) != expected_total:
            raise ISECNetError(
                f"Tamaño inconsistente: header indica {size} bytes de contenido "
                f"(total esperado {expected_total}), recibido {len(data)} bytes"
            )
        
        # Valida checksum
        if not Checksum.validate_packet(data):
            raise ISECNetError("Checksum inválido")
        
        command = data[1]
        content = bytes(data[2:-1])  # Excluye size, command e checksum
        
        return cls(command=command, content=content)

    @classmethod
    def try_parse(cls, data: bytes | bytearray) -> Self | None:
        """Intenta fazer o análisis de bytes, devolviendo None en caso de error.
        
        Args:
            data: Bytes do frame completo.
            
        Returns:
            Instancia de ISECNetFrame ou None se inválido.
        """
        try:
            return cls.parse(data)
        except ISECNetError:
            return None

    @property
    def is_mobile_command(self) -> bool:
        """Verifica si é um comando ISECMobile (0xE9)."""
        return self.command == ISECNET_COMMAND_MOBILE

    @property
    def is_heartbeat(self) -> bool:
        """Verifica si é um comando de heartbeat (0xF7)."""
        return self.command == ISECNET_COMMAND_HEARTBEAT

    @classmethod
    def create_heartbeat(cls) -> "ISECNetFrame":
        """Crea un frame de heartbeat (0xF7).
        
        Returns:
            Frame de heartbeat pronto para envio.
        """
        return cls(command=ISECNET_COMMAND_HEARTBEAT, content=bytes())

    @classmethod
    def create_ack_response(cls) -> "ISECNetFrame":
        """Crea una respuesta ACK (0xFE) encapsulada em 0xE9.
        
        Usado para responder a comandos ISECMobile.
        
        Returns:
            Frame de respuesta ACK encapsulado.
        """
        return cls(command=ISECNET_COMMAND_MOBILE, content=bytes([ResponseCode.ACK]))

    @classmethod
    def create_simple_ack(cls) -> "ISECNetFrame":
        """Crea una respuesta ACK simples (frame curto).
        
        El ACK (0xFE) é enviado diretamente como comando, sem encapsulamento.
        Usado para responder a comandos como 0x94 e 0xF7.
        
        Returns:
            Frame ACK simples.
        """
        return cls(command=ResponseCode.ACK, content=bytes())

    def __repr__(self) -> str:
        return (
            f"ISECNetFrame(command=0x{self.command:02X}, "
            f"content={self.content.hex(' ')})"
        )


class ISECNetFrameReader:
    """Lector de frames ISECNet de um stream de bytes.
    
    Útil para processar datos recibidos via socket, donde múltiplos
    frames pueden llegar ou frames pueden llegar parcialmente.
    """

    def __init__(self) -> None:
        """Inicializa el lector."""
        self._buffer = bytearray()

    def feed(self, data: bytes | bytearray) -> list[ISECNetFrame]:
        """Alimenta datos al buffer e devuelve frames completos.
        
        Args:
            data: Bytes recibidos.
            
        Returns:
            Lista de frames completos analizados.
        """
        self._buffer.extend(data)
        frames: list[ISECNetFrame] = []
        
        while self._try_extract_frame(frames):
            pass
        
        return frames

    def _try_extract_frame(self, frames: list[ISECNetFrame]) -> bool:
        """Intenta extrair um frame do buffer.
        
        Args:
            frames: Lista donde adicionar frames encontrados.
            
        Returns:
            True si se extrajo un frame, False de lo contrario.
        """
        if len(self._buffer) < 1:
            return False
        
        # Verifica si é um heartbeat de 1 byte (0xF7)
        # A central envía apenas o byte F7, sem tamaño nem checksum
        if self._buffer[0] == ISECNET_COMMAND_HEARTBEAT:
            frames.append(ISECNetFrame(command=ISECNET_COMMAND_HEARTBEAT, content=bytes()))
            self._buffer.pop(0)
            return True
        
        # Frame normal precisa de al menos 3 bytes
        if len(self._buffer) < 3:
            return False
        
        size = self._buffer[0]
        total_size = size + 2  # size byte + content + checksum
        
        if size < 1:
            # Tamaño inválido (debe tener al menos o comando), descarte byte
            self._buffer.pop(0)
            return True
        
        if len(self._buffer) < total_size:
            # Espera más datos
            return False
        
        frame_data = bytes(self._buffer[:total_size])
        frame = ISECNetFrame.try_parse(frame_data)
        
        if frame:
            frames.append(frame)
            del self._buffer[:total_size]
        else:
            # Frame inválido, descarte primer byte e intenta nuevamente
            self._buffer.pop(0)
        
        return True

    def clear(self) -> None:
        """Limpia el buffer interno."""
        self._buffer.clear()

    @property
    def pending_bytes(self) -> int:
        """Devuelve o número de bytes pendentes no buffer."""
        return len(self._buffer)

