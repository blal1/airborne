"""WebSocket protocol message definitions for remote control.

This module defines the JSON message format for communication between
the Airborne simulator and remote control clients.

Message Types:
- telemetry: Aircraft state broadcast from server to clients
- control: Control inputs from client to server
- action: Discrete actions (gear, flaps, etc.) from client
- config: Client configuration (e.g., telemetry rate)
- status: Server status messages
"""

import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class MessageType(Enum):
    """Types of WebSocket messages."""

    TELEMETRY = "telemetry"
    CONTROL = "control"
    ACTION = "action"
    CONFIG = "config"
    STATUS = "status"
    ERROR = "error"


@dataclass
class TelemetryData:
    """Aircraft telemetry data sent to clients.

    All values use aviation standard units:
    - Speeds: knots
    - Altitudes: feet
    - Vertical speed: feet per minute
    - Angles: degrees
    - Position: meters (world coordinates)
    """

    # Timestamp
    timestamp: float = field(default_factory=time.time)

    # Position (world coordinates in meters)
    position_x: float = 0.0
    position_y: float = 0.0  # Altitude in meters
    position_z: float = 0.0

    # Velocity (m/s)
    velocity_x: float = 0.0
    velocity_y: float = 0.0
    velocity_z: float = 0.0

    # Aviation units
    airspeed_kts: float = 0.0
    groundspeed_kts: float = 0.0
    altitude_ft: float = 0.0
    altitude_agl_ft: float = 0.0
    vertical_speed_fpm: float = 0.0

    # Attitude (degrees)
    heading_deg: float = 0.0
    pitch_deg: float = 0.0
    roll_deg: float = 0.0

    # Angular velocity (deg/s)
    pitch_rate: float = 0.0
    roll_rate: float = 0.0
    yaw_rate: float = 0.0

    # Control surfaces (normalized -1 to 1 or 0 to 1)
    elevator: float = 0.0
    aileron: float = 0.0
    rudder: float = 0.0
    throttle: float = 0.0
    flaps: float = 0.0
    gear: float = 1.0

    # Trim (normalized -1 to 1)
    pitch_trim: float = 0.0
    rudder_trim: float = 0.0

    # Engine state
    engine_running: bool = False
    engine_rpm: float = 0.0
    engine_power_hp: float = 0.0
    fuel_flow_gph: float = 0.0

    # Fuel
    fuel_quantity_gal: float = 0.0
    fuel_remaining_hours: float = 0.0

    # Electrical
    battery_voltage: float = 0.0
    alternator_amps: float = 0.0
    master_switch: bool = False

    # State flags
    on_ground: bool = True
    parking_brake: bool = False
    stall_warning: bool = False

    # Acceleration (g)
    g_force: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class ControlInput:
    """Control input from remote client.

    Continuous control axes for flight control surfaces.
    All values normalized to -1.0 to 1.0 (or 0.0 to 1.0 for throttle/brakes).
    """

    pitch: float | None = None  # -1 (nose down) to 1 (nose up)
    roll: float | None = None  # -1 (left) to 1 (right)
    yaw: float | None = None  # -1 (left) to 1 (right)
    throttle: float | None = None  # 0 to 1
    brakes: float | None = None  # 0 to 1
    pitch_trim: float | None = None  # -1 to 1
    rudder_trim: float | None = None  # -1 to 1

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ControlInput":
        """Create from dictionary."""
        return cls(
            pitch=data.get("pitch"),
            roll=data.get("roll"),
            yaw=data.get("yaw"),
            throttle=data.get("throttle"),
            brakes=data.get("brakes"),
            pitch_trim=data.get("pitch_trim"),
            rudder_trim=data.get("rudder_trim"),
        )


@dataclass
class ActionCommand:
    """Discrete action command from remote client.

    Actions are one-shot commands like toggling gear or changing flaps.
    """

    action: str  # Action name (e.g., "gear_toggle", "flaps_up")
    value: float | None = None  # Optional value for the action

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActionCommand":
        """Create from dictionary."""
        return cls(
            action=data.get("action", ""),
            value=data.get("value"),
        )


