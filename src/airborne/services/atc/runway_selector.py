"""Runway selection based on wind and aircraft type.

Selects the optimal runway for takeoff/landing based on:
- Wind direction and speed (prefer headwind)
- Aircraft type (runway length requirements)
- Runway surface and lighting

Typical usage:
    from airborne.services.atc.runway_selector import RunwaySelector

    selector = RunwaySelector()
    runway = selector.select_runway(runways, wind_direction=270, wind_speed=10)
"""

import logging
import math
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from airborne.airports.database import Runway
    from airborne.services.atc.gateway_loader import GatewayRunway

logger = logging.getLogger(__name__)


class AircraftCategory(Enum):
    """Aircraft size category for runway selection.

    Determines minimum runway length requirements.
    """

    LIGHT_GA = "light_ga"  # Cessna 172, Piper Cherokee
    HEAVY_GA = "heavy_ga"  # Bonanza, Mooney, Twin
    TURBOPROP = "turboprop"  # King Air, PC-12
    LIGHT_JET = "light_jet"  # Citation, Phenom
    MEDIUM_JET = "medium_jet"  # Challenger, Gulfstream
    HEAVY_JET = "heavy_jet"  # 737, A320


# Minimum runway lengths in feet for each category
MIN_RUNWAY_LENGTHS: dict[AircraftCategory, int] = {
    AircraftCategory.LIGHT_GA: 2000,
    AircraftCategory.HEAVY_GA: 3000,
    AircraftCategory.TURBOPROP: 4000,
    AircraftCategory.LIGHT_JET: 5000,
    AircraftCategory.MEDIUM_JET: 6000,
    AircraftCategory.HEAVY_JET: 8000,
}

# Maximum crosswind component (knots) for each category
MAX_CROSSWIND: dict[AircraftCategory, int] = {
    AircraftCategory.LIGHT_GA: 12,
    AircraftCategory.HEAVY_GA: 15,
    AircraftCategory.TURBOPROP: 20,
    AircraftCategory.LIGHT_JET: 25,
    AircraftCategory.MEDIUM_JET: 30,
    AircraftCategory.HEAVY_JET: 35,
}


@dataclass
class RunwayEnd:
    """One end of a runway.

    Attributes:
        ident: Runway identifier (e.g., "31", "09L").
        heading: Magnetic heading in degrees.
        latitude: Latitude of threshold.
        longitude: Longitude of threshold.
        elevation_ft: Threshold elevation.
    """

    ident: str
    heading: float
    latitude: float = 0.0
    longitude: float = 0.0
    elevation_ft: float = 0.0


@dataclass
class RunwayInfo:
    """Complete runway information for selection.

    Attributes:
        low_end: Low-numbered end of runway.
        high_end: High-numbered end of runway.
        length_ft: Runway length in feet.
        width_ft: Runway width in feet.
        surface: Surface type description.
        lighted: Whether runway has lighting.
        closed: Whether runway is closed.
    """

    low_end: RunwayEnd
    high_end: RunwayEnd
    length_ft: float
    width_ft: float = 0.0
    surface: str = "asphalt"
    lighted: bool = True
    closed: bool = False


@dataclass
class RunwaySelection:
    """Result of runway selection.

    Attributes:
        runway_id: Selected runway identifier.
        heading: Runway magnetic heading.
        headwind_component: Headwind component in knots (positive = headwind).
        crosswind_component: Crosswind component in knots (absolute value).
        runway_info: Full runway information.
        selection_reason: Why this runway was selected.
    """

    runway_id: str
    heading: float
    headwind_component: float
    crosswind_component: float
    runway_info: RunwayInfo
    selection_reason: str


