"""Constantes do protocolo ISECNet/ISECMobile."""

from enum import IntEnum


# =============================================================================
# Configuraciones de Rede
# =============================================================================

DEFAULT_PORT = 9009
"""Porta TCP predeterminado para comunicación ISECNet."""

RESPONSE_TIMEOUT = 8.0
"""Timeout máximo em segundos para esperar respuesta da central (Ethernet)."""

KEEPALIVE_INTERVAL = 30.0
"""Intervalo em segundos para envio de keep-alive."""


# =============================================================================
# Protocolo ISECNet
# =============================================================================

ISECNET_COMMAND_MOBILE = 0xE9
"""Comando ISECNet para encapsular frames ISECMobile."""

ISECNET_COMMAND_HEARTBEAT = 0xF7
"""Comando ISECNet para heartbeat (keep-alive)."""


# =============================================================================
# Protocolo ISECMobile
# =============================================================================

ISECMOBILE_FRAME_DELIMITER = 0x21
"""Delimitador de frame ISECMobile (caractere '!')."""

ISECMOBILE_PASSWORD_MIN_LEN = 4
"""Tamaño mínimo da contraseña em bytes."""

ISECMOBILE_PASSWORD_MAX_LEN = 6
"""Tamaño máximo da contraseña em bytes."""

ISECMOBILE_CONTENT_MAX_LEN = 52
"""Tamaño máximo do contenido em bytes."""


# =============================================================================
# Comandos ISECMobile
# =============================================================================

class CommandCode(IntEnum):
    """Códigos de comandos ISECMobile."""
    
    ACTIVATION = 0x41
    """Comando 0x41 - Activación/Armar da central ou partición."""
    
    DEACTIVATION = 0x44
    """Comando 0x44 - Desactivación/Desarmar da central ou partición."""
    
    PGM_CONTROL = 0x50
    """Comando 0x50 - Controle de PGM (ligar/apagar salida programável)."""
    
    SIREN_ON = 0x43
    """Comando 0x43 - Liga a sirene."""
    
    SIREN_OFF = 0x63
    """Comando 0x63 - Desliga a sirene."""
    
    STATUS_REQUEST_PARTIAL = 0x5A
    """Comando 0x5A - Solicita estado parcial da central (devuelve 43 bytes)."""
    
    STATUS_REQUEST = 0x5B
    """Comando 0x5B - Solicita status completo da central (devuelve 54 bytes)."""


class PGMAction(IntEnum):
    """Ações para controle de PGM."""
    
    TURN_ON = 0x4C
    """Liga a PGM (0x4C = 'L')."""
    
    TURN_OFF = 0x44
    """Desliga a PGM (0x44 = 'D')."""


class PGMOutput(IntEnum):
    """Direccións de salida PGM (1 a 19)."""
    
    PGM_1 = 0x31
    PGM_2 = 0x32
    PGM_3 = 0x33
    PGM_4 = 0x34
    PGM_5 = 0x35
    PGM_6 = 0x36
    PGM_7 = 0x37
    PGM_8 = 0x38
    PGM_9 = 0x39
    PGM_10 = 0x3A
    PGM_11 = 0x3B
    PGM_12 = 0x3C
    PGM_13 = 0x3D
    PGM_14 = 0x3E
    PGM_15 = 0x3F
    PGM_16 = 0x40
    PGM_17 = 0x41
    PGM_18 = 0x42
    PGM_19 = 0x43
    
    @classmethod
    def from_number(cls, num: int) -> "PGMOutput":
        """Convierte número da PGM (1-19) para o enum.
        
        Args:
            num: Número da PGM (1-19).
            
        Returns:
            Valor do enum correspdondente.
            
        Raises:
            ValueError: Si o número estiver fora do range válido.
        """
        if num < 1 or num > 19:
            raise ValueError(f"Número de PGM inválido: {num}. Deve ser entre 1 e 19.")
        return cls(0x30 + num)


class PartitionCode(IntEnum):
    """Códigos de partición para comando de activación."""
    
    ALL = 0x00
    """Ativa todas las particiones (NULL - sem sub-comando)."""
    
    PARTITION_A = 0x41
    """Ativa partición A."""
    
    PARTITION_B = 0x42
    """Ativa partición B."""
    
    PARTITION_C = 0x43
    """Ativa partición C."""
    
    PARTITION_D = 0x44
    """Ativa partición D."""
    
    STAY_MODE = 0x50
    """Ativa no modo Stay."""


