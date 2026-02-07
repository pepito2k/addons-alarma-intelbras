"""Frame ISECMobile - Capa de comandos do protocolo.

O frame ISECMobile contém los comandos enviados a la central de alarma.
Este frame é encapsulado dentro de um frame ISECNet para transmisión.

Estructura do frame:
| Campo      | Bytes | Descripción                              |
|------------|-------|----------------------------------------|
| Inicio     | 1     | 0x21 ("!") - delimitador               |
| Contraseña      | 4-6   | Contraseña ASCII do usuario                 |
| Comando    | 1-2   | Código do comando                      |
| Contenido   | 0-52  | Datos do comando (opcional)            |
| Fin        | 1     | 0x21 ("!") - delimitador               |

Ejemplo de la documentación (activación completa):
    21 31 32 33 34 41 21
    - 21: Inicio do frame
    - 31 32 33 34: Contraseña "1234" em ASCII
    - 41: Comando de activación
    - 21: Fin do frame
"""

from dataclasses import dataclass, field
from typing import Self

from ..const import (
    ISECMOBILE_FRAME_DELIMITER,
    ISECMOBILE_PASSWORD_MIN_LEN,
    ISECMOBILE_PASSWORD_MAX_LEN,
    ISECMOBILE_CONTENT_MAX_LEN,
)


class ISECMobileError(Exception):
    """Error de análisis o validación de frame ISECMobile."""
    pass