class RunwaySelector:
    """Select optimal runway based on wind and aircraft.

    Analyzes wind conditions and aircraft requirements to select
    the best runway for operations.

    Examples:
        >>> selector = RunwaySelector()
        >>> result = selector.select_runway(
        ...     runways,
        ...     wind_direction=270,
        ...     wind_speed=15,
        ...     aircraft_category=AircraftCategory.LIGHT_GA
        ... )
        >>> print(f"Use runway {result.runway_id}")
    """

    def __init__(self) -> None:
        """Initialize runway selector."""
        pass

    def select_runway(
        self,
        runways: list[RunwayInfo],
        wind_direction: float,
        wind_speed: float,
        aircraft_category: AircraftCategory = AircraftCategory.LIGHT_GA,
        prefer_lighted: bool = False,
    ) -> RunwaySelection | None:
        """Select the best runway for current conditions.

        Args:
            runways: List of available runways.
            wind_direction: Wind direction in degrees (where wind is FROM).
            wind_speed: Wind speed in knots.
            aircraft_category: Aircraft type for length requirements.
            prefer_lighted: Prefer lighted runways (for night operations).

        Returns:
            RunwaySelection with best runway, or None if no suitable runway.

        Examples:
            >>> result = selector.select_runway(runways, 270, 15)
            >>> print(f"Runway {result.runway_id}, headwind {result.headwind_component:.0f}kt")
        """
        if not runways:
            return None

        # Filter out closed runways
        available = [r for r in runways if not r.closed]
        if not available:
            logger.warning("All runways are closed")
            return None

        # Filter by aircraft requirements
        min_length = MIN_RUNWAY_LENGTHS.get(aircraft_category, 2000)
        suitable = [r for r in available if r.length_ft >= min_length]

        if not suitable:
            logger.warning(
                "No runways meet minimum length %d ft for %s",
                min_length,
                aircraft_category.value,
            )
            # Fall back to longest available runway
            suitable = sorted(available, key=lambda r: r.length_ft, reverse=True)[:1]

        # Calculate wind components for each runway end
        candidates: list[tuple[RunwayEnd, RunwayInfo, float, float]] = []

        for runway in suitable:
            # Check both ends of runway
            for end in [runway.low_end, runway.high_end]:
                headwind, crosswind = self._calculate_wind_components(
                    end.heading, wind_direction, wind_speed
                )
                candidates.append((end, runway, headwind, crosswind))

        # Filter by crosswind limits
        max_crosswind = MAX_CROSSWIND.get(aircraft_category, 15)
        within_limits = [c for c in candidates if c[3] <= max_crosswind]

        if not within_limits:
            logger.warning(
                "All runways exceed crosswind limit %d kt for %s",
                max_crosswind,
                aircraft_category.value,
            )
            # Use runway with minimum crosswind
            within_limits = candidates

        # Sort by headwind (prefer maximum headwind)
        within_limits.sort(key=lambda c: c[2], reverse=True)

        # Apply lighting preference if requested
        if prefer_lighted:
            lighted = [c for c in within_limits if c[1].lighted]
            if lighted:
                within_limits = lighted

        # Select best runway
        best = within_limits[0]
        end, runway, headwind, crosswind = best

        # Determine selection reason
        if headwind >= 0:
            reason = f"Best headwind ({headwind:.0f} kt)"
        else:
            reason = f"Minimum tailwind ({-headwind:.0f} kt)"

        if prefer_lighted and runway.lighted:
            reason += ", lighted"

        return RunwaySelection(
            runway_id=end.ident,
            heading=end.heading,
            headwind_component=headwind,
            crosswind_component=crosswind,
            runway_info=runway,
            selection_reason=reason,
        )

    def select_runway_from_gateway(
        self,
        gateway_runways: list["GatewayRunway"],
        wind_direction: float,
        wind_speed: float,
        aircraft_category: AircraftCategory = AircraftCategory.LIGHT_GA,
    ) -> RunwaySelection | None:
        """Select runway using Gateway runway data.

        Args:
            gateway_runways: Runways from GatewayAirportData.
            wind_direction: Wind direction in degrees.
            wind_speed: Wind speed in knots.
            aircraft_category: Aircraft type.

        Returns:
            RunwaySelection or None.
        """
        # Convert Gateway runways to RunwayInfo
        runways = []
        for gw_rwy in gateway_runways:
            runway = RunwayInfo(
                low_end=RunwayEnd(
                    ident=gw_rwy.id1,
                    heading=gw_rwy.heading1,
                    latitude=gw_rwy.lat1,
                    longitude=gw_rwy.lon1,
                ),
                high_end=RunwayEnd(
                    ident=gw_rwy.id2,
                    heading=gw_rwy.heading2,
                    latitude=gw_rwy.lat2,
                    longitude=gw_rwy.lon2,
                ),
                length_ft=self._calculate_runway_length(gw_rwy),
                width_ft=gw_rwy.width_m * 3.28084,  # Convert meters to feet
                surface=self._surface_code_to_name(gw_rwy.surface),
                lighted=True,  # Assume lighted unless specified
            )
            runways.append(runway)

        return self.select_runway(runways, wind_direction, wind_speed, aircraft_category)

    def select_runway_from_database(
        self,
        db_runways: list["Runway"],
        wind_direction: float,
        wind_speed: float,
        aircraft_category: AircraftCategory = AircraftCategory.LIGHT_GA,
    ) -> RunwaySelection | None:
        """Select runway using OurAirports database runway data.

        Args:
            db_runways: Runways from AirportDatabase.
            wind_direction: Wind direction in degrees.
            wind_speed: Wind speed in knots.
            aircraft_category: Aircraft type.

        Returns:
            RunwaySelection or None.
        """
        runways = []
        for db_rwy in db_runways:
            runway = RunwayInfo(
                low_end=RunwayEnd(
                    ident=db_rwy.le_ident,
                    heading=db_rwy.le_heading_deg,
                    latitude=db_rwy.le_latitude,
                    longitude=db_rwy.le_longitude,
                    elevation_ft=db_rwy.le_elevation_ft,
                ),
                high_end=RunwayEnd(
                    ident=db_rwy.he_ident,
                    heading=db_rwy.he_heading_deg,
                    latitude=db_rwy.he_latitude,
                    longitude=db_rwy.he_longitude,
                    elevation_ft=db_rwy.he_elevation_ft,
                ),
                length_ft=db_rwy.length_ft,
                width_ft=db_rwy.width_ft,
                surface=db_rwy.surface.value if db_rwy.surface else "unknown",
                lighted=db_rwy.lighted,
                closed=db_rwy.closed,
            )
            runways.append(runway)

        return self.select_runway(runways, wind_direction, wind_speed, aircraft_category)

    @staticmethod
    def _calculate_wind_components(
        runway_heading: float, wind_direction: float, wind_speed: float
    ) -> tuple[float, float]:
        """Calculate headwind and crosswind components.

        Args:
            runway_heading: Runway magnetic heading in degrees.
            wind_direction: Wind direction (from) in degrees.
            wind_speed: Wind speed in knots.

        Returns:
            Tuple of (headwind, crosswind) in knots.
            Positive headwind = into the wind (good).
            Negative headwind = tailwind (bad).
            Crosswind is always positive (absolute value).
        """
        # Calculate angle between runway and wind
        # Wind direction is where wind comes FROM
        # We want angle from runway heading to wind direction
        angle_diff = wind_direction - runway_heading
        angle_rad = math.radians(angle_diff)

        # Headwind component: positive when landing into wind
        # cos(0) = 1 when runway points into wind
        headwind = wind_speed * math.cos(angle_rad)

        # Crosswind component: absolute value
        crosswind = abs(wind_speed * math.sin(angle_rad))

        return headwind, crosswind

    @staticmethod
    def _calculate_runway_length(gw_rwy: "GatewayRunway") -> float:
        """Calculate runway length from endpoint coordinates.

        Args:
            gw_rwy: Gateway runway data.

        Returns:
            Runway length in feet.
        """
        # Haversine formula for distance
        lat1, lon1 = math.radians(gw_rwy.lat1), math.radians(gw_rwy.lon1)
        lat2, lon2 = math.radians(gw_rwy.lat2), math.radians(gw_rwy.lon2)

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))

        # Earth radius in feet
        radius_ft = 20_902_231  # ~6371 km

        return c * radius_ft

    @staticmethod
    def _surface_code_to_name(code: int) -> str:
        """Convert X-Plane surface code to name.

        Args:
            code: X-Plane surface type code.

        Returns:
            Human-readable surface name.
        """
        surfaces = {
            1: "asphalt",
            2: "concrete",
            3: "turf",
            4: "dirt",
            5: "gravel",
            12: "dry_lakebed",
            13: "water",
            14: "snow",
            15: "transparent",
        }
        return surfaces.get(code, "unknown")


def calculate_active_runway(
    runway_headings: list[tuple[str, int]],
    wind_direction: float,
    wind_speed: float,
) -> str:
    """Calculate active runway from list of runway/heading pairs.

    Simple version for backwards compatibility with existing code.

    Args:
        runway_headings: List of (runway_id, heading) tuples.
        wind_direction: Wind direction in degrees.
        wind_speed: Wind speed in knots.

    Returns:
        Best runway identifier.

    Examples:
        >>> runways = [("31", 310), ("13", 130)]
        >>> calculate_active_runway(runways, 300, 10)
        '31'
    """
    if not runway_headings:
        return ""

    if wind_speed < 3:
        # Calm wind - return first runway
        return runway_headings[0][0]

    best_runway = runway_headings[0][0]
    best_headwind = float("-inf")

    for runway_id, heading in runway_headings:
        # Calculate wind angle
        angle_diff = wind_direction - heading
        angle_rad = math.radians(angle_diff)
        headwind = wind_speed * math.cos(angle_rad)

        if headwind > best_headwind:
            best_headwind = headwind
            best_runway = runway_id

    return best_runway
