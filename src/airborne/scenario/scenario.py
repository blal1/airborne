"""Flight scenario management system.

This module provides functionality for managing flight scenarios including
spawn location, aircraft configuration, weather, and initial conditions.

Typical usage:
    from airborne.scenario import Scenario, ScenarioBuilder

    # Create scenario from CLI args
    scenario = ScenarioBuilder.from_cli_args(args)

    # Or create scenario programmatically
    scenario = ScenarioBuilder() \\
        .with_airport("KPAO") \\
        .with_aircraft("cessna172") \\
        .with_parking("RAMP") \\
        .build()
"""

import logging
from dataclasses import dataclass
from enum import Enum

from airborne.physics.vectors import Vector3

logger = logging.getLogger(__name__)


class SpawnLocation(Enum):
    """Where to spawn aircraft at airport.

    Attributes:
        RAMP: Parking ramp
        RUNWAY: Active runway threshold
        TAXIWAY: Random taxiway
        GATE: Gate (if available)
    """

    RAMP = "ramp"
    RUNWAY = "runway"
    TAXIWAY = "taxiway"
    GATE = "gate"


class EngineState(Enum):
    """Initial engine state.

    Attributes:
        COLD_AND_DARK: All systems off
        READY_TO_START: Battery on, ready for startup
        RUNNING: Engine running, ready to taxi
        READY_FOR_TAKEOFF: Configured for immediate takeoff
    """

    COLD_AND_DARK = "cold_and_dark"
    READY_TO_START = "ready_to_start"
    RUNNING = "running"
    READY_FOR_TAKEOFF = "ready_for_takeoff"


@dataclass
class Scenario:
    """Flight scenario configuration.

    Attributes:
        airport_icao: Departure airport ICAO code
        arrival_icao: Arrival airport ICAO code (optional, None for circuit training)
        circuit_training: If True, practicing patterns at departure airport only
        spawn_location: Where to spawn at airport
        spawn_position: Specific position (if None, auto-selected)
        spawn_heading: Initial heading in degrees (0-359)
        aircraft_type: Aircraft type identifier
        engine_state: Initial engine state
        fuel_gallons: Fuel load in gallons (None = use aircraft default)
        passenger_count: Number of passengers (0-max based on aircraft)
        time_of_day: Hour of day (0-23)
        weather_preset: Weather preset name (optional)
        callsign: Aircraft callsign (if None, auto-generated)

    Examples:
        >>> scenario = Scenario(
        ...     airport_icao="KPAO",
        ...     spawn_location=SpawnLocation.RAMP,
        ...     aircraft_type="cessna172",
        ...     engine_state=EngineState.COLD_AND_DARK,
        ... )
    """

    airport_icao: str
    arrival_icao: str | None = None
    circuit_training: bool = False
    spawn_location: SpawnLocation = SpawnLocation.RAMP
    spawn_position: Vector3 | None = None
    spawn_heading: float = 0.0
    aircraft_type: str = "cessna172"
    engine_state: EngineState = EngineState.COLD_AND_DARK
    fuel_gallons: float | None = None  # None = use aircraft default
    passenger_count: int = 0
    time_of_day: int = 12
    weather_preset: str | None = None
    callsign: str | None = None


