"""Airport database using X-Plane Gateway data.

This module provides functionality for loading and querying airport data
from the X-Plane Scenery Gateway, including airports, runways, taxiways,
parking positions, and frequencies.

Typical usage:
    db = AirportDatabase()
    db.load_airport("KPAO")  # Load on-demand from Gateway

    airport = db.get_airport("KPAO")
    runways = db.get_runways("KPAO")
    parking = db.get_parking("KPAO")
"""

import logging
import math
import warnings
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from airborne.physics.vectors import Vector3
from airborne.services.atc.gateway_loader import (
    GatewayAirportData,
    GatewayAirportLoader,
)

logger = logging.getLogger(__name__)


class AirportType(Enum):
    """Airport type classification."""

    HELIPORT = "heliport"
    SMALL_AIRPORT = "small_airport"
    SEAPLANE_BASE = "seaplane_base"
    MEDIUM_AIRPORT = "medium_airport"
    LARGE_AIRPORT = "large_airport"
    CLOSED = "closed"
    BALLOONPORT = "balloonport"


class SurfaceType(Enum):
    """Runway surface type."""

    ASPH = "asphalt"
    CONC = "concrete"
    TURF = "turf"
    DIRT = "dirt"
    GRVL = "gravel"
    GRASS = "grass"
    SAND = "sand"
    WATER = "water"
    UNKNOWN = "unknown"


# X-Plane surface code to SurfaceType mapping
XPLANE_SURFACE_MAP = {
    1: SurfaceType.ASPH,  # Asphalt
    2: SurfaceType.CONC,  # Concrete
    3: SurfaceType.GRASS,  # Turf/grass
    4: SurfaceType.DIRT,  # Dirt
    5: SurfaceType.GRVL,  # Gravel
    12: SurfaceType.ASPH,  # Dry lakebed (treat as asphalt)
    13: SurfaceType.WATER,  # Water
    14: SurfaceType.UNKNOWN,  # Snow/ice
    15: SurfaceType.UNKNOWN,  # Transparent
}


class FrequencyType(Enum):
    """Radio frequency type."""

    TWR = "tower"
    GND = "ground"
    ATIS = "atis"
    UNICOM = "unicom"
    CTAF = "ctaf"
    APP = "approach"
    DEP = "departure"
    CLEARANCE = "clearance"
    MULTICOM = "multicom"
    FSS = "fss"
    OTHER = "other"


# Gateway frequency type to FrequencyType mapping
GATEWAY_FREQ_MAP = {
    "TOWER": FrequencyType.TWR,
    "TWR": FrequencyType.TWR,
    "GROUND": FrequencyType.GND,
    "GND": FrequencyType.GND,
    "ATIS": FrequencyType.ATIS,
    "UNICOM": FrequencyType.UNICOM,
    "CTAF": FrequencyType.CTAF,
    "APP": FrequencyType.APP,
    "APPROACH": FrequencyType.APP,
    "DEP": FrequencyType.DEP,
    "DEPARTURE": FrequencyType.DEP,
    "CLEARANCE": FrequencyType.CLEARANCE,
}


@dataclass
class Airport:
    """Airport information from X-Plane Gateway.

    Attributes:
        icao: ICAO code (e.g., "KPAO")
        name: Airport name
        position: Geographic position (x=lon, y=elevation, z=lat)
        airport_type: Type classification (derived from data)
        municipality: City/town name (empty for Gateway data)
        iso_country: ISO country code (empty for Gateway data)
        scheduled_service: Whether airport has scheduled airline service
        iata_code: IATA code (3-letter, if exists)
        gps_code: GPS code
        home_link: Airport website URL
        wikipedia_link: Wikipedia URL
    """

    icao: str
    name: str
    position: Vector3  # x=longitude, y=elevation, z=latitude
    airport_type: AirportType
    municipality: str = ""
    iso_country: str = ""
    scheduled_service: bool = False
    iata_code: str | None = None
    gps_code: str | None = None
    home_link: str | None = None
    wikipedia_link: str | None = None


@dataclass
class Runway:
    """Runway information.

    Attributes:
        airport_icao: Parent airport ICAO code
        runway_id: Runway identifier (e.g., "09/27")
        length_ft: Runway length in feet
        width_ft: Runway width in feet
        surface: Surface type
        lighted: Whether runway is lighted
        closed: Whether runway is closed
        le_ident: Low-end identifier (e.g., "09")
        le_latitude: Low-end latitude
        le_longitude: Low-end longitude
        le_elevation_ft: Low-end elevation in feet
        le_heading_deg: Low-end magnetic heading
        he_ident: High-end identifier (e.g., "27")
        he_latitude: High-end latitude
        he_longitude: High-end longitude
        he_elevation_ft: High-end elevation in feet
        he_heading_deg: High-end magnetic heading
    """

    airport_icao: str
    runway_id: str
    length_ft: float
    width_ft: float
    surface: SurfaceType
    lighted: bool
    closed: bool
    le_ident: str
    le_latitude: float
    le_longitude: float
    le_elevation_ft: float
    le_heading_deg: float
    he_ident: str
    he_latitude: float
    he_longitude: float
    he_elevation_ft: float
    he_heading_deg: float


