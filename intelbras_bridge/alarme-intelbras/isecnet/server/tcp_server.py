"""Servidor TCP para comunicación com central AMT.

Este servidor escuta conexiones da central de alarma Intelbras AMT 2018 / 4010.
A central inicia a conexión TCP (nós somos o server).

Características:
    - Porta predeterminado: 9009
    - Baseado em asyncio
    - Suporta múltiplas conexiones
    - Timeout de respuesta: 8 segundos
"""

import asyncio
import logging
from typing import Callable, Awaitable
from dataclasses import dataclass, field

from ..const import DEFAULT_PORT, RESPONSE_TIMEOUT
from ..protocol.isecnet import ISECNetFrame, ISECNetFrameReader
from ..protocol.responses import Response
from ..protocol.commands.connection import ConnectionInfo, CONNECTION_INFO_COMMAND
from .connection_manager import ConnectionManager, AMTConnection


logger = logging.getLogger(__name__)


# Tipo para callbacks de frames recibidos
FrameCallback = Callable[[AMTConnection, ISECNetFrame], Awaitable[None]]

# Tipo para callbacks de conexión
ConnectionCallback = Callable[[AMTConnection], Awaitable[None]]


@dataclass
class AMTServerConfig:
    """Configuraciones do servidor AMT.
    
    Attributes:
        host: Dirección IP para bind (predeterminado: todos los interfaces).
        port: Porta TCP para escutar.
        response_timeout: Timeout em segundos para respuestas.
        auto_ack_heartbeat: Si True, respdonde automaticamente aos heartbeats.
        auto_ack_connection: Si True, respdonde automaticamente ao comando 0x94.
    """
    
    host: str = "0.0.0.0"
    port: int = DEFAULT_PORT
    response_timeout: float = RESPONSE_TIMEOUT
    auto_ack_heartbeat: bool = True
    auto_ack_connection: bool = True


