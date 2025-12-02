"""Telemetry collector for gathering aircraft state data.

This module collects telemetry data from various sources (physics, engine,
electrical, fuel systems) and aggregates them into a single TelemetryData
object for transmission to remote clients.
"""

import time
from typing import Any

from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessageTopic
from airborne.plugins.network.protocol import TelemetryData

logger = get_logger(__name__)


class TelemetryCollector:
    """Collects and aggregates telemetry data from various systems.

    The collector subscribes to various message topics and caches the latest
    data. When get_telemetry() is called, it returns the current aggregated
    state.
    """

    def __init__(self) -> None:
        """Initialize telemetry collector."""
        self._telemetry = TelemetryData()

        # Cached state from various systems
        self._position_data: dict[str, Any] = {}
        self._engine_data: dict[str, Any] = {}
        self._electrical_data: dict[str, Any] = {}
        self._fuel_data: dict[str, Any] = {}
        self._control_data: dict[str, Any] = {}

        # Terrain elevation for AGL calculation
        self._terrain_elevation_m: float = 0.0

        # Simulation state
        self._paused: bool = False
        self._parking_brake: bool = False

    def handle_message(self, message: Message) -> None:
        """Handle incoming messages and update cached state.

        Args:
            message: Message from the queue.
        """
        if message.topic == MessageTopic.POSITION_UPDATED:
            self._update_from_position(message.data)
        elif message.topic == MessageTopic.ENGINE_STATE:
            self._update_from_engine(message.data)
        elif message.topic == MessageTopic.ELECTRICAL_STATE:
            self._update_from_electrical(message.data)
        elif message.topic == MessageTopic.FUEL_STATE:
            self._update_from_fuel(message.data)
        elif message.topic == MessageTopic.CONTROL_INPUT:
            self._update_from_controls(message.data)
        elif message.topic == MessageTopic.TERRAIN_UPDATED:
            self._terrain_elevation_m = float(message.data.get("elevation", 0.0))
        elif message.topic == "parking_brake":
            action = message.data.get("action", "toggle")
            if action == "set":
                self._parking_brake = True
            elif action == "release":
                self._parking_brake = False
            else:
                self._parking_brake = not self._parking_brake

    def _update_from_position(self, data: dict[str, Any]) -> None:
        """Update telemetry from position update message.

        Args:
            data: Position update data dictionary.
        """
        self._position_data = data

        # Position (world coordinates)
        pos = data.get("position", {})
        self._telemetry.position_x = float(pos.get("x", 0.0))
        self._telemetry.position_y = float(pos.get("y", 0.0))
        self._telemetry.position_z = float(pos.get("z", 0.0))

        # Velocity
        vel = data.get("velocity", {})
        self._telemetry.velocity_x = float(vel.get("x", 0.0))
        self._telemetry.velocity_y = float(vel.get("y", 0.0))
        self._telemetry.velocity_z = float(vel.get("z", 0.0))

        # Aviation units (already converted in physics plugin)
        self._telemetry.airspeed_kts = float(data.get("airspeed", 0.0))
        self._telemetry.altitude_ft = float(data.get("altitude", 0.0))
        self._telemetry.vertical_speed_fpm = float(data.get("vspeed", 0.0))
        self._telemetry.heading_deg = float(data.get("heading", 0.0))
        self._telemetry.pitch_deg = float(data.get("pitch", 0.0))
        self._telemetry.roll_deg = float(data.get("bank", 0.0))

        # Ground speed
        groundspeed = data.get("groundspeed", 0.0)
        self._telemetry.groundspeed_kts = float(groundspeed)

        # Angular velocity (convert from rad/s to deg/s)
        ang_vel = data.get("angular_velocity", {})
        self._telemetry.pitch_rate = float(ang_vel.get("x", 0.0)) * 57.2958
        self._telemetry.roll_rate = float(ang_vel.get("y", 0.0)) * 57.2958
        self._telemetry.yaw_rate = float(ang_vel.get("z", 0.0)) * 57.2958

        # State flags
        self._telemetry.on_ground = bool(data.get("on_ground", True))

        # AGL altitude
        altitude_m = float(pos.get("y", 0.0))
        agl_m = altitude_m - self._terrain_elevation_m
        self._telemetry.altitude_agl_ft = agl_m * 3.28084

        # G-force from acceleration
        accel = data.get("acceleration", {})
        accel_y = float(accel.get("y", 0.0))
        # Approximate G-force (1g = 9.81 m/s^2, add 1 for gravity)
        self._telemetry.g_force = (accel_y / 9.81) + 1.0

        # Stall warning from angle of attack
        aoa = data.get("angle_of_attack_deg")
        if aoa is not None:
            # Typical stall warning at ~15 degrees AoA
            self._telemetry.stall_warning = float(aoa) > 14.0

    def _update_from_engine(self, data: dict[str, Any]) -> None:
        """Update telemetry from engine state message.

        Args:
            data: Engine state data dictionary.
        """
        self._engine_data = data

        self._telemetry.engine_running = bool(data.get("running", False))
        self._telemetry.engine_rpm = float(data.get("rpm", 0.0))
        # Accept both "horsepower" and "power_hp"
        power = data.get("horsepower") or data.get("power_hp", 0.0)
        self._telemetry.engine_power_hp = float(power)
        self._telemetry.fuel_flow_gph = float(data.get("fuel_flow_gph", 0.0))

    def _update_from_electrical(self, data: dict[str, Any]) -> None:
        """Update telemetry from electrical state message.

        Args:
            data: Electrical state data dictionary.
        """
        self._electrical_data = data

        self._telemetry.battery_voltage = float(data.get("battery_voltage", 0.0))
        self._telemetry.alternator_amps = float(data.get("alternator_amps", 0.0))
        self._telemetry.master_switch = bool(data.get("master_switch", False))

    def _update_from_fuel(self, data: dict[str, Any]) -> None:
        """Update telemetry from fuel state message.

        Args:
            data: Fuel state data dictionary.
        """
        self._fuel_data = data

        self._telemetry.fuel_quantity_gal = float(data.get("quantity_gallons", 0.0))
        self._telemetry.fuel_remaining_hours = float(data.get("remaining_hours", 0.0))

    def _update_from_controls(self, data: dict[str, Any]) -> None:
        """Update telemetry from control input message.

        Args:
            data: Control input data dictionary.
        """
        self._control_data = data

        self._telemetry.elevator = float(data.get("pitch", 0.0))
        self._telemetry.aileron = float(data.get("roll", 0.0))
        self._telemetry.rudder = float(data.get("yaw", 0.0))
        self._telemetry.throttle = float(data.get("throttle", 0.0))
        self._telemetry.flaps = float(data.get("flaps", 0.0))
        self._telemetry.gear = float(data.get("gear", 1.0))
        self._telemetry.pitch_trim = float(data.get("pitch_trim", 0.0))
        self._telemetry.rudder_trim = float(data.get("rudder_trim", 0.0))

    def get_telemetry(self) -> TelemetryData:
        """Get current aggregated telemetry data.

        Returns:
            TelemetryData with current aircraft state.
        """
        # Update timestamp
        self._telemetry.timestamp = time.time()

        # Update parking brake from cached state
        self._telemetry.parking_brake = self._parking_brake

        return self._telemetry

    def set_paused(self, paused: bool) -> None:
        """Set simulation paused state.

        Args:
            paused: Whether simulation is paused.
        """
        self._paused = paused

    def is_paused(self) -> bool:
        """Check if simulation is paused.

        Returns:
            True if simulation is paused.
        """
        return self._paused