@dataclass
class ClientConfig:
    """Client configuration message.

    Allows clients to configure their connection parameters.
    """

    telemetry_rate_ms: int = 50  # Telemetry broadcast interval in milliseconds
    client_name: str = ""  # Optional client identifier

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClientConfig":
        """Create from dictionary."""
        return cls(
            telemetry_rate_ms=data.get("telemetry_rate_ms", 50),
            client_name=data.get("client_name", ""),
        )


@dataclass
class ServerStatus:
    """Server status message sent to clients."""

    connected_clients: int = 0
    server_version: str = "1.0.0"
    simulation_paused: bool = False
    aircraft_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class ProtocolMessage:
    """WebSocket protocol message encoder/decoder."""

    @staticmethod
    def encode_telemetry(data: TelemetryData) -> str:
        """Encode telemetry data to JSON string."""
        return json.dumps(
            {
                "type": MessageType.TELEMETRY.value,
                "data": data.to_dict(),
            }
        )

    @staticmethod
    def encode_status(status: ServerStatus) -> str:
        """Encode server status to JSON string."""
        return json.dumps(
            {
                "type": MessageType.STATUS.value,
                "data": status.to_dict(),
            }
        )

    @staticmethod
    def encode_error(error_message: str, error_code: str = "unknown") -> str:
        """Encode error message to JSON string."""
        return json.dumps(
            {
                "type": MessageType.ERROR.value,
                "data": {
                    "error": error_message,
                    "code": error_code,
                },
            }
        )

    @staticmethod
    def decode(message: str) -> tuple[MessageType, dict[str, Any]]:
        """Decode JSON message string.

        Args:
            message: JSON string message.

        Returns:
            Tuple of (message_type, data_dict).

        Raises:
            ValueError: If message is invalid JSON or missing required fields.
        """
        try:
            parsed = json.loads(message)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}") from e

        if "type" not in parsed:
            raise ValueError("Message missing 'type' field")

        try:
            msg_type = MessageType(parsed["type"])
        except ValueError as e:
            raise ValueError(f"Unknown message type: {parsed['type']}") from e

        data = parsed.get("data", {})
        return msg_type, data


# List of valid action names for validation
VALID_ACTIONS = {
    # Flight controls
    "pitch_up",
    "pitch_down",
    "roll_left",
    "roll_right",
    "yaw_left",
    "yaw_right",
    "throttle_increase",
    "throttle_decrease",
    "throttle_full",
    "throttle_idle",
    # Brakes and gear
    "brakes",
    "parking_brake_set",
    "parking_brake_release",
    "gear_toggle",
    # Flaps
    "flaps_up",
    "flaps_down",
    "flaps_read",
    # Trim
    "trim_pitch_up",
    "trim_pitch_down",
    "trim_rudder_left",
    "trim_rudder_right",
    "auto_trim_enable",
    "auto_trim_disable",
    "auto_trim_read",
    # Center controls
    "center_controls",
    # Instrument readouts
    "read_airspeed",
    "read_altitude",
    "read_heading",
    "read_vspeed",
    "read_attitude",
    "read_engine",
    "read_electrical",
    "read_fuel",
    "read_pitch_trim",
    "read_rudder_trim",
    # Menu controls
    "menu_toggle",
    "menu_up",
    "menu_down",
    "menu_select",
    "menu_back",
    "atc_menu",
    "checklist_menu",
    "ground_services_menu",
    # ATC selection
    "atc_select_1",
    "atc_select_2",
    "atc_select_3",
    "atc_select_4",
    "atc_select_5",
    "atc_select_6",
    "atc_select_7",
    "atc_select_8",
    "atc_select_9",
    # TTS
    "tts_next",
    "tts_repeat",
    "tts_interrupt",
    # System
    "pause",
}
