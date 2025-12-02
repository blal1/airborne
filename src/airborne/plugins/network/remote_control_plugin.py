"""Remote Control Plugin for Airborne Flight Simulator.

This plugin provides a WebSocket server (port 51128) that allows external
clients to receive aircraft telemetry and send control inputs for debugging
and automation purposes.

Features:
- Full telemetry broadcast at configurable per-client rates
- Multiple simultaneous client connections
- Complete control input support (axes + discrete actions)
- JSON message protocol
"""

import asyncio
import threading
from typing import Any

from airborne.core.input import InputAction
from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessagePriority, MessageTopic
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType
from airborne.plugins.network.protocol import ActionCommand, ControlInput
from airborne.plugins.network.telemetry_collector import TelemetryCollector
from airborne.plugins.network.websocket_server import RemoteControlServer

logger = get_logger(__name__)


class RemoteControlPlugin(IPlugin):
    """Plugin that provides WebSocket-based remote control interface.

    This plugin runs a WebSocket server that broadcasts telemetry to connected
    clients and accepts control inputs. It integrates with the input system
    via the message queue.
    """

    def __init__(self) -> None:
        """Initialize the remote control plugin."""
        self.context: PluginContext | None = None
        self.server: RemoteControlServer | None = None
        self.telemetry_collector: TelemetryCollector | None = None

        # Async event loop running in background thread
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._running = False

        # Control state (accumulated from remote clients)
        self._remote_pitch: float | None = None
        self._remote_roll: float | None = None
        self._remote_yaw: float | None = None
        self._remote_throttle: float | None = None
        self._remote_brakes: float | None = None
        self._remote_pitch_trim: float | None = None
        self._remote_rudder_trim: float | None = None

        # Lock for thread-safe control state access
        self._control_lock = threading.Lock()

        # Broadcast task
        self._broadcast_task: asyncio.Task | None = None

    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return PluginMetadata(
            name="remote_control",
            version="1.0.0",
            author="AirBorne Team",
            plugin_type=PluginType.NETWORK,
            dependencies=[],
            provides=["remote_control", "telemetry_stream"],
            optional=True,
            update_priority=200,  # Update after physics/systems
            requires_physics=False,
            requires_network=True,
            description="WebSocket server for remote aircraft control and telemetry",
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize the plugin.

        Args:
            context: Plugin context with access to core systems.
        """
        self.context = context

        # Get configuration
        config = context.config.get("remote_control", {})
        host = config.get("host", "0.0.0.0")
        port = config.get("port", 51128)

        # Create telemetry collector
        self.telemetry_collector = TelemetryCollector()

        # Create WebSocket server
        self.server = RemoteControlServer(
            host=host,
            port=port,
            on_control_input=self._handle_control_input,
            on_action=self._handle_action,
        )

        # Set aircraft name from config
        aircraft_name = context.config.get("name", "Unknown Aircraft")
        self.server.set_aircraft_name(aircraft_name)

        # Subscribe to messages for telemetry collection
        self._subscribe_to_messages()

        # Start async event loop in background thread
        self._start_async_loop()

        logger.info(f"Remote control plugin initialized (ws://{host}:{port})")

    def _subscribe_to_messages(self) -> None:
        """Subscribe to messages for telemetry collection."""
        if not self.context:
            return

        mq = self.context.message_queue

        # Position and flight state
        mq.subscribe(MessageTopic.POSITION_UPDATED, self._on_telemetry_message)

        # Engine state
        mq.subscribe(MessageTopic.ENGINE_STATE, self._on_telemetry_message)

        # Electrical system
        mq.subscribe(MessageTopic.ELECTRICAL_STATE, self._on_telemetry_message)

        # Fuel system
        mq.subscribe(MessageTopic.FUEL_STATE, self._on_telemetry_message)

        # Control inputs
        mq.subscribe(MessageTopic.CONTROL_INPUT, self._on_telemetry_message)

        # Terrain elevation for AGL
        mq.subscribe(MessageTopic.TERRAIN_UPDATED, self._on_telemetry_message)

        # Parking brake
        mq.subscribe("parking_brake", self._on_telemetry_message)

    def _on_telemetry_message(self, message: Message) -> None:
        """Handle telemetry-related messages.

        Args:
            message: Message from the queue.
        """
        if self.telemetry_collector:
            self.telemetry_collector.handle_message(message)

    def _start_async_loop(self) -> None:
        """Start the async event loop in a background thread."""
        self._running = True
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_async_loop, daemon=True)
        self._thread.start()

    def _run_async_loop(self) -> None:
        """Run the async event loop (called from background thread)."""
        if not self._loop:
            return

        asyncio.set_event_loop(self._loop)

        try:
            # Start server and broadcast loop
            self._loop.run_until_complete(self._async_main())
        except Exception as e:
            logger.error(f"Async loop error: {e}")
        finally:
            self._loop.close()

    async def _async_main(self) -> None:
        """Main async coroutine that runs server and broadcast loop."""
        if not self.server:
            return

        # Start server
        await self.server.start()

        # Start broadcast loop
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())

        # Wait until stopped
        while self._running:
            await asyncio.sleep(0.1)

        # Cleanup
        if self._broadcast_task:
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass

        await self.server.stop()

    async def _broadcast_loop(self) -> None:
        """Broadcast telemetry to clients at regular intervals."""
        while self._running and self.server:
            try:
                await self.server.broadcast_telemetry()
                # Small sleep to prevent busy-waiting (actual rate is per-client)
                await asyncio.sleep(0.005)  # 5ms = 200 Hz max check rate
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Broadcast error: {e}")
                await asyncio.sleep(0.1)

    def _handle_control_input(self, control: ControlInput) -> None:
        """Handle control input from remote client.

        This is called from the async thread, so we need to be thread-safe.

        Args:
            control: Control input from client.
        """
        with self._control_lock:
            if control.pitch is not None:
                self._remote_pitch = control.pitch
            if control.roll is not None:
                self._remote_roll = control.roll
            if control.yaw is not None:
                self._remote_yaw = control.yaw
            if control.throttle is not None:
                self._remote_throttle = control.throttle
            if control.brakes is not None:
                self._remote_brakes = control.brakes
            if control.pitch_trim is not None:
                self._remote_pitch_trim = control.pitch_trim
            if control.rudder_trim is not None:
                self._remote_rudder_trim = control.rudder_trim

    def _handle_action(self, action: ActionCommand) -> None:
        """Handle action command from remote client.

        Args:
            action: Action command from client.
        """
        if not self.context:
            return

        # Map action string to InputAction enum
        action_map = {
            "pitch_up": InputAction.PITCH_UP,
            "pitch_down": InputAction.PITCH_DOWN,
            "roll_left": InputAction.ROLL_LEFT,
            "roll_right": InputAction.ROLL_RIGHT,
            "yaw_left": InputAction.YAW_LEFT,
            "yaw_right": InputAction.YAW_RIGHT,
            "throttle_increase": InputAction.THROTTLE_INCREASE,
            "throttle_decrease": InputAction.THROTTLE_DECREASE,
            "throttle_full": InputAction.THROTTLE_FULL,
            "throttle_idle": InputAction.THROTTLE_IDLE,
            "brakes": InputAction.BRAKES,
            "parking_brake_set": InputAction.PARKING_BRAKE_SET,
            "parking_brake_release": InputAction.PARKING_BRAKE_RELEASE,
            "gear_toggle": InputAction.GEAR_TOGGLE,
            "flaps_up": InputAction.FLAPS_UP,
            "flaps_down": InputAction.FLAPS_DOWN,
            "flaps_read": InputAction.FLAPS_READ,
            "trim_pitch_up": InputAction.TRIM_PITCH_UP,
            "trim_pitch_down": InputAction.TRIM_PITCH_DOWN,
            "trim_rudder_left": InputAction.TRIM_RUDDER_LEFT,
            "trim_rudder_right": InputAction.TRIM_RUDDER_RIGHT,
            "auto_trim_enable": InputAction.AUTO_TRIM_ENABLE,
            "auto_trim_disable": InputAction.AUTO_TRIM_DISABLE,
            "auto_trim_read": InputAction.AUTO_TRIM_READ,
            "center_controls": InputAction.CENTER_CONTROLS,
            "read_airspeed": InputAction.READ_AIRSPEED,
            "read_altitude": InputAction.READ_ALTITUDE,
            "read_heading": InputAction.READ_HEADING,
            "read_vspeed": InputAction.READ_VSPEED,
            "read_attitude": InputAction.READ_ATTITUDE,
            "read_engine": InputAction.READ_ENGINE,
            "read_electrical": InputAction.READ_ELECTRICAL,
            "read_fuel": InputAction.READ_FUEL,
            "read_pitch_trim": InputAction.READ_PITCH_TRIM,
            "read_rudder_trim": InputAction.READ_RUDDER_TRIM,
            "menu_toggle": InputAction.MENU_TOGGLE,
            "menu_up": InputAction.MENU_UP,
            "menu_down": InputAction.MENU_DOWN,
            "menu_select": InputAction.MENU_SELECT,
            "menu_back": InputAction.MENU_BACK,
            "atc_menu": InputAction.ATC_MENU,
            "checklist_menu": InputAction.CHECKLIST_MENU,
            "ground_services_menu": InputAction.GROUND_SERVICES_MENU,
            "atc_select_1": InputAction.ATC_SELECT_1,
            "atc_select_2": InputAction.ATC_SELECT_2,
            "atc_select_3": InputAction.ATC_SELECT_3,
            "atc_select_4": InputAction.ATC_SELECT_4,
            "atc_select_5": InputAction.ATC_SELECT_5,
            "atc_select_6": InputAction.ATC_SELECT_6,
            "atc_select_7": InputAction.ATC_SELECT_7,
            "atc_select_8": InputAction.ATC_SELECT_8,
            "atc_select_9": InputAction.ATC_SELECT_9,
            "tts_next": InputAction.TTS_NEXT,
            "tts_repeat": InputAction.TTS_REPEAT,
            "tts_interrupt": InputAction.TTS_INTERRUPT,
            "pause": InputAction.PAUSE,
        }

        input_action = action_map.get(action.action)

        if input_action:
            # Publish action event via event bus
            from airborne.core.input import InputActionEvent

            self.context.event_bus.publish(
                InputActionEvent(action=input_action.value, value=action.value)
            )
            logger.debug(f"Remote action dispatched: {action.action}")
        else:
            logger.warning(f"Unknown action: {action.action}")

    def update(self, dt: float) -> None:
        """Update plugin state.

        This is called every frame from the main thread.

        Args:
            dt: Delta time in seconds.
        """
        if not self.context or not self.server:
            return

        # Update telemetry for broadcast
        if self.telemetry_collector:
            telemetry = self.telemetry_collector.get_telemetry()
            self.server.update_telemetry(telemetry)

        # Apply remote control inputs if any
        self._apply_remote_controls()

    def _apply_remote_controls(self) -> None:
        """Apply accumulated remote control inputs to the input system."""
        if not self.context:
            return

        with self._control_lock:
            # Check if we have any remote inputs to apply
            has_inputs = any(
                [
                    self._remote_pitch is not None,
                    self._remote_roll is not None,
                    self._remote_yaw is not None,
                    self._remote_throttle is not None,
                    self._remote_brakes is not None,
                    self._remote_pitch_trim is not None,
                    self._remote_rudder_trim is not None,
                ]
            )

            if not has_inputs:
                return

            # Build control input message data
            data: dict[str, Any] = {}

            if self._remote_pitch is not None:
                data["pitch"] = self._remote_pitch
            if self._remote_roll is not None:
                data["roll"] = self._remote_roll
            if self._remote_yaw is not None:
                data["yaw"] = self._remote_yaw
            if self._remote_throttle is not None:
                data["throttle"] = self._remote_throttle
            if self._remote_brakes is not None:
                data["brakes"] = self._remote_brakes
            if self._remote_pitch_trim is not None:
                data["pitch_trim"] = self._remote_pitch_trim
            if self._remote_rudder_trim is not None:
                data["rudder_trim"] = self._remote_rudder_trim

        # Publish control input message
        # Note: This merges with local inputs (last-wins)
        self.context.message_queue.publish(
            Message(
                sender="remote_control",
                recipients=["*"],
                topic=MessageTopic.CONTROL_INPUT,
                data=data,
                priority=MessagePriority.HIGH,
            )
        )

    def shutdown(self) -> None:
        """Shutdown the plugin."""
        logger.info("Shutting down remote control plugin...")

        # Signal async loop to stop
        self._running = False

        # Wait for thread to finish
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
            if self._thread.is_alive():
                logger.warning("Async thread did not stop cleanly")

        # Unsubscribe from messages
        if self.context:
            mq = self.context.message_queue
            mq.unsubscribe(MessageTopic.POSITION_UPDATED, self._on_telemetry_message)
            mq.unsubscribe(MessageTopic.ENGINE_STATE, self._on_telemetry_message)
            mq.unsubscribe(MessageTopic.ELECTRICAL_STATE, self._on_telemetry_message)
            mq.unsubscribe(MessageTopic.FUEL_STATE, self._on_telemetry_message)
            mq.unsubscribe(MessageTopic.CONTROL_INPUT, self._on_telemetry_message)
            mq.unsubscribe(MessageTopic.TERRAIN_UPDATED, self._on_telemetry_message)
            mq.unsubscribe("parking_brake", self._on_telemetry_message)

        logger.info("Remote control plugin shutdown complete")

    def handle_message(self, message: Message) -> None:
        """Handle messages from other plugins.

        Args:
            message: Message from the queue.
        """
        # Most messages are handled via direct subscription
        # This is for any additional messages we might need
        pass

    def on_config_changed(self, config: dict[str, Any]) -> None:
        """Handle configuration changes.

        Args:
            config: New configuration dictionary.
        """
        # Configuration changes require restart
        logger.info("Remote control config changed (restart required for changes)")
