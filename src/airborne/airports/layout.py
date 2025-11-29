"""Airport layout abstraction for ground navigation.

Provides a unified representation of airport ground geometry (runways, taxiways,
parking, hold short points) that works with both parsed .apt data and generated
layouts for airports without detailed scenery.

Typical usage:
    from airborne.airports.layout import AirportLayoutLoader

    loader = AirportLayoutLoader()
    layout = loader.load("LFLY", airport_db)

    for runway in layout.runways:
        print(f"Runway {runway.id}: {runway.heading}°")
"""

import logging
import math
from dataclasses import dataclass, field

from airborne.airports.database import AirportDatabase, Runway
from airborne.physics.vectors import Vector3
from airborne.services.atc.gateway_loader import GatewayAirportData

logger = logging.getLogger(__name__)


@dataclass
class LayoutRunway:
    """Runway representation for ground navigation.

    Attributes:
        id: Runway identifier (e.g., "27L", "09").
        threshold_pos: Threshold position (x=lon, y=elev, z=lat).
        end_pos: Opposite end position.
        width_m: Runway width in meters.
        heading: Magnetic heading in degrees.
    """

    id: str
    threshold_pos: Vector3
    end_pos: Vector3
    width_m: float
    heading: float

    def get_centerline_point(self, fraction: float) -> Vector3:
        """Get a point along the runway centerline.

        Args:
            fraction: 0.0 = threshold, 1.0 = opposite end.

        Returns:
            Position on centerline.
        """
        return Vector3(
            self.threshold_pos.x + fraction * (self.end_pos.x - self.threshold_pos.x),
            self.threshold_pos.y + fraction * (self.end_pos.y - self.threshold_pos.y),
            self.threshold_pos.z + fraction * (self.end_pos.z - self.threshold_pos.z),
        )

    @property
    def length_m(self) -> float:
        """Calculate runway length in meters."""
        dx = (self.end_pos.x - self.threshold_pos.x) * 111000
        dz = (self.end_pos.z - self.threshold_pos.z) * 111000
        return math.sqrt(dx * dx + dz * dz)

    @property
    def midpoint(self) -> Vector3:
        """Get runway midpoint."""
        return self.get_centerline_point(0.5)


@dataclass
class TaxiwaySegment:
    """A segment of a taxiway.

    Attributes:
        start_pos: Start position (x=lon, y=elev, z=lat).
        end_pos: End position.
        width_m: Segment width in meters.
    """

    start_pos: Vector3
    end_pos: Vector3
    width_m: float = 15.0

    @property
    def length_m(self) -> float:
        """Calculate segment length in meters."""
        dx = (self.end_pos.x - self.start_pos.x) * 111000
        dz = (self.end_pos.z - self.start_pos.z) * 111000
        return math.sqrt(dx * dx + dz * dz)

    @property
    def heading(self) -> float:
        """Calculate heading from start to end."""
        dx = (self.end_pos.x - self.start_pos.x) * 111000
        dz = (self.end_pos.z - self.start_pos.z) * 111000
        heading = math.degrees(math.atan2(dx, dz))
        return (heading + 360) % 360


@dataclass
class LayoutTaxiway:
    """Taxiway representation for ground navigation.

    Attributes:
        name: Taxiway name (e.g., "A", "B1").
        segments: Ordered list of taxiway segments.
    """

    name: str
    segments: list[TaxiwaySegment] = field(default_factory=list)

    @property
    def total_length_m(self) -> float:
        """Calculate total taxiway length."""
        return sum(seg.length_m for seg in self.segments)


@dataclass
class LayoutParking:
    """Parking position for ground navigation.

    Attributes:
        id: Position identifier (e.g., "Hangar", "Gate 5", "N17").
        position: Position (x=lon, y=elev, z=lat).
        heading: Aircraft heading when parked (degrees).
        parking_type: Type of parking (hangar, tie_down, gate).
    """

    id: str
    position: Vector3
    heading: float
    parking_type: str = "tie_down"


@dataclass
class LayoutHoldShort:
    """Hold short point for runway entry.

    Attributes:
        runway_id: Runway being protected (e.g., "27L").
        position: Hold short line position.
        taxiway_name: Taxiway this hold short is on.
    """

    runway_id: str
    position: Vector3
    taxiway_name: str