# =============================================================================
# Respostas ISECMobile
# =============================================================================

class ResponseCode(IntEnum):
    """Códigos de respuesta ISECMobile."""
    
    # ACK - Sucesso
    ACK = 0xFE
    """Comando recibido e executado com éxito."""
    
    # NACK - Erros
    NACK_INVALID_PACKET = 0xE0
    """Formato de pacote inválido."""
    
    NACK_WRONG_PASSWORD = 0xE1
    """Contraseña incorreta."""
    
    NACK_INVALID_COMMAND = 0xE2
    """Comando inválido."""
    
    NACK_NOT_PARTITIONED = 0xE3
    """Central no particionada."""
    
    NACK_ZONES_OPEN = 0xE4
    """Zonas abertas."""
    
    NACK_DISCONTINUED = 0xE5
    """Comando descontinuado."""
    
    NACK_NO_BYPASS_PERMISSION = 0xE6
    """Usuário sem permissão para bypass."""
    
    NACK_NO_DEACTIVATE_PERMISSION = 0xE7
    """Usuário sem permissão para desarmar."""
    
    NACK_BYPASS_NOT_ALLOWED = 0xE8
    """Bypass no permitido com a central ativada."""
    
    NACK_NO_ZONES_IN_PARTITION = 0xEA
    """Partición sem zonas habilitadas."""


# =============================================================================
# Mapeo de mensajes de error
# =============================================================================

RESPONSE_MESSAGES: dict[int, str] = {
    ResponseCode.ACK: "Comando executado com éxito",
    ResponseCode.NACK_INVALID_PACKET: "Formato de pacote inválido",
    ResponseCode.NACK_WRONG_PASSWORD: "Contraseña incorreta",
    ResponseCode.NACK_INVALID_COMMAND: "Comando inválido",
    ResponseCode.NACK_NOT_PARTITIONED: "Central no particionada",
    ResponseCode.NACK_ZONES_OPEN: "Zonas abertas",
    ResponseCode.NACK_DISCONTINUED: "Comando descontinuado",
    ResponseCode.NACK_NO_BYPASS_PERMISSION: "Usuário sem permissão para bypass",
    ResponseCode.NACK_NO_DEACTIVATE_PERMISSION: "Usuário sem permissão para desarmar",
    ResponseCode.NACK_BYPASS_NOT_ALLOWED: "Bypass no permitido com a central ativada",
    ResponseCode.NACK_NO_ZONES_IN_PARTITION: "Partición sem zonas habilitadas",
}


def is_ack(response_code: int) -> bool:
    """Verifica si o código de respuesta é ACK (éxito).
    
    Args:
        response_code: Código de respuesta recibido.
        
    Returns:
        True se for ACK, False de lo contrario.
    """
    return response_code == ResponseCode.ACK


def is_nack(response_code: int) -> bool:
    """Verifica si o código de respuesta é NACK (error).
    
    Args:
        response_code: Código de respuesta recibido.
        
    Returns:
        True se for NACK, False de lo contrario.
    """
    return 0xE0 <= response_code <= 0xEA


def get_response_message(response_code: int) -> str:
    """Obtiene a mensaje descriptiva para um código de respuesta.
    
    Args:
        response_code: Código de respuesta recibido.
        
    Returns:
        Mensagem descriptiva do código ou "Código desconocido".
    """
    return RESPONSE_MESSAGES.get(response_code, f"Código desconocido: 0x{response_code:02X}")


# =============================================================================
# Modelos de Centrais
# =============================================================================

class CentralModel(IntEnum):
    """Modelos de centrais de alarme Intelbras."""
    
    AMT_2018_E = 0x1E
    """AMT 2018 E/EG - Central de alarme monitorada."""
    
    AMT_4010 = 0x41
    """AMT 4010 - Central de alarme monitorada."""
    
    @classmethod
    def get_name(cls, model_code: int) -> str:
        """Devuelve o nome do modelo.
        
        Args:
            model_code: Código do modelo (hex).
            
        Returns:
            Nome do modelo ou código hex se desconocido.
        """
        model_names = {
            cls.AMT_2018_E: "AMT 2018 E/EG",
            cls.AMT_4010: "AMT 4010",
        }
        return model_names.get(model_code, f"0x{model_code:02X}")

