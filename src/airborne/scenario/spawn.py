"""Aircraft spawning system.

This module provides functionality for spawning aircraft at airports
based on scenario configuration.

Typical usage:
    from airborne.scenario import SpawnManager, Scenario

    spawn_manager = SpawnManager(airport_db)
    spawn_state = spawn_manager.spawn_aircraft(scenario)
"""

import logging
from dataclasses import dataclass

from airborne.airports.database import AirportDatabase, ParkingPosition
from airborne.physics.vectors import Vector3
from airborne.scenario.scenario import EngineState, Scenario, SpawnLocation

logger = logging.getLogger(__name__)


@dataclass
class SpawnState:
    """Aircraft spawn state.

    Attributes:
        position: Spawn position (longitude, elevation, latitude)
        heading: Initial heading in degrees
        airspeed: Initial airspeed in m/s
        engine_running: Whether engine should be running
        on_ground: Whether aircraft is on ground
        parking_brake: Whether parking brake is set
        at_parking: Whether spawned at a parking position
        parking_id: ID of the parking spot (if at_parking is True)
    """

    position: Vector3
    heading: float
    airspeed: float = 0.0
    engine_running: bool = False
    on_ground: bool = True
    parking_brake: bool = True
    at_parking: bool = False
    parking_id: str | None = None