@dataclass
class AirportLayout:
    """Unified airport ground layout.

    Contains all ground navigation geometry for an airport, whether loaded
    from .apt data or generated for airports without detailed scenery.

    Attributes:
        icao: Airport ICAO code.
        runways: List of runway layouts.
        taxiways: List of taxiway layouts.
        parking: List of parking positions.
        hold_short_points: List of hold short points.
        is_generated: True if layout was generated (no .apt data).
    """

    icao: str
    runways: list[LayoutRunway] = field(default_factory=list)
    taxiways: list[LayoutTaxiway] = field(default_factory=list)
    parking: list[LayoutParking] = field(default_factory=list)
    hold_short_points: list[LayoutHoldShort] = field(default_factory=list)
    is_generated: bool = False

    def get_runway(self, runway_id: str) -> LayoutRunway | None:
        """Get runway by ID.

        Args:
            runway_id: Runway identifier (e.g., "27L", "09").

        Returns:
            LayoutRunway if found, None otherwise.
        """
        for runway in self.runways:
            if runway.id == runway_id:
                return runway
        return None

    def get_taxiway(self, name: str) -> LayoutTaxiway | None:
        """Get taxiway by name.

        Args:
            name: Taxiway name (e.g., "A", "B1").

        Returns:
            LayoutTaxiway if found, None otherwise.
        """
        for taxiway in self.taxiways:
            if taxiway.name == name:
                return taxiway
        return None

    def get_parking(self, parking_id: str) -> LayoutParking | None:
        """Get parking position by ID.

        Args:
            parking_id: Parking identifier.

        Returns:
            LayoutParking if found, None otherwise.
        """
        for pos in self.parking:
            if pos.id == parking_id:
                return pos
        return None


# ICAO taxiway width codes to meters
TAXIWAY_WIDTH_MAP = {
    "A": 7.5,  # Small aircraft
    "B": 10.5,  # Medium aircraft
    "C": 15.0,  # Large aircraft
    "D": 18.0,  # Heavy aircraft
    "E": 23.0,  # Very heavy aircraft
    "F": 25.0,  # Super heavy aircraft
}