@dataclass
class Frequency:
    """Radio frequency information.

    Attributes:
        airport_icao: Parent airport ICAO code
        freq_type: Frequency type
        description: Frequency description
        frequency_mhz: Frequency in MHz
    """

    airport_icao: str
    freq_type: FrequencyType
    description: str
    frequency_mhz: float


@dataclass
class ParkingPosition:
    """Parking/startup position at an airport.

    Attributes:
        airport_icao: Parent airport ICAO code
        position_id: Position identifier (e.g., "C12", "Gate 5")
        position: Geographic position (x=lon, y=elevation, z=lat)
        heading: Aircraft heading when parked
        parking_type: Type of parking (tie_down, gate, hangar)
        aircraft_types: List of supported aircraft types
    """

    airport_icao: str
    position_id: str
    position: Vector3
    heading: float
    parking_type: str = "tie_down"
    aircraft_types: list[str] | None = None


class AirportDatabase:
    """Airport database using X-Plane Gateway data.

    Loads airport data on-demand from the X-Plane Scenery Gateway,
    including runways, taxiways, parking positions, and frequencies.

    Examples:
        >>> db = AirportDatabase()
        >>> db.load_airport("KPAO")
        >>> airport = db.get_airport("KPAO")
        >>> print(f"{airport.name} at {airport.position}")
        >>> parking = db.get_parking("KPAO")
    """

    def __init__(self, cache_dir: str | Path | None = None) -> None:
        """Initialize database with Gateway loader.

        Args:
            cache_dir: Directory for caching Gateway data.
                      Defaults to data/airports/gateway_cache
        """
        self.gateway_loader = GatewayAirportLoader(cache_dir)
        self.airports: dict[str, Airport] = {}
        self.runways: dict[str, list[Runway]] = {}
        self.frequencies: dict[str, list[Frequency]] = {}
        self.parking: dict[str, list[ParkingPosition]] = {}
        self._gateway_data: dict[str, GatewayAirportData] = {}

    def load_airport(self, icao: str) -> bool:
        """Load a single airport from Gateway.

        Args:
            icao: ICAO code (e.g., "KPAO")

        Returns:
            True if airport was loaded successfully

        Examples:
            >>> db = AirportDatabase()
            >>> if db.load_airport("LFLY"):
            ...     print("Loaded Lyon Bron")
        """
        icao = icao.upper()

        # Already loaded?
        if icao in self.airports:
            return True

        # Fetch from Gateway
        gateway_data = self.gateway_loader.get_airport(icao)
        if not gateway_data:
            logger.warning("Airport %s not found in Gateway", icao)
            return False

        # Store raw gateway data for advanced queries
        self._gateway_data[icao] = gateway_data

        # Convert to our dataclasses
        self._convert_airport(gateway_data)
        self._convert_runways(gateway_data)
        self._convert_frequencies(gateway_data)
        self._convert_parking(gateway_data)

        logger.info(
            "Loaded %s: %s (runways=%d, parking=%d, freq=%d)",
            icao,
            gateway_data.name,
            len(self.runways.get(icao, [])),
            len(self.parking.get(icao, [])),
            len(self.frequencies.get(icao, [])),
        )

        return True

    def _convert_airport(self, data: GatewayAirportData) -> None:
        """Convert Gateway airport data to Airport dataclass."""
        # Determine airport type based on ATC presence and runway count
        # This is a heuristic - Gateway doesn't provide explicit classification
        airport_type = AirportType.MEDIUM_AIRPORT if data.has_atc else AirportType.SMALL_AIRPORT

        elevation_m = data.elevation_ft * 0.3048

        airport = Airport(
            icao=data.icao,
            name=data.name,
            position=Vector3(data.longitude, elevation_m, data.latitude),
            airport_type=airport_type,
        )

        self.airports[data.icao] = airport

    def _convert_runways(self, data: GatewayAirportData) -> None:
        """Convert Gateway runway data to Runway dataclasses."""
        runways = []

        for gw_rwy in data.runways:
            # Calculate runway length from coordinates
            length_m = self._calculate_distance_m(
                gw_rwy.lat1, gw_rwy.lon1, gw_rwy.lat2, gw_rwy.lon2
            )
            length_ft = length_m * 3.28084
            width_ft = gw_rwy.width_m * 3.28084

            # Map surface type
            surface = XPLANE_SURFACE_MAP.get(gw_rwy.surface, SurfaceType.UNKNOWN)

            runway = Runway(
                airport_icao=data.icao,
                runway_id=f"{gw_rwy.id1}/{gw_rwy.id2}",
                length_ft=length_ft,
                width_ft=width_ft,
                surface=surface,
                lighted=True,  # Gateway doesn't provide this, assume lighted
                closed=False,
                le_ident=gw_rwy.id1,
                le_latitude=gw_rwy.lat1,
                le_longitude=gw_rwy.lon1,
                le_elevation_ft=data.elevation_ft,  # Use airport elevation
                le_heading_deg=gw_rwy.heading1,
                he_ident=gw_rwy.id2,
                he_latitude=gw_rwy.lat2,
                he_longitude=gw_rwy.lon2,
                he_elevation_ft=data.elevation_ft,
                he_heading_deg=gw_rwy.heading2,
            )

            runways.append(runway)

        self.runways[data.icao] = runways

    def _convert_frequencies(self, data: GatewayAirportData) -> None:
        """Convert Gateway frequency data to Frequency dataclasses."""
        frequencies = []

        for gw_freq in data.frequencies:
            freq_type = GATEWAY_FREQ_MAP.get(gw_freq.type, FrequencyType.OTHER)

            frequency = Frequency(
                airport_icao=data.icao,
                freq_type=freq_type,
                description=gw_freq.name,
                frequency_mhz=gw_freq.frequency_mhz,
            )

            frequencies.append(frequency)

        self.frequencies[data.icao] = frequencies

    def _convert_parking(self, data: GatewayAirportData) -> None:
        """Convert Gateway parking data to ParkingPosition dataclasses."""
        parking_list = []
        elevation_m = data.elevation_ft * 0.3048

        for gw_parking in data.parking_positions:
            parking = ParkingPosition(
                airport_icao=data.icao,
                position_id=gw_parking.id,
                position=Vector3(gw_parking.longitude, elevation_m, gw_parking.latitude),
                heading=gw_parking.heading,
                parking_type=gw_parking.type,
                aircraft_types=gw_parking.aircraft_types or [],
            )

            parking_list.append(parking)

        self.parking[data.icao] = parking_list

    @staticmethod
    def _calculate_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points in meters."""
        lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
        lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)

        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.asin(math.sqrt(a))

        # Earth radius in meters
        radius_m = 6371000

        return c * radius_m

    def get_airport(self, icao: str) -> Airport | None:
        """Get airport by ICAO code.

        Automatically loads from Gateway if not already loaded.

        Args:
            icao: ICAO code (e.g., "KPAO")

        Returns:
            Airport if found, None otherwise

        Examples:
            >>> airport = db.get_airport("KPAO")
            >>> if airport:
            ...     print(airport.name)
        """
        icao = icao.upper()

        # Try to load if not present
        if icao not in self.airports:
            self.load_airport(icao)

        return self.airports.get(icao)

    def get_runways(self, icao: str) -> list[Runway]:
        """Get runways for an airport.

        Args:
            icao: Airport ICAO code

        Returns:
            List of runways (empty if none found)

        Examples:
            >>> runways = db.get_runways("KPAO")
            >>> for runway in runways:
            ...     print(f"{runway.runway_id}: {runway.length_ft}ft")
        """
        icao = icao.upper()

        # Try to load if not present
        if icao not in self.runways:
            self.load_airport(icao)

        return self.runways.get(icao, [])

    def get_frequencies(self, icao: str) -> list[Frequency]:
        """Get frequencies for an airport.

        Args:
            icao: Airport ICAO code

        Returns:
            List of frequencies (empty if none found)

        Examples:
            >>> freqs = db.get_frequencies("KPAO")
            >>> for freq in freqs:
            ...     print(f"{freq.freq_type.value}: {freq.frequency_mhz:.3f}")
        """
        icao = icao.upper()

        # Try to load if not present
        if icao not in self.frequencies:
            self.load_airport(icao)

        return self.frequencies.get(icao, [])

    def get_parking(self, icao: str) -> list[ParkingPosition]:
        """Get parking positions for an airport.

        Args:
            icao: Airport ICAO code

        Returns:
            List of parking positions (empty if none found)

        Examples:
            >>> parking = db.get_parking("LFLY")
            >>> for pos in parking:
            ...     print(f"{pos.position_id}: {pos.parking_type} @ {pos.heading}°")
        """
        icao = icao.upper()

        # Try to load if not present
        if icao not in self.parking:
            self.load_airport(icao)

        return self.parking.get(icao, [])

    def get_gateway_data(self, icao: str) -> GatewayAirportData | None:
        """Get raw Gateway data for advanced queries (taxiway network, etc.).

        Args:
            icao: Airport ICAO code

        Returns:
            GatewayAirportData if loaded, None otherwise

        Examples:
            >>> gw_data = db.get_gateway_data("LFLY")
            >>> if gw_data:
            ...     print(f"Taxi nodes: {len(gw_data.taxi_nodes)}")
        """
        icao = icao.upper()

        # Try to load if not present
        if icao not in self._gateway_data:
            self.load_airport(icao)

        return self._gateway_data.get(icao)

    def get_airports_near(self, position: Vector3, radius_nm: float) -> list[tuple[Airport, float]]:
        """Get loaded airports within radius of position.

        Note: This only searches already-loaded airports.
        For a comprehensive search, airports must be pre-loaded.

        Args:
            position: Center position (x=lon, y=elev, z=lat)
            radius_nm: Search radius in nautical miles

        Returns:
            List of (airport, distance_nm) tuples, sorted by distance

        Examples:
            >>> nearby = db.get_airports_near(Vector3(-122.05, 0, 37.36), 10)
            >>> for airport, distance in nearby:
            ...     print(f"{airport.icao}: {distance:.1f} nm")
        """
        results = []

        for airport in self.airports.values():
            distance_nm = self._haversine_distance_nm(position, airport.position)
            if distance_nm <= radius_nm:
                results.append((airport, distance_nm))

        # Sort by distance
        results.sort(key=lambda x: x[1])
        return results

    @staticmethod
    def _haversine_distance_nm(pos1: Vector3, pos2: Vector3) -> float:
        """Calculate great circle distance between two positions.

        Args:
            pos1: First position (x=lon, y=elev, z=lat)
            pos2: Second position (x=lon, y=elev, z=lat)

        Returns:
            Distance in nautical miles
        """
        # Extract lat/lon from Vector3 (z=lat, x=lon)
        lat1, lon1 = math.radians(pos1.z), math.radians(pos1.x)
        lat2, lon2 = math.radians(pos2.z), math.radians(pos2.x)

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))

        # Earth radius in nautical miles
        radius_nm = 3440.065

        return c * radius_nm

    def get_airport_count(self) -> int:
        """Get number of currently loaded airports.

        Returns:
            Number of loaded airports

        Examples:
            >>> count = db.get_airport_count()
            >>> print(f"Loaded {count} airports")
        """
        return len(self.airports)

    def get_countries(self) -> list[str]:
        """Get list of countries for loaded airports.

        Note: Gateway data doesn't include country info, so this
        may return an empty list.

        Returns:
            Sorted list of ISO country codes
        """
        countries = {
            airport.iso_country for airport in self.airports.values() if airport.iso_country
        }
        return sorted(countries)

    def _map_surface_type(self, surface: str) -> SurfaceType:
        """Map surface type string to SurfaceType enum.

        Args:
            surface: Surface type string from Gateway

        Returns:
            Corresponding SurfaceType enum value
        """
        surface_lower = surface.lower()
        mapping = {
            "asphalt": SurfaceType.ASPH,
            "asph": SurfaceType.ASPH,
            "concrete": SurfaceType.CONC,
            "conc": SurfaceType.CONC,
            "grass": SurfaceType.GRASS,
            "turf": SurfaceType.TURF,
            "dirt": SurfaceType.DIRT,
            "gravel": SurfaceType.GRVL,
            "grvl": SurfaceType.GRVL,
            "sand": SurfaceType.SAND,
            "water": SurfaceType.WATER,
        }
        return mapping.get(surface_lower, SurfaceType.UNKNOWN)

    def _map_frequency_type(self, freq_type: str) -> FrequencyType:
        """Map frequency type string to FrequencyType enum.

        Args:
            freq_type: Frequency type string from Gateway

        Returns:
            Corresponding FrequencyType enum value
        """
        return GATEWAY_FREQ_MAP.get(freq_type.upper(), FrequencyType.OTHER)

    # Backwards compatibility alias
    def load_from_csv(self, data_dir: str | Path) -> None:
        """Legacy method for CSV loading - no longer supported.

        This method is kept for backwards compatibility but no longer
        loads CSV data. Use load_airport() instead.

        Args:
            data_dir: Ignored - was directory containing CSV files

        Raises:
            DeprecationWarning: Always raised as this method is deprecated
        """
        warnings.warn(
            "load_from_csv() is no longer supported. "
            "Use load_airport(icao) to load airports on demand from X-Plane Gateway.",
            DeprecationWarning,
            stacklevel=2,
        )
