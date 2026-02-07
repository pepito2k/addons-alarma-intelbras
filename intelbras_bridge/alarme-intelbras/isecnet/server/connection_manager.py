"""Gerenciador de conexiones com centrais AMT.

Mantém o registro de todas las conexiones ativas e permite
enviar comandos para centrais específicas ou todas ao mesmo tempo.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


logger = logging.getLogger(__name__)


@dataclass
class AMTConnection:
    """Representa una conexión com uma central AMT.
    
    Attributes:
        id: Identificador único da conexión (IP:porta).
        address: Tupla (host, port) do dirección remoto.
        reader: StreamReader asyncio para leitura.
        writer: StreamWriter asyncio para escrita.
        connected_at: Timestamp da conexión.
        pending_response: Future esperando respuesta.
        metadata: Datos adicionais da conexión.
    """
    
    id: str
    address: tuple[str, int]
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    connected_at: datetime = field(default_factory=datetime.now)
    pending_response: asyncio.Future | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def host(self) -> str:
        """Dirección IP da central."""
        return self.address[0]

    @property
    def port(self) -> int:
        """Porta da conexión."""
        return self.address[1]

    @property
    def is_connected(self) -> bool:
        """Verifica si a conexión está ativa."""
        return not self.writer.is_closing()

    async def close(self) -> None:
        """Fecha a conexión."""
        if not self.writer.is_closing():
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception:
                pass

    def __repr__(self) -> str:
        return f"AMTConnection(id='{self.id}', connected_at={self.connected_at})"


class ConnectionManager:
    """Gerencia múltiplas conexiones de centrais AMT.
    
    Permite registrar, buscar e remover conexiones, y además de
    manter estatísticas de uso.
    
    Example:
        ```python
        manager = ConnectionManager()
        
        # Adicionar conexión
        manager.add(connection)
        
        # Buscar conexión
        conn = manager.get("192.168.1.100:12345")
        
        # Listar todas
        for conn_id, conn in manager.all().items():
            print(f"{conn_id}: {conn.host}")
        ```
    """

    def __init__(self) -> None:
        """Inicializa el gerenciador de conexiones."""
        self._connections: dict[str, AMTConnection] = {}
        self._lock = asyncio.Lock()

    @property
    def count(self) -> int:
        """Número de conexiones ativas."""
        return len(self._connections)

    def add(self, connection: AMTConnection) -> None:
        """Adiciona uma nova conexión.
        
        Args:
            connection: Conexión a ser adicionada.
        """
        self._connections[connection.id] = connection
        logger.debug(f"Conexión adicionada: {connection.id}")

    def remove(self, connection_id: str) -> AMTConnection | None:
        """Remove uma conexión pelo ID.
        
        Args:
            connection_id: ID da conexión a remover.
            
        Returns:
            Conexión removida ou None se no existir.
        """
        connection = self._connections.pop(connection_id, None)
        if connection:
            logger.debug(f"Conexión removida: {connection_id}")
        return connection

    def get(self, connection_id: str) -> AMTConnection | None:
        """Busca uma conexión pelo ID.
        
        Args:
            connection_id: ID da conexión.
            
        Returns:
            Conexión ou None se no existir.
        """
        return self._connections.get(connection_id)

    def get_by_host(self, host: str) -> AMTConnection | None:
        """Busca uma conexión pelo dirección IP.
        
        Útil quando você sabe o IP da central mas no a porta.
        Devuelve a primeira conexión encontrada para o host.
        
        Args:
            host: Dirección IP da central.
            
        Returns:
            Conexión ou None se no existir.
        """
        for connection in self._connections.values():
            if connection.host == host:
                return connection
        return None

    def all(self) -> dict[str, AMTConnection]:
        """Devuelve todas las conexiones.
        
        Returns:
            Dicionário {id: connection}.
        """
        return self._connections.copy()

    def list_hosts(self) -> list[str]:
        """Lista los direccións IP de todas las conexiones.
        
        Returns:
            Lista de IPs conectados.
        """
        return [conn.host for conn in self._connections.values()]

    def has_connection(self, connection_id: str) -> bool:
        """Verifica si uma conexión existe.
        
        Args:
            connection_id: ID da conexión.
            
        Returns:
            True se existir.
        """
        return connection_id in self._connections

    def has_host(self, host: str) -> bool:
        """Verifica si hay conexión com um host específico.
        
        Args:
            host: Dirección IP.
            
        Returns:
            True se existir conexión.
        """
        return any(conn.host == host for conn in self._connections.values())

    async def close_all(self) -> None:
        """Fecha todas las conexiones."""
        async with self._lock:
            for connection in list(self._connections.values()):
                try:
                    await connection.close()
                except Exception as e:
                    logger.error(f"Erro ao fechar conexión {connection.id}: {e}")
            self._connections.clear()
        logger.info("Todas as conexiones fechadas")

    async def close_connection(self, connection_id: str) -> bool:
        """Fecha uma conexión específica.
        
        Args:
            connection_id: ID da conexión.
            
        Returns:
            True se a conexión fue fechada.
        """
        connection = self.get(connection_id)
        if not connection:
            return False
        
        try:
            await connection.close()
            self.remove(connection_id)
            return True
        except Exception as e:
            logger.error(f"Erro ao fechar conexión {connection_id}: {e}")
            return False

    def get_stats(self) -> dict[str, Any]:
        """Devuelve estatísticas do gerenciador.
        
        Returns:
            Dicionário com estatísticas.
        """
        return {
            "total_connections": self.count,
            "hosts": self.list_hosts(),
            "connections": [
                {
                    "id": conn.id,
                    "host": conn.host,
                    "port": conn.port,
                    "connected_at": conn.connected_at.isoformat(),
                    "is_connected": conn.is_connected,
                }
                for conn in self._connections.values()
            ],
        }

    def __len__(self) -> int:
        """Devuelve o número de conexiones."""
        return self.count

    def __contains__(self, connection_id: str) -> bool:
        """Verifica si uma conexión existe."""
        return self.has_connection(connection_id)

    def __iter__(self):
        """Itera sobre as conexiones."""
        return iter(self._connections.values())

    def __repr__(self) -> str:
        return f"ConnectionManager(connections={self.count})"