class AirportLayoutLoader:
    """Loads or generates airport layouts.

    Provides a unified interface for loading airport ground geometry.
    Uses Gateway/apt.dat data when available, otherwise generates a
    basic layout from runway data.

    Examples:
        >>> loader = AirportLayoutLoader()
        >>> layout = loader.load("LFLY", airport_db)
        >>> print(f"Runways: {len(layout.runways)}, Taxiways: {len(layout.taxiways)}")
    """

    def __init__(self) -> None:
        """Initialize the layout loader."""
        pass

    def load(self, icao: str, airport_db: AirportDatabase) -> AirportLayout:
        """Load layout from .apt or generate basic layout.

        Args:
            icao: Airport ICAO code.
            airport_db: Airport database for data access.

        Returns:
            AirportLayout with ground navigation geometry.

        Raises:
            ValueError: If airport not found or has no runway data.
        """
        icao = icao.upper()

        # Try to get Gateway data (includes taxi network)
        gateway_data = airport_db.get_gateway_data(icao)

        if gateway_data and gateway_data.taxi_nodes:
            logger.info("Loading %s layout from Gateway data", icao)
            return self._load_from_gateway(icao, gateway_data)

        # Fall back to generating basic layout
        logger.info("Generating basic layout for %s (no taxi network)", icao)
        return self._generate_basic(icao, airport_db)

    def _load_from_gateway(self, icao: str, data: GatewayAirportData) -> AirportLayout:
        """Convert Gateway data to AirportLayout.

        Args:
            icao: Airport ICAO code.
            data: Gateway airport data.

        Returns:
            AirportLayout from Gateway data.
        """
        layout = AirportLayout(icao=icao, is_generated=False)

        elevation_m = data.elevation_ft * 0.3048

        # Convert runways
        for gw_runway in data.runways:
            # Create both runway ends
            layout.runways.append(
                LayoutRunway(
                    id=gw_runway.id1,
                    threshold_pos=Vector3(gw_runway.lon1, elevation_m, gw_runway.lat1),
                    end_pos=Vector3(gw_runway.lon2, elevation_m, gw_runway.lat2),
                    width_m=gw_runway.width_m,
                    heading=gw_runway.heading1,
                )
            )
            layout.runways.append(
                LayoutRunway(
                    id=gw_runway.id2,
                    threshold_pos=Vector3(gw_runway.lon2, elevation_m, gw_runway.lat2),
                    end_pos=Vector3(gw_runway.lon1, elevation_m, gw_runway.lat1),
                    width_m=gw_runway.width_m,
                    heading=gw_runway.heading2,
                )
            )

        # Build taxiway segments from edges
        taxiway_segments: dict[str, list[TaxiwaySegment]] = {}

        for edge in data.taxi_edges:
            if edge.is_runway:
                continue  # Skip runway edges

            name = edge.name if edge.name else "UNNAMED"

            start_node = data.taxi_nodes.get(edge.node_begin)
            end_node = data.taxi_nodes.get(edge.node_end)

            if not start_node or not end_node:
                continue

            width_m = TAXIWAY_WIDTH_MAP.get(edge.width_code, 15.0)

            segment = TaxiwaySegment(
                start_pos=Vector3(start_node.longitude, elevation_m, start_node.latitude),
                end_pos=Vector3(end_node.longitude, elevation_m, end_node.latitude),
                width_m=width_m,
            )

            if name not in taxiway_segments:
                taxiway_segments[name] = []
            taxiway_segments[name].append(segment)

        # Create taxiway objects
        for name, segments in taxiway_segments.items():
            layout.taxiways.append(LayoutTaxiway(name=name, segments=segments))

        # Convert parking positions
        for gw_parking in data.parking_positions:
            layout.parking.append(
                LayoutParking(
                    id=gw_parking.id,
                    position=Vector3(gw_parking.longitude, elevation_m, gw_parking.latitude),
                    heading=gw_parking.heading,
                    parking_type=gw_parking.type,
                )
            )

        # Find hold short points from taxi nodes
        for node in data.taxi_nodes.values():
            if node.is_hold_short and node.on_runway:
                # Find which taxiway this node is on
                taxiway_name = self._find_taxiway_for_node(node.id, data)

                layout.hold_short_points.append(
                    LayoutHoldShort(
                        runway_id=node.on_runway,
                        position=Vector3(node.longitude, elevation_m, node.latitude),
                        taxiway_name=taxiway_name,
                    )
                )

        logger.info(
            "Loaded %s: %d runways, %d taxiways, %d parking, %d hold short",
            icao,
            len(layout.runways),
            len(layout.taxiways),
            len(layout.parking),
            len(layout.hold_short_points),
        )

        return layout

    def _find_taxiway_for_node(self, node_id: int, data: GatewayAirportData) -> str:
        """Find which taxiway a node belongs to.

        Args:
            node_id: Node ID to search for.
            data: Gateway airport data.

        Returns:
            Taxiway name or empty string if not found.
        """
        for edge in data.taxi_edges:
            if edge.node_begin == node_id or edge.node_end == node_id:
                if edge.name and not edge.is_runway:
                    return edge.name
        return ""

    def _generate_basic(self, icao: str, db: AirportDatabase) -> AirportLayout:
        """Generate basic airport layout from runway data.

        Creates a generic small airport template with:
        - Runway from database
        - Hangar on left side when facing lower-numbered runway end
        - Single taxiway from hangar to runway midpoint
        - Hold short point before runway

        Args:
            icao: Airport ICAO code.
            db: Airport database.

        Returns:
            Generated AirportLayout.

        Raises:
            ValueError: If no runway data available.
        """
        runways = db.get_runways(icao)
        if not runways:
            raise ValueError(f"No runway data for {icao}")

        runway = runways[0]  # Use primary runway
        airport = db.get_airport(icao)
        elevation_m = airport.position.y if airport else 0.0

        # Determine which end is lower-numbered
        le_num = self._parse_runway_number(runway.le_ident)
        he_num = self._parse_runway_number(runway.he_ident)

        if le_num < he_num:
            # Face toward lower number (le end)
            facing_heading = runway.le_heading_deg
            runway_start = Vector3(runway.le_longitude, elevation_m, runway.le_latitude)
            runway_end = Vector3(runway.he_longitude, elevation_m, runway.he_latitude)
            lower_id = runway.le_ident
            higher_id = runway.he_ident
        else:
            # Face toward higher number (he end)
            facing_heading = runway.he_heading_deg
            runway_start = Vector3(runway.he_longitude, elevation_m, runway.he_latitude)
            runway_end = Vector3(runway.le_longitude, elevation_m, runway.le_latitude)
            lower_id = runway.he_ident
            higher_id = runway.le_ident

        runway_width_m = runway.width_ft * 0.3048

        layout = AirportLayout(icao=icao, is_generated=True)

        # Add runway (both directions)
        layout.runways.append(
            LayoutRunway(
                id=lower_id,
                threshold_pos=runway_start,
                end_pos=runway_end,
                width_m=runway_width_m,
                heading=facing_heading,
            )
        )
        layout.runways.append(
            LayoutRunway(
                id=higher_id,
                threshold_pos=runway_end,
                end_pos=runway_start,
                width_m=runway_width_m,
                heading=(facing_heading + 180) % 360,
            )
        )

        # Calculate runway midpoint
        midpoint = Vector3(
            (runway_start.x + runway_end.x) / 2,
            elevation_m,
            (runway_start.z + runway_end.z) / 2,
        )

        # Hangar is on left when facing lower number
        # Left = facing_heading - 90 degrees
        hangar_direction = (facing_heading - 90) % 360
        hangar_offset_m = 50.0  # 50m from runway centerline

        hangar_pos = self._offset_position(midpoint, hangar_direction, hangar_offset_m)

        # Create parking position at hangar
        layout.parking.append(
            LayoutParking(
                id="Hangar",
                position=hangar_pos,
                heading=(hangar_direction + 180) % 360,  # Face toward runway
                parking_type="hangar",
            )
        )

        # Create taxiway from hangar to runway
        # Taxiway meets runway at midpoint
        taxiway_runway_junction = self._offset_position(
            midpoint, hangar_direction, runway_width_m / 2 + 2  # Just off runway edge
        )

        layout.taxiways.append(
            LayoutTaxiway(
                name="A",
                segments=[
                    TaxiwaySegment(
                        start_pos=hangar_pos,
                        end_pos=taxiway_runway_junction,
                        width_m=15.0,
                    )
                ],
            )
        )

        # Hold short point 10m before runway edge
        hold_short_pos = self._offset_position(
            midpoint, hangar_direction, runway_width_m / 2 + 10
        )

        layout.hold_short_points.append(
            LayoutHoldShort(
                runway_id=f"{lower_id}/{higher_id}",
                position=hold_short_pos,
                taxiway_name="A",
            )
        )

        logger.info(
            "Generated basic layout for %s: 1 runway, 1 taxiway, 1 parking",
            icao,
        )

        return layout

    @staticmethod
    def _parse_runway_number(ident: str) -> int:
        """Parse runway number from identifier.

        Args:
            ident: Runway identifier (e.g., "09", "27L", "31R").

        Returns:
            Numeric runway heading (1-36).
        """
        # Extract digits
        digits = "".join(c for c in ident if c.isdigit())
        if digits:
            return int(digits)
        return 0

    @staticmethod
    def _offset_position(pos: Vector3, heading: float, distance_m: float) -> Vector3:
        """Calculate position offset from a point.

        Args:
            pos: Starting position.
            heading: Direction to offset (degrees).
            distance_m: Distance to offset (meters).

        Returns:
            New position.
        """
        heading_rad = math.radians(heading)

        # Convert meters to degrees (approximate)
        # At mid-latitudes, 1 degree ~ 111km
        meters_per_degree = 111000.0

        dx = distance_m * math.sin(heading_rad) / meters_per_degree
        dz = distance_m * math.cos(heading_rad) / meters_per_degree

        return Vector3(pos.x + dx, pos.y, pos.z + dz)