class SpawnManager:
    """Manages aircraft spawning at airports.

    Handles determining spawn position based on scenario configuration
    and airport layout.

    Attributes:
        airport_db: Airport database for airport lookups

    Examples:
        >>> spawn_manager = SpawnManager(airport_db)
        >>> scenario = Scenario(airport_icao="KPAO")
        >>> spawn_state = spawn_manager.spawn_aircraft(scenario)
    """

    def __init__(self, airport_db: AirportDatabase) -> None:
        """Initialize spawn manager.

        Args:
            airport_db: Airport database instance
        """
        self.airport_db = airport_db

    def spawn_aircraft(self, scenario: Scenario) -> SpawnState:
        """Spawn aircraft according to scenario.

        Args:
            scenario: Scenario configuration

        Returns:
            Spawn state with position and configuration

        Raises:
            ValueError: If airport not found in database
        """
        # Get airport
        airport = self.airport_db.get_airport(scenario.airport_icao)
        if not airport:
            raise ValueError(f"Airport not found: {scenario.airport_icao}")

        logger.info(f"Spawning at {airport.name} ({scenario.airport_icao})")

        # Determine spawn position and parking info
        at_parking = False
        parking_id: str | None = None

        if scenario.spawn_position:
            position = scenario.spawn_position
            heading = scenario.spawn_heading
        else:
            position, heading, at_parking, parking_id = self._get_spawn_position(
                scenario, airport.icao
            )

        # Determine engine and brake state based on engine state
        engine_running = scenario.engine_state in (
            EngineState.RUNNING,
            EngineState.READY_FOR_TAKEOFF,
        )

        parking_brake = scenario.engine_state in (
            EngineState.COLD_AND_DARK,
            EngineState.READY_TO_START,
        )

        # Initial airspeed (takeoff scenarios may have initial speed)
        airspeed = 0.0
        if scenario.engine_state == EngineState.READY_FOR_TAKEOFF:
            airspeed = 0.0  # Still stationary, just configured

        return SpawnState(
            position=position,
            heading=heading,
            airspeed=airspeed,
            engine_running=engine_running,
            on_ground=True,
            parking_brake=parking_brake,
            at_parking=at_parking,
            parking_id=parking_id,
        )

    def _get_spawn_position(
        self, scenario: Scenario, airport_icao: str
    ) -> tuple[Vector3, float, bool, str | None]:
        """Get spawn position for scenario.

        Args:
            scenario: Scenario configuration
            airport_icao: Airport ICAO code

        Returns:
            Tuple of (position, heading, at_parking, parking_id)
        """
        if scenario.spawn_location == SpawnLocation.RUNWAY:
            pos, hdg = self._get_runway_spawn(airport_icao, scenario.spawn_heading)
            return pos, hdg, False, None
        elif scenario.spawn_location == SpawnLocation.RAMP:
            return self._get_ramp_spawn(airport_icao, scenario.spawn_heading)
        elif scenario.spawn_location == SpawnLocation.TAXIWAY:
            pos, hdg = self._get_taxiway_spawn(airport_icao, scenario.spawn_heading)
            return pos, hdg, False, None
        elif scenario.spawn_location == SpawnLocation.GATE:
            return self._get_gate_spawn(airport_icao, scenario.spawn_heading)
        else:
            # Default to airport center
            airport = self.airport_db.get_airport(airport_icao)
            if airport:
                return airport.position, scenario.spawn_heading, False, None
            else:
                return Vector3(0, 0, 0), 0.0, False, None

    def _get_runway_spawn(
        self, airport_icao: str, preferred_heading: float
    ) -> tuple[Vector3, float]:
        """Get spawn position at runway threshold.

        Args:
            airport_icao: Airport ICAO code
            preferred_heading: Preferred runway heading

        Returns:
            Tuple of (position, heading)
        """
        runways = self.airport_db.get_runways(airport_icao)

        if not runways:
            # No runways, use airport center
            airport = self.airport_db.get_airport(airport_icao)
            if airport:
                logger.warning(f"No runways at {airport_icao}, using airport center")
                return airport.position, preferred_heading
            return Vector3(0, 0, 0), 0.0

        # Find runway closest to preferred heading
        best_runway = runways[0]
        if preferred_heading > 0:
            min_diff = abs(best_runway.le_heading_deg - preferred_heading)
            for runway in runways[1:]:
                diff = abs(runway.le_heading_deg - preferred_heading)
                if diff < min_diff:
                    min_diff = diff
                    best_runway = runway

        # Use runway low-end threshold position
        position = Vector3(
            best_runway.le_longitude,
            best_runway.le_elevation_ft * 0.3048,  # Convert feet to meters
            best_runway.le_latitude,
        )
        heading = best_runway.le_heading_deg

        logger.info(f"Spawning on runway {best_runway.le_ident} heading {heading:.0f}")

        return position, heading

    def _get_ramp_spawn(
        self, airport_icao: str, preferred_heading: float
    ) -> tuple[Vector3, float, bool, str | None]:
        """Get spawn position at ramp/parking.

        Uses real parking data from X-Plane Gateway.

        Args:
            airport_icao: Airport ICAO code
            preferred_heading: Preferred heading (used as fallback)

        Returns:
            Tuple of (position, heading, at_parking, parking_id)
        """
        airport = self.airport_db.get_airport(airport_icao)

        if not airport:
            logger.warning("Airport %s not found", airport_icao)
            return Vector3(0, 0, 0), 0.0, False, None

        # Get real parking positions from Gateway data
        parking_positions = self.airport_db.get_parking(airport_icao)

        if parking_positions:
            # Find a suitable parking position for GA aircraft
            # Prefer tie_down positions for small aircraft
            parking = self._select_parking_position(parking_positions)

            if parking:
                logger.info(
                    "Spawning at parking %s (%s) at %s, heading %.0f",
                    parking.position_id,
                    parking.parking_type,
                    airport.name,
                    parking.heading,
                )
                return parking.position, parking.heading, True, parking.position_id

        # Fallback: offset from airport center (50m south)
        logger.warning("No parking available at %s, using fallback position", airport_icao)
        position = Vector3(
            airport.position.x,
            airport.position.y,
            airport.position.z - 0.0005,  # ~50m south
        )
        heading = preferred_heading if preferred_heading > 0 else 0.0

        return position, heading, False, None

    def _select_parking_position(
        self, parking_positions: list[ParkingPosition]
    ) -> ParkingPosition | None:
        """Select a suitable parking position for GA aircraft.

        Prefers tie_down and hangar positions over gates.
        For small GA aircraft like C172, avoid jet/heavy gates.

        Args:
            parking_positions: List of available parking positions

        Returns:
            Selected parking position, or None if none suitable
        """
        # Priority order for GA aircraft
        preferred_types = ["tie_down", "hangar", "misc", "gate"]

        for ptype in preferred_types:
            for parking in parking_positions:
                if parking.parking_type == ptype:
                    # Check aircraft type restrictions if available
                    if parking.aircraft_types:
                        # Skip if this is for jets/heavy aircraft only
                        types_str = "|".join(parking.aircraft_types).lower()
                        if "jets" in types_str or "heavy" in types_str:
                            continue
                    return parking

        # If no preferred type found, return first available
        return parking_positions[0] if parking_positions else None

    def _get_taxiway_spawn(
        self, airport_icao: str, preferred_heading: float
    ) -> tuple[Vector3, float]:
        """Get spawn position on taxiway.

        Args:
            airport_icao: Airport ICAO code
            preferred_heading: Preferred heading

        Returns:
            Tuple of (position, heading) - taxiway spawns are not at parking
        """
        # For now, use ramp spawn but strip parking info
        pos, hdg, _, _ = self._get_ramp_spawn(airport_icao, preferred_heading)
        return pos, hdg

    def _get_gate_spawn(
        self, airport_icao: str, preferred_heading: float
    ) -> tuple[Vector3, float, bool, str | None]:
        """Get spawn position at gate.

        Args:
            airport_icao: Airport ICAO code
            preferred_heading: Preferred heading

        Returns:
            Tuple of (position, heading, at_parking, parking_id)
        """
        airport = self.airport_db.get_airport(airport_icao)

        if not airport:
            logger.warning("Airport %s not found", airport_icao)
            return Vector3(0, 0, 0), 0.0, False, None

        # Get parking positions and prefer actual gates
        parking_positions = self.airport_db.get_parking(airport_icao)

        if parking_positions:
            # Prefer gate-type positions
            for parking in parking_positions:
                if parking.parking_type == "gate":
                    logger.info(
                        "Spawning at gate %s at %s, heading %.0f",
                        parking.position_id,
                        airport.name,
                        parking.heading,
                    )
                    return parking.position, parking.heading, True, parking.position_id

            # Fall back to any parking
            parking = parking_positions[0]
            logger.info(
                "No gates at %s, using parking %s (%s), heading %.0f",
                airport.name,
                parking.position_id,
                parking.parking_type,
                parking.heading,
            )
            return parking.position, parking.heading, True, parking.position_id

        # Fallback to ramp spawn
        return self._get_ramp_spawn(airport_icao, preferred_heading)
