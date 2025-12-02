"""WebSocket server for remote control connections.

This module provides an async WebSocket server that handles multiple client
connections, broadcasts telemetry at configurable rates, and receives
control inputs from connected clients.
"""

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import websockets
from websockets.asyncio.server import Server, ServerConnection

from airborne.core.logging_system import get_logger
from airborne.plugins.network.protocol import (
    VALID_ACTIONS,
    ActionCommand,
    ClientConfig,
    ControlInput,
    MessageType,
    ProtocolMessage,
    ServerStatus,
    TelemetryData,
)

logger = get_logger(__name__)


@dataclass
class ClientSession:
    """Represents a connected client session."""

    websocket: ServerConnection
    client_id: str
    client_name: str = ""
    telemetry_rate_ms: int = 50  # Default 50ms = 20 Hz
    last_telemetry_time: float = 0.0
    connected_at: float = field(default_factory=time.time)

    def should_send_telemetry(self, current_time: float) -> bool:
        """Check if it's time to send telemetry to this client.

        Args:
            current_time: Current timestamp.

        Returns:
            True if telemetry should be sent.
        """
        elapsed_ms = (current_time - self.last_telemetry_time) * 1000
        return elapsed_ms >= self.telemetry_rate_ms


class RemoteControlServer:
    """Async WebSocket server for remote aircraft control.

    Handles multiple client connections, broadcasts telemetry at per-client
    configurable rates, and processes incoming control commands.
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 51128,
        on_control_input: Callable[[ControlInput], None] | None = None,
        on_action: Callable[[ActionCommand], None] | None = None,
    ) -> None:
        """Initialize the WebSocket server.

        Args:
            host: Host address to bind to.
            port: Port number to listen on.
            on_control_input: Callback for control input messages.
            on_action: Callback for action command messages.
        """
        self.host = host
        self.port = port
        self.on_control_input = on_control_input
        self.on_action = on_action

        # Connected clients
        self._clients: dict[str, ClientSession] = {}
        self._client_counter = 0

        # Server instance
        self._server: Server | None = None
        self._running = False

        # Current telemetry data (updated externally)
        self._current_telemetry: TelemetryData | None = None

        # Server info
        self._aircraft_name: str = ""
        self._paused: bool = False

        # Async lock for thread-safe client access
        self._clients_lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the WebSocket server."""
        if self._running:
            logger.warning("Server already running")
            return

        self._running = True
        logger.info(f"Starting WebSocket server on {self.host}:{self.port}")

        try:
            self._server = await websockets.serve(
                self._handle_connection,
                self.host,
                self.port,
                ping_interval=20,
                ping_timeout=30,
            )
            logger.info(f"WebSocket server listening on ws://{self.host}:{self.port}")
        except OSError as e:
            logger.error(f"Failed to start WebSocket server: {e}")
            self._running = False
            raise

    async def stop(self) -> None:
        """Stop the WebSocket server and disconnect all clients."""
        if not self._running:
            return

        logger.info("Stopping WebSocket server...")
        self._running = False

        # Close all client connections
        async with self._clients_lock:
            for session in list(self._clients.values()):
                try:
                    await session.websocket.close(1001, "Server shutting down")
                except Exception as e:
                    logger.debug(f"Error closing client {session.client_id}: {e}")
            self._clients.clear()

        # Close server
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        logger.info("WebSocket server stopped")

    async def _handle_connection(self, websocket: ServerConnection) -> None:
        """Handle a new client connection.

        Args:
            websocket: The WebSocket connection.
        """
        # Generate client ID
        self._client_counter += 1
        client_id = f"client_{self._client_counter}"

        # Create session
        session = ClientSession(
            websocket=websocket,
            client_id=client_id,
        )

        async with self._clients_lock:
            self._clients[client_id] = session

        remote_addr = websocket.remote_address
        logger.info(f"Client connected: {client_id} from {remote_addr}")

        # Send welcome status message
        try:
            status = ServerStatus(
                connected_clients=len(self._clients),
                server_version="1.0.0",
                simulation_paused=self._paused,
                aircraft_name=self._aircraft_name,
            )
            await websocket.send(ProtocolMessage.encode_status(status))
        except Exception as e:
            logger.error(f"Error sending welcome message to {client_id}: {e}")

        try:
            async for message in websocket:
                await self._handle_message(session, message)
        except websockets.exceptions.ConnectionClosed as e:
            logger.info(f"Client {client_id} disconnected: {e.code} {e.reason}")
        except Exception as e:
            logger.error(f"Error handling client {client_id}: {e}")
        finally:
            async with self._clients_lock:
                self._clients.pop(client_id, None)
            logger.info(f"Client {client_id} removed, {len(self._clients)} clients remaining")

    async def _handle_message(self, session: ClientSession, raw_message: str | bytes) -> None:
        """Handle incoming message from client.

        Args:
            session: Client session.
            raw_message: Raw message string.
        """
        if isinstance(raw_message, bytes):
            raw_message = raw_message.decode("utf-8")

        try:
            msg_type, data = ProtocolMessage.decode(raw_message)
        except ValueError as e:
            logger.warning(f"Invalid message from {session.client_id}: {e}")
            error_msg = ProtocolMessage.encode_error(str(e), "invalid_message")
            await session.websocket.send(error_msg)
            return

        if msg_type == MessageType.CONTROL:
            self._handle_control(session, data)
        elif msg_type == MessageType.ACTION:
            self._handle_action(session, data)
        elif msg_type == MessageType.CONFIG:
            await self._handle_config(session, data)
        else:
            logger.debug(f"Ignoring message type {msg_type} from {session.client_id}")

    def _handle_control(self, session: ClientSession, data: dict[str, Any]) -> None:
        """Handle control input message.

        Args:
            session: Client session.
            data: Control data dictionary.
        """
        control = ControlInput.from_dict(data)

        if self.on_control_input:
            self.on_control_input(control)

        logger.debug(
            f"Control from {session.client_id}: "
            f"pitch={control.pitch}, roll={control.roll}, "
            f"throttle={control.throttle}"
        )

    def _handle_action(self, session: ClientSession, data: dict[str, Any]) -> None:
        """Handle action command message.

        Args:
            session: Client session.
            data: Action data dictionary.
        """
        action = ActionCommand.from_dict(data)

        # Validate action name
        if action.action not in VALID_ACTIONS:
            logger.warning(f"Unknown action '{action.action}' from {session.client_id}")
            return

        if self.on_action:
            self.on_action(action)

        logger.debug(f"Action from {session.client_id}: {action.action} ({action.value})")

    async def _handle_config(self, session: ClientSession, data: dict[str, Any]) -> None:
        """Handle client configuration message.

        Args:
            session: Client session.
            data: Config data dictionary.
        """
        config = ClientConfig.from_dict(data)

        # Validate telemetry rate (minimum 10ms, maximum 1000ms)
        rate = max(10, min(1000, config.telemetry_rate_ms))
        session.telemetry_rate_ms = rate
        session.client_name = config.client_name

        logger.info(
            f"Client {session.client_id} config updated: rate={rate}ms, name='{config.client_name}'"
        )

        # Send confirmation status
        status = ServerStatus(
            connected_clients=len(self._clients),
            server_version="1.0.0",
            simulation_paused=self._paused,
            aircraft_name=self._aircraft_name,
        )
        await session.websocket.send(ProtocolMessage.encode_status(status))

    def update_telemetry(self, telemetry: TelemetryData) -> None:
        """Update current telemetry data.

        This is called from the main thread to update the telemetry that
        will be broadcast to clients.

        Args:
            telemetry: Current telemetry data.
        """
        self._current_telemetry = telemetry

    async def broadcast_telemetry(self) -> None:
        """Broadcast telemetry to all clients that need updates.

        This should be called periodically from the async event loop.
        """
        if not self._current_telemetry:
            return

        current_time = time.time()
        telemetry_json = ProtocolMessage.encode_telemetry(self._current_telemetry)

        async with self._clients_lock:
            for session in list(self._clients.values()):
                if session.should_send_telemetry(current_time):
                    try:
                        await session.websocket.send(telemetry_json)
                        session.last_telemetry_time = current_time
                    except websockets.exceptions.ConnectionClosed:
                        logger.debug(f"Client {session.client_id} disconnected during broadcast")
                    except Exception as e:
                        logger.error(f"Error sending telemetry to {session.client_id}: {e}")

    def set_aircraft_name(self, name: str) -> None:
        """Set the aircraft name for status messages.

        Args:
            name: Aircraft name.
        """
        self._aircraft_name = name

    def set_paused(self, paused: bool) -> None:
        """Set simulation paused state.

        Args:
            paused: Whether simulation is paused.
        """
        self._paused = paused

    @property
    def client_count(self) -> int:
        """Get number of connected clients."""
        return len(self._clients)

    @property
    def is_running(self) -> bool:
        """Check if server is running."""
        return self._running