class AMTServer:
    """Servidor TCP para comunicación com centrais AMT.
    
    Este servidor aceita conexiones de centrais de alarme e gerencia
    a comunicación bidirecional via protocolo ISECNet/ISECMobile.
    
    Example:
        ```python
        server = AMTServer()
        
        @server.on_frame
        async def handle_frame(conn, frame):
            print(f"Frame recibido de {conn.address}: {frame}")
        
        await server.start()
        ```
    """

    def __init__(self, config: AMTServerConfig | None = None) -> None:
        """Inicializa el servidor.
        
        Args:
            config: Configuraciones do servidor (usa predeterminados se None).
        """
        self._config = config or AMTServerConfig()
        self._server: asyncio.Server | None = None
        self._connection_manager = ConnectionManager()
        
        # Callbacks
        self._frame_callbacks: list[FrameCallback] = []
        self._connect_callbacks: list[ConnectionCallback] = []
        self._disconnect_callbacks: list[ConnectionCallback] = []
        
        # Estado
        self._running = False

    @property
    def config(self) -> AMTServerConfig:
        """Configuraciones do servidor."""
        return self._config

    @property
    def connections(self) -> ConnectionManager:
        """Gerenciador de conexiones."""
        return self._connection_manager

    @property
    def is_running(self) -> bool:
        """Verifica si o servidor está rodando."""
        return self._running

    def on_frame(self, callback: FrameCallback) -> FrameCallback:
        """Decorator para registrar callback de frames recibidos.
        
        Args:
            callback: Função async(connection, frame) a ser chamada.
            
        Returns:
            A própria função callback.
        """
        self._frame_callbacks.append(callback)
        return callback

    def on_connect(self, callback: ConnectionCallback) -> ConnectionCallback:
        """Decorator para registrar callback de nova conexión.
        
        Args:
            callback: Função async(connection) a ser chamada.
            
        Returns:
            A própria função callback.
        """
        self._connect_callbacks.append(callback)
        return callback

    def on_disconnect(self, callback: ConnectionCallback) -> ConnectionCallback:
        """Decorator para registrar callback de desconexión.
        
        Args:
            callback: Função async(connection) a ser chamada.
            
        Returns:
            A própria função callback.
        """
        self._disconnect_callbacks.append(callback)
        return callback

    async def start(self) -> None:
        """Inicia o servidor TCP.
        
        Raises:
            RuntimeError: Si o servidor já estiver rodando.
        """
        if self._running:
            raise RuntimeError("Servidor já está rodando")
        
        self._server = await asyncio.start_server(
            self._handle_client,
            self._config.host,
            self._config.port,
            reuse_address=True,
        )
        
        self._running = True
        
        addrs = ', '.join(str(sock.getsockname()) for sock in self._server.sockets)
        logger.debug(f"Servidor AMT iniciado em {addrs}")

    async def stop(self) -> None:
        """Para o servidor TCP."""
        if not self._running:
            return
        
        self._running = False
        
        # Fecha todas las conexiones
        await self._connection_manager.close_all()
        
        # Para o servidor
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        
        logger.info("Servidor AMT parado")

    async def serve_forever(self) -> None:
        """Roda o servidor indefinidamente.
        
        Bloqueia até o servidor ser parado.
        """
        if not self._server:
            await self.start()
        
        if self._server:
            async with self._server:
                await self._server.serve_forever()

    async def send_command(
        self,
        connection_id: str,
        frame: ISECNetFrame,
        wait_response: bool = True,
    ) -> Response | None:
        """Envia um comando para uma central específica.
        
        Args:
            connection_id: ID da conexión (dirección IP:porta).
            frame: Frame ISECNet a ser enviado.
            wait_response: Si deve esperar respuesta.
            
        Returns:
            Response se wait_response=True e respuesta recebida, Nonede lo contrario.
            
        Raises:
            ValueError: Si a conexión no existir.
            TimeoutError: Si timeout esperando respuesta.
        """
        connection = self._connection_manager.get(connection_id)
        if not connection:
            raise ValueError(f"Conexión no encontrada: {connection_id}")
        
        return await self._send_and_wait(connection, frame, wait_response)

    async def broadcast_command(
        self,
        frame: ISECNetFrame,
        wait_response: bool = False,
    ) -> dict[str, Response | None]:
        """Envia um comando para todas las centrais conectadas.
        
        Args:
            frame: Frame ISECNet a ser enviado.
            wait_response: Si deve esperar respuesta de cada central.
            
        Returns:
            Dicionário {connection_id: Response ou None}.
        """
        results: dict[str, Response | None] = {}
        
        for conn_id, connection in self._connection_manager.all().items():
            try:
                results[conn_id] = await self._send_and_wait(
                    connection, frame, wait_response
                )
            except Exception as e:
                logger.error(f"Erro ao enviar para {conn_id}: {e}")
                results[conn_id] = None
        
        return results

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handler para nova conexión de cliente.
        
        Args:
            reader: Stream de leitura.
            writer: Stream de escrita.
        """
        addr = writer.get_extra_info('peername')
        connection_id = f"{addr[0]}:{addr[1]}"
        
        connection = AMTConnection(
            id=connection_id,
            address=addr,
            reader=reader,
            writer=writer,
        )
        
        self._connection_manager.add(connection)
        logger.info(f"Nova conexión de {connection_id}")
        
        # Notifica callbacks de conexión
        for callback in self._connect_callbacks:
            try:
                await callback(connection)
            except Exception as e:
                logger.error(f"Erro em callback de conexión: {e}")
        
        # Processa datos da conexión
        frame_reader = ISECNetFrameReader()
        
        try:
            while not reader.at_eof():
                data = await reader.read(1024)
                if not data:
                    break
                
                logger.debug(f"Datos brutos de {connection_id}: {data.hex(' ')}")
                frames = frame_reader.feed(data)
                
                # Log se hay bytes pendentes no buffer
                if frame_reader.pending_bytes > 0:
                    logger.debug(f"Bytes pendentes no buffer: {frame_reader.pending_bytes}")
                
                # Log se hay respuesta pendente esperando
                if connection.pending_response:
                    logger.debug(f"Há respuesta pendente esperando frame...")
                
                if not frames:
                    logger.debug(f"Nenhum frame completo extraído de {len(data)} bytes recibidos")
                
                for frame in frames:
                    logger.debug(f"Frame recibido de {connection_id}: {frame}")
                    
                    # Flags para controlar se o frame deve preencher pending_response
                    is_auto_handled = False
                    
                    # Trata heartbeat automaticamente se configurado
                    if frame.is_heartbeat and self._config.auto_ack_heartbeat:
                        await self._handle_heartbeat(connection, frame)
                        is_auto_handled = True
                        # Continua para notificar callbacks (para contagem, etc)
                    
                    # Trata comando de identificação (0x94) automaticamente
                    if frame.command == CONNECTION_INFO_COMMAND and self._config.auto_ack_connection:
                        await self._handle_connection_info(connection, frame)
                        is_auto_handled = True
                        # Continua para notificar callbacks também
                    
                    # Verifica si hay respuesta pendente
                    # IMPORTANTE: Heartbeats e comandos auto-tratados NÃO preenchem pending_response
                    if connection.pending_response and not is_auto_handled:
                        logger.debug(
                            f"Preenchendo respuesta pendente de {connection_id} com frame: "
                            f"command=0x{frame.command:02X}, content={frame.content.hex(' ')}"
                        )
                        if not connection.pending_response.done():
                            connection.pending_response.set_result(frame)
                            connection.pending_response = None
                        else:
                            logger.warning(
                                f"Intentativa de preencher pending_response já concluído para {connection_id}"
                            )
                    elif not is_auto_handled:
                        # Notifica callbacks de frame (apenas se no fue auto-tratado)
                        for callback in self._frame_callbacks:
                            try:
                                await callback(connection, frame)
                            except Exception as e:
                                logger.error(f"Erro em callback de frame: {e}")
        
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Erro na conexión {connection_id}: {e}")
        finally:
            # Cleanup
            self._connection_manager.remove(connection_id)
            
            # Notifica callbacks de desconexión
            for callback in self._disconnect_callbacks:
                try:
                    await callback(connection)
                except Exception as e:
                    logger.error(f"Erro em callback de desconexión: {e}")
            
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            
            logger.info(f"Conexión encerrada: {connection_id}")

    async def _handle_heartbeat(
        self,
        connection: AMTConnection,
        frame: ISECNetFrame,
    ) -> None:
        """Respdonde a um heartbeat da central.
        
        Args:
            connection: Conexión que enviou o heartbeat.
            frame: Frame de heartbeat recibido.
        """
        logger.debug(f"Heartbeat recibido de {connection.id}, enviando ACK")
        
        # Cria e envia respuesta ACK simples (frame curto)
        ack_frame = ISECNetFrame.create_simple_ack()
        ack_data = ack_frame.build()
        
        logger.debug(f"ACK heartbeat: {ack_data.hex(' ')}")
        connection.writer.write(ack_data)
        await connection.writer.drain()
        
        # Atualiza timestamp do último heartbeat
        connection.metadata["last_heartbeat"] = asyncio.get_event_loop().time()

    async def _handle_connection_info(
        self,
        connection: AMTConnection,
        frame: ISECNetFrame,
    ) -> None:
        """Processa e respdonde ao comando de identificação (0x94).
        
        A central envía este comando logo após conectar para se identificar.
        
        Args:
            connection: Conexión que enviou o comando.
            frame: Frame 0x94 recibido.
        """
        # Parseia as informações
        info = ConnectionInfo.try_parse(frame.content)
        
        if info:
            logger.info(
                f"Central identificada: Conta={info.account}, "
                f"Canal={info.channel.name_pt}, MAC=...{info.mac_suffix}"
            )
            
            # Salva nos metadatos da conexión
            connection.metadata["account"] = info.account
            connection.metadata["channel"] = info.channel.name
            connection.metadata["mac_suffix"] = info.mac_suffix
            connection.metadata["connection_info"] = info
        else:
            logger.warning(f"No fue posible analizar comando 0x94: {frame.content.hex()}")
        
        # Envia ACK simples (frame curto)
        ack_frame = ISECNetFrame.create_simple_ack()
        ack_data = ack_frame.build()
        
        logger.debug(f"ACK para 0x94: {ack_data.hex(' ')}")
        connection.writer.write(ack_data)
        await connection.writer.drain()

    async def _send_and_wait(
        self,
        connection: AMTConnection,
        frame: ISECNetFrame,
        wait_response: bool,
    ) -> Response | None:
        """Envia frame e opcionalmente espera respuesta.
        
        Args:
            connection: Conexión para enviar.
            frame: Frame a ser enviado.
            wait_response: Si deve esperar respuesta.
            
        Returns:
            Response ou None.
            
        Raises:
            TimeoutError: Si timeout esperando respuesta.
        """
        data = frame.build()
        
        if wait_response:
            # Prepara para esperar respuesta
            connection.pending_response = asyncio.get_event_loop().create_future()
            logger.debug(f"Criado pending_response para {connection.id}, esperando respuesta...")
        
        # Envia datos
        connection.writer.write(data)
        await connection.writer.drain()
        
        logger.debug(f"Enviado para {connection.id}: {data.hex(' ')}")
        
        if not wait_response:
            return None
        
        # Espera respuesta com timeout
        try:
            logger.debug(f"Esperando respuesta de {connection.id} (timeout: {self._config.response_timeout}s)...")
            response_frame = await asyncio.wait_for(
                connection.pending_response,
                timeout=self._config.response_timeout,
            )
            logger.debug(f"Resposta recebida de {connection.id}: {response_frame}")
            return Response.from_isecnet_frame(response_frame)
        except asyncio.TimeoutError:
            logger.warning(
                f"Timeout esperando respuesta de {connection.id} "
                f"({self._config.response_timeout}s). "
                f"pending_response ainda existe: {connection.pending_response is not None}"
            )
            connection.pending_response = None
            raise TimeoutError(
                f"Timeout esperando respuesta de {connection.id} "
                f"({self._config.response_timeout}s)"
            )

    async def __aenter__(self) -> "AMTServer":
        """Context manager: inicia servidor."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager: para servidor."""
        await self.stop()