@dataclass
class ISECMobileFrame:
    """Representa un frame do protocolo ISECMobile.
    
    Attributes:
        password: Contraseña do usuario (string ou bytes).
        command: Código do comando (1-2 bytes).
        content: Contenido/datos do comando (opcional).
    """
    
    password: bytes
    command: bytes
    content: bytes = field(default_factory=bytes)

    @classmethod
    def create(
        cls,
        password: str | bytes,
        command: int | bytes,
        content: bytes | None = None,
    ) -> Self:
        """Crea un frame ISECMobile.
        
        Args:
            password: Contraseña do usuario (4-6 caracteres/bytes).
            command: Código do comando (int ou bytes).
            content: Datos opcionais do comando.
            
        Returns:
            Instancia de ISECMobileFrame.
            
        Raises:
            ISECMobileError: Si los parámetros forem inválidos.
        """
        # Convierte contraseña para bytes
        if isinstance(password, str):
            password_bytes = password.encode('ascii')
        else:
            password_bytes = bytes(password)
        
        # Valida tamaño da contraseña
        if not ISECMOBILE_PASSWORD_MIN_LEN <= len(password_bytes) <= ISECMOBILE_PASSWORD_MAX_LEN:
            raise ISECMobileError(
                f"Contraseña debe tener entre {ISECMOBILE_PASSWORD_MIN_LEN} e "
                f"{ISECMOBILE_PASSWORD_MAX_LEN} caracteres, "
                f"recibido {len(password_bytes)}"
            )
        
        # Convierte comando para bytes
        if isinstance(command, int):
            command_bytes = bytes([command])
        else:
            command_bytes = bytes(command)
        
        if not 1 <= len(command_bytes) <= 2:
            raise ISECMobileError(
                f"Comando debe tener 1 ou 2 bytes, recibido {len(command_bytes)}"
            )
        
        # Valida contenido
        content_bytes = bytes(content) if content else bytes()
        
        if len(content_bytes) > ISECMOBILE_CONTENT_MAX_LEN:
            raise ISECMobileError(
                f"Contenido máximo de {ISECMOBILE_CONTENT_MAX_LEN} bytes, "
                f"recibido {len(content_bytes)}"
            )
        
        return cls(
            password=password_bytes,
            command=command_bytes,
            content=content_bytes,
        )

    def build(self) -> bytes:
        """Construye o frame completo.
        
        Returns:
            Bytes do frame ISECMobile.
            
        Example:
            >>> frame = ISECMobileFrame.create("1234", 0x41)
            >>> frame.build().hex(' ')
            '21 31 32 33 34 41 21'
        """
        return bytes([
            ISECMOBILE_FRAME_DELIMITER,
            *self.password,
            *self.command,
            *self.content,
            ISECMOBILE_FRAME_DELIMITER,
        ])

    @classmethod
    def parse(cls, data: bytes | bytearray) -> Self:
        """Realiza el análisis de bytes em um frame ISECMobile.
        
        Args:
            data: Bytes do frame completo.
            
        Returns:
            Instancia de ISECMobileFrame analizada.
            
        Raises:
            ISECMobileError: Si o frame for inválido.
        """
        if len(data) < 6:
            raise ISECMobileError(
                f"Frame demasiado corto: {len(data)} bytes (mínimo 6)"
            )
        
        # Verifica delimitadores
        if data[0] != ISECMOBILE_FRAME_DELIMITER:
            raise ISECMobileError(
                f"Delimitador inicial inválido: 0x{data[0]:02X} "
                f"(esperado 0x{ISECMOBILE_FRAME_DELIMITER:02X})"
            )
        
        if data[-1] != ISECMOBILE_FRAME_DELIMITER:
            raise ISECMobileError(
                f"Delimitador final inválido: 0x{data[-1]:02X} "
                f"(esperado 0x{ISECMOBILE_FRAME_DELIMITER:02X})"
            )
        
        # Remove delimitadores
        inner = data[1:-1]
        
        if len(inner) < ISECMOBILE_PASSWORD_MIN_LEN + 1:
            raise ISECMobileError(
                f"Contenido interno demasiado corto: {len(inner)} bytes"
            )
        
        # Intenta determinar o tamaño da contraseña
        # Asumimos que a contraseña tem entre 4 e 6 bytes
        # El comando vem depois da contraseña
        # Necesitamos encontrar o fim da contraseña de forma heurística
        
        # Estrategia: Assumir contraseña de 4 bytes por predeterminado (más comum)
        # Si necesario, puedenos ajustar basado no contexto
        password_len = ISECMOBILE_PASSWORD_MIN_LEN
        
        # Verifica si hay más contenido para contraseña maior
        # A contraseña generalmente é numérica ASCII (0x30-0x39)
        for i in range(ISECMOBILE_PASSWORD_MIN_LEN, min(ISECMOBILE_PASSWORD_MAX_LEN + 1, len(inner) - 1)):
            if inner[i] >= 0x41 and inner[i] <= 0x50:  # Comandos começam generalmente em 0x41+
                password_len = i
                break
        
        password = bytes(inner[:password_len])
        
        # Determina tamaño do comando (1 ou 2 bytes)
        # Comandos conhecidos são de 1 byte, mas o protocolo suporta 2
        remaining = inner[password_len:]
        
        if len(remaining) == 0:
            raise ISECMobileError("Comando ausente en el frame")
        
        # Asumimos comando de 1 byte por predeterminado
        command = bytes([remaining[0]])
        content = bytes(remaining[1:]) if len(remaining) > 1 else bytes()
        
        return cls(password=password, command=command, content=content)

    @classmethod
    def try_parse(cls, data: bytes | bytearray) -> Self | None:
        """Intenta fazer o análisis de bytes, devolviendo None en caso de error.
        
        Args:
            data: Bytes do frame completo.
            
        Returns:
            Instancia de ISECMobileFrame ou None se inválido.
        """
        try:
            return cls.parse(data)
        except ISECMobileError:
            return None

    @property
    def command_code(self) -> int:
        """Devuelve o código do comando como entero."""
        return self.command[0]

    @property
    def password_str(self) -> str:
        """Devuelve a contraseña como cadena."""
        return self.password.decode('ascii', errors='replace')

    def __repr__(self) -> str:
        return (
            f"ISECMobileFrame(password='{self.password_str}', "
            f"command=0x{self.command.hex()}, "
            f"content={self.content.hex(' ') if self.content else 'none'})"
        )