class ScenarioBuilder:
    """Builder for creating Scenario instances.

    Provides a fluent API for constructing scenarios with validation.

    Examples:
        >>> scenario = ScenarioBuilder() \\
        ...     .with_airport("KPAO") \\
        ...     .with_spawn_location(SpawnLocation.RUNWAY) \\
        ...     .with_engine_state(EngineState.READY_FOR_TAKEOFF) \\
        ...     .build()
    """

    def __init__(self) -> None:
        """Initialize scenario builder with defaults."""
        self._airport_icao: str | None = None
        self._arrival_icao: str | None = None
        self._circuit_training: bool = False
        self._spawn_location = SpawnLocation.RAMP
        self._spawn_position: Vector3 | None = None
        self._spawn_heading: float = 0.0
        self._aircraft_type = "cessna172"
        self._engine_state = EngineState.COLD_AND_DARK
        self._fuel_gallons: float | None = None
        self._passenger_count: int = 0
        self._time_of_day: int = 12
        self._weather_preset: str | None = None
        self._callsign: str | None = None

    def with_airport(self, icao: str) -> "ScenarioBuilder":
        """Set departure airport.

        Args:
            icao: Airport ICAO code (e.g., "KPAO", "EGLL")

        Returns:
            Self for method chaining
        """
        self._airport_icao = icao.upper()
        return self

    def with_arrival(self, icao: str | None) -> "ScenarioBuilder":
        """Set arrival airport.

        Args:
            icao: Airport ICAO code or None for circuit training

        Returns:
            Self for method chaining
        """
        self._arrival_icao = icao.upper() if icao else None
        return self

    def with_circuit_training(self, enabled: bool = True) -> "ScenarioBuilder":
        """Enable or disable circuit training mode.

        Args:
            enabled: True for circuit training at single airport

        Returns:
            Self for method chaining
        """
        self._circuit_training = enabled
        return self

    def with_spawn_location(self, location: SpawnLocation) -> "ScenarioBuilder":
        """Set spawn location type.

        Args:
            location: Spawn location type

        Returns:
            Self for method chaining
        """
        self._spawn_location = location
        return self

    def with_spawn_position(self, position: Vector3) -> "ScenarioBuilder":
        """Set specific spawn position.

        Args:
            position: Exact spawn position (overrides spawn_location)

        Returns:
            Self for method chaining
        """
        self._spawn_position = position
        return self

    def with_spawn_heading(self, heading: float) -> "ScenarioBuilder":
        """Set initial heading.

        Args:
            heading: Heading in degrees (0-359)

        Returns:
            Self for method chaining
        """
        self._spawn_heading = heading % 360
        return self

    def with_aircraft(self, aircraft_type: str) -> "ScenarioBuilder":
        """Set aircraft type.

        Args:
            aircraft_type: Aircraft identifier (e.g., "cessna172")

        Returns:
            Self for method chaining
        """
        self._aircraft_type = aircraft_type
        return self

    def with_engine_state(self, state: EngineState) -> "ScenarioBuilder":
        """Set initial engine state.

        Args:
            state: Engine state

        Returns:
            Self for method chaining
        """
        self._engine_state = state
        return self

    def with_fuel(self, gallons: float | None) -> "ScenarioBuilder":
        """Set fuel load in gallons.

        Args:
            gallons: Fuel amount in gallons, or None for aircraft default

        Returns:
            Self for method chaining
        """
        self._fuel_gallons = gallons
        return self

    def with_passengers(self, count: int) -> "ScenarioBuilder":
        """Set number of passengers.

        Args:
            count: Number of passengers (0 or more)

        Returns:
            Self for method chaining
        """
        self._passenger_count = max(0, count)
        return self

    def with_time_of_day(self, hour: int) -> "ScenarioBuilder":
        """Set time of day.

        Args:
            hour: Hour (0-23)

        Returns:
            Self for method chaining
        """
        self._time_of_day = hour % 24
        return self

    def with_weather(self, preset: str) -> "ScenarioBuilder":
        """Set weather preset.

        Args:
            preset: Weather preset name

        Returns:
            Self for method chaining
        """
        self._weather_preset = preset
        return self

    def with_callsign(self, callsign: str) -> "ScenarioBuilder":
        """Set aircraft callsign.

        Args:
            callsign: Callsign string

        Returns:
            Self for method chaining
        """
        self._callsign = callsign
        return self

    def build(self) -> Scenario:
        """Build the scenario.

        Returns:
            Configured scenario instance

        Raises:
            ValueError: If airport_icao not set
        """
        if not self._airport_icao:
            raise ValueError("Airport ICAO code is required")

        return Scenario(
            airport_icao=self._airport_icao,
            arrival_icao=self._arrival_icao,
            circuit_training=self._circuit_training,
            spawn_location=self._spawn_location,
            spawn_position=self._spawn_position,
            spawn_heading=self._spawn_heading,
            aircraft_type=self._aircraft_type,
            engine_state=self._engine_state,
            fuel_gallons=self._fuel_gallons,
            passenger_count=self._passenger_count,
            time_of_day=self._time_of_day,
            weather_preset=self._weather_preset,
            callsign=self._callsign,
        )

    @staticmethod
    def from_airport(airport_icao: str) -> Scenario:
        """Create default scenario at given airport.

        Args:
            airport_icao: Airport ICAO code

        Returns:
            Scenario with default settings
        """
        return ScenarioBuilder().with_airport(airport_icao).build()
