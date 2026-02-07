"""Parser de respuestas ISECMobile.

A central de alarma respdonde aos comandos com frames curtos indicando
éxito (ACK) ou error (NACK).

Estructura da respuesta (dentro do ISECNet):
    - ACK: 1 byte = 0xFE (éxito)
    - NACK: 1 byte = 0xE0-0xEA (código de error)

Ejemplo de la documentación:
    Resposta ACK (activación bem-sucedida):
        02 E9 FE EA
        - 02: 2 bytes no pacote
        - E9: Comando ISECMobile
        - FE: ACK (éxito)
        - EA: Checksum
"""

from dataclasses import dataclass
from enum import Enum
from typing import Self

from ..const import (
    ResponseCode,
    RESPONSE_MESSAGES,
    is_ack,
    is_nack,
)
from .isecnet import ISECNetFrame, ISECNetError


class ResponseType(Enum):
    """Tipo de respuesta recebida."""
    
    ACK = "ack"
    """Comando executado com éxito."""
    
    NACK = "nack"
    """Erro na execução do comando."""
    
    DATA = "data"
    """Resposta com datos (para comandos de consulta)."""
    
    UNKNOWN = "unknown"
    """Resposta desconhecida."""


@dataclass
class Response:
    """Representa una respuesta da central de alarma.
    
    Attributes:
        response_type: Tipo da respuesta (ACK, NACK, DATA, UNKNOWN).
        code: Código de respuesta (0xFE para ACK, 0xE0-0xEA para NACK).
        data: Datos adicionais da respuesta (para respuestas tipo DATA).
        raw_frame: Frame ISECNet original.
    """
    
    response_type: ResponseType
    code: int
    data: bytes
    raw_frame: ISECNetFrame

    @property
    def is_success(self) -> bool:
        """Verifica si a respuesta indica éxito."""
        # Respostas com datos grandes (status) são consideradas éxito
        return self.response_type == ResponseType.ACK or (
            self.response_type == ResponseType.DATA and len(self.data) >= 43
        )

    @property
    def is_error(self) -> bool:
        """Verifica si a respuesta indica error."""
        return self.response_type == ResponseType.NACK

    @property
    def message(self) -> str:
        """Devuelve a mensaje descriptiva da respuesta."""
        if self.response_type == ResponseType.DATA and len(self.data) >= 43:
            return f"Resposta com datos ({len(self.data)} bytes)"
        return RESPONSE_MESSAGES.get(
            self.code, 
            f"Código desconocido: 0x{self.code:02X}"
        )

    @property
    def error_code(self) -> ResponseCode | None:
        """Devuelve o código de error como enum, se for NACK."""
        if self.is_error:
            try:
                return ResponseCode(self.code)
            except ValueError:
                return None
        return None

    @classmethod
    def from_isecnet_frame(cls, frame: ISECNetFrame) -> Self:
        """Crea una Response a partir de um frame ISECNet.
        
        Args:
            frame: Frame ISECNet recibido.
            
        Returns:
            Instancia de Response analizada.
        """
        content = frame.content
        
        if len(content) == 0:
            return cls(
                response_type=ResponseType.UNKNOWN,
                code=0,
                data=bytes(),
                raw_frame=frame,
            )
        
        # Si o contenido tem muitos bytes (43+ para estado parcial, 54+ para completo),
        # é uma respuesta DATA mesmo que o primer byte no seja ACK/NACK
        if len(content) >= 43:
            # Resposta com datos grandes (comandos 0x5A ou 0x5B)
            response_type = ResponseType.DATA
            code = 0x00  # Código neutro para respuestas com datos
            data = content  # Todo o contenido são los datos
        else:
            code = content[0] if len(content) > 0 else 0
            data = content[1:] if len(content) > 1 else bytes()
            
            # Determina o tipo de respuesta
            if is_ack(code):
                response_type = ResponseType.ACK
            elif is_nack(code):
                response_type = ResponseType.NACK
            elif len(data) > 0:
                response_type = ResponseType.DATA
            else:
                response_type = ResponseType.UNKNOWN
        
        return cls(
            response_type=response_type,
            code=code,
            data=data,
            raw_frame=frame,
        )

    @classmethod
    def parse(cls, raw_data: bytes | bytearray) -> Self:
        """Realiza el análisis de bytes brutos em uma Response.
        
        Args:
            raw_data: Bytes do pacote ISECNet completo.
            
        Returns:
            Instancia de Response analizada.
            
        Raises:
            ISECNetError: Si o frame for inválido.
        """
        frame = ISECNetFrame.parse(raw_data)
        return cls.from_isecnet_frame(frame)

    @classmethod
    def try_parse(cls, raw_data: bytes | bytearray) -> Self | None:
        """Intenta fazer o análisis, devolviendo None en caso de error.
        
        Args:
            raw_data: Bytes do pacote ISECNet completo.
            
        Returns:
            Instancia de Response ou None se inválido.
        """
        try:
            return cls.parse(raw_data)
        except (ISECNetError, Exception):
            return None

    def __repr__(self) -> str:
        return (
            f"Response(type={self.response_type.value}, "
            f"code=0x{self.code:02X}, "
            f"message='{self.message}')"
        )


class ResponseParser:
    """Parser de respuestas com suporte a múltiplos frames.
    
    Útil para processar respuestas que pueden conter datos adicionais
    ou múltiplos frames.
    """

    @staticmethod
    def parse_ack_response(frame: ISECNetFrame) -> Response:
        """Processa um frame esperando ACK/NACK simples.
        
        Args:
            frame: Frame ISECNet recibido.
            
        Returns:
            Response analizada.
        """
        return Response.from_isecnet_frame(frame)

    @staticmethod
    def is_ack_frame(frame: ISECNetFrame) -> bool:
        """Verifica si um frame é respuesta ACK.
        
        Args:
            frame: Frame ISECNet a verificar.
            
        Returns:
            True se for ACK.
        """
        if len(frame.content) == 0:
            return False
        return is_ack(frame.content[0])

    @staticmethod
    def is_nack_frame(frame: ISECNetFrame) -> bool:
        """Verifica si um frame é respuesta NACK.
        
        Args:
            frame: Frame ISECNet a verificar.
            
        Returns:
            True se for NACK.
        """
        if len(frame.content) == 0:
            return False
        return is_nack(frame.content[0])

    @staticmethod
    def get_nack_reason(frame: ISECNetFrame) -> str:
        """Obtiene a razão de um NACK.
        
        Args:
            frame: Frame ISECNet NACK.
            
        Returns:
            Mensagem descriptiva do error.
        """
        if len(frame.content) == 0:
            return "Resposta vazia"
        code = frame.content[0]
        return RESPONSE_MESSAGES.get(code, f"Erro desconocido: 0x{code:02X}")
