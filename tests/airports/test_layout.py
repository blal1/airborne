"""Tests for Airport Layout abstraction."""

import math
from unittest.mock import MagicMock

import pytest

from airborne.airports.layout import (
    AirportLayout,
    AirportLayoutLoader,
    LayoutParking,
    LayoutRunway,
    LayoutTaxiway,
    TaxiwaySegment,
)
from airborne.physics.vectors import Vector3


class TestLayoutRunway:
    """Test LayoutRunway dataclass."""

    def test_create_runway(self) -> None:
        """Test creating a runway layout."""
        runway = LayoutRunway(
            id="27L",
            threshold_pos=Vector3(-122.0, 10.0, 37.5),
            end_pos=Vector3(-122.01, 10.0, 37.5),
            width_m=45.0,
            heading=270.0,
        )

        assert runway.id == "27L"
        assert runway.width_m == 45.0
        assert runway.heading == 270.0

    def test_runway_length(self) -> None:
        """Test runway length calculation."""
        # Runway approximately 1km long (0.01 degrees ≈ 1110m at simple approx)
        runway = LayoutRunway(
            id="27",
            threshold_pos=Vector3(-122.0, 10.0, 37.5),
            end_pos=Vector3(-122.01, 10.0, 37.5),
            width_m=30.0,
            heading=270.0,
        )

        length = runway.length_m
        # 0.01 degrees × 111000 m/deg = 1110m (simple approximation)
        assert 1000 < length < 1200

    def test_runway_midpoint(self) -> None:
        """Test runway midpoint calculation."""
        runway = LayoutRunway(
            id="09",
            threshold_pos=Vector3(-122.0, 10.0, 37.5),
            end_pos=Vector3(-122.02, 10.0, 37.5),
            width_m=30.0,
            heading=90.0,
        )

        midpoint = runway.midpoint
        assert midpoint.x == pytest.approx(-122.01)
        assert midpoint.z == pytest.approx(37.5)

    def test_runway_centerline_point(self) -> None:
        """Test getting points along centerline."""
        runway = LayoutRunway(
            id="18",
            threshold_pos=Vector3(-122.0, 10.0, 37.5),
            end_pos=Vector3(-122.0, 10.0, 37.52),
            width_m=30.0,
            heading=180.0,
        )

        # Threshold
        point_0 = runway.get_centerline_point(0.0)
        assert point_0.z == pytest.approx(37.5)

        # End
        point_1 = runway.get_centerline_point(1.0)
        assert point_1.z == pytest.approx(37.52)

        # Quarter
        point_25 = runway.get_centerline_point(0.25)
        assert point_25.z == pytest.approx(37.505)


class TestTaxiwaySegment:
    """Test TaxiwaySegment dataclass."""

    def test_create_segment(self) -> None:
        """Test creating a taxiway segment."""
        segment = TaxiwaySegment(
            start_pos=Vector3(-122.0, 10.0, 37.5),
            end_pos=Vector3(-122.001, 10.0, 37.5),
            width_m=15.0,
        )

        assert segment.width_m == 15.0

    def test_segment_length(self) -> None:
        """Test segment length calculation."""
        segment = TaxiwaySegment(
            start_pos=Vector3(-122.0, 10.0, 37.5),
            end_pos=Vector3(-122.001, 10.0, 37.5),
            width_m=15.0,
        )

        # 0.001 degrees × 111000 m/deg = 111m (simple approximation)
        assert 100 < segment.length_m < 120

    def test_segment_heading(self) -> None:
        """Test segment heading calculation."""
        # Segment pointing east
        segment_east = TaxiwaySegment(
            start_pos=Vector3(-122.0, 10.0, 37.5),
            end_pos=Vector3(-121.99, 10.0, 37.5),
            width_m=15.0,
        )
        assert 85 < segment_east.heading < 95  # ~90 degrees

        # Segment pointing north
        segment_north = TaxiwaySegment(
            start_pos=Vector3(-122.0, 10.0, 37.5),
            end_pos=Vector3(-122.0, 10.0, 37.51),
            width_m=15.0,
        )
        assert segment_north.heading < 5 or segment_north.heading > 355  # ~0 degrees


class TestLayoutTaxiway:
    """Test LayoutTaxiway dataclass."""

    def test_create_taxiway(self) -> None:
        """Test creating a taxiway."""
        taxiway = LayoutTaxiway(name="A", segments=[])
        assert taxiway.name == "A"
        assert taxiway.total_length_m == 0

    def test_taxiway_total_length(self) -> None:
        """Test taxiway total length calculation."""
        segments = [
            TaxiwaySegment(
                start_pos=Vector3(-122.0, 10.0, 37.5),
                end_pos=Vector3(-122.001, 10.0, 37.5),
                width_m=15.0,
            ),
            TaxiwaySegment(
                start_pos=Vector3(-122.001, 10.0, 37.5),
                end_pos=Vector3(-122.002, 10.0, 37.5),
                width_m=15.0,
            ),
        ]

        taxiway = LayoutTaxiway(name="A", segments=segments)

        # Each segment ~111m, total ~222m
        assert 200 < taxiway.total_length_m < 250


class TestAirportLayout:
    """Test AirportLayout dataclass."""

    @pytest.fixture
    def sample_layout(self) -> AirportLayout:
        """Create sample airport layout."""
        layout = AirportLayout(icao="KPAO")

        layout.runways.append(
            LayoutRunway(
                id="31",
                threshold_pos=Vector3(-122.12, 10.0, 37.46),
                end_pos=Vector3(-122.10, 10.0, 37.47),
                width_m=23.0,
                heading=310.0,
            )
        )
        layout.runways.append(
            LayoutRunway(
                id="13",
                threshold_pos=Vector3(-122.10, 10.0, 37.47),
                end_pos=Vector3(-122.12, 10.0, 37.46),
                width_m=23.0,
                heading=130.0,
            )
        )

        layout.taxiways.append(
            LayoutTaxiway(
                name="A",
                segments=[
                    TaxiwaySegment(
                        start_pos=Vector3(-122.11, 10.0, 37.465),
                        end_pos=Vector3(-122.115, 10.0, 37.465),
                        width_m=15.0,
                    )
                ],
            )
        )

        layout.parking.append(
            LayoutParking(
                id="N17",
                position=Vector3(-122.116, 10.0, 37.465),
                heading=130.0,
                parking_type="tie_down",
            )
        )

        return layout

    def test_get_runway(self, sample_layout: AirportLayout) -> None:
        """Test getting runway by ID."""
        runway = sample_layout.get_runway("31")
        assert runway is not None
        assert runway.id == "31"
        assert runway.heading == 310.0

        # Non-existent runway
        assert sample_layout.get_runway("27") is None

    def test_get_taxiway(self, sample_layout: AirportLayout) -> None:
        """Test getting taxiway by name."""
        taxiway = sample_layout.get_taxiway("A")
        assert taxiway is not None
        assert taxiway.name == "A"

        # Non-existent taxiway
        assert sample_layout.get_taxiway("B") is None

    def test_get_parking(self, sample_layout: AirportLayout) -> None:
        """Test getting parking by ID."""
        parking = sample_layout.get_parking("N17")
        assert parking is not None
        assert parking.parking_type == "tie_down"

        # Non-existent parking
        assert sample_layout.get_parking("Gate1") is None


class TestAirportLayoutLoaderGeneration:
    """Test AirportLayoutLoader basic airport generation."""

    def test_parse_runway_number(self) -> None:
        """Test runway number parsing."""
        loader = AirportLayoutLoader()

        assert loader._parse_runway_number("09") == 9
        assert loader._parse_runway_number("27L") == 27
        assert loader._parse_runway_number("31R") == 31
        assert loader._parse_runway_number("36C") == 36
        assert loader._parse_runway_number("X") == 0

    def test_offset_position(self) -> None:
        """Test position offset calculation."""
        loader = AirportLayoutLoader()
        pos = Vector3(-122.0, 10.0, 37.5)

        # Offset 100m north (heading 0)
        north = loader._offset_position(pos, 0.0, 100.0)
        assert north.z > pos.z  # Latitude increased
        assert abs(north.x - pos.x) < 0.0001  # Longitude unchanged

        # Offset 100m east (heading 90)
        east = loader._offset_position(pos, 90.0, 100.0)
        assert east.x > pos.x  # Longitude increased (less negative)
        assert abs(east.z - pos.z) < 0.0001  # Latitude unchanged

    def test_hangar_placement_convention(self) -> None:
        """Test that hangar is placed on left when facing lower-numbered runway.

        For runway 09/27:
        - Lower number is 09 (heading ~090)
        - Facing 09, left is north (heading 000)
        - Hangar should be north of runway
        """
        # Create mock database
        mock_db = MagicMock()
        mock_airport = MagicMock()
        mock_airport.position = Vector3(-122.0, 10.0, 37.5)

        # Runway 09/27 (east-west)
        mock_runway = MagicMock()
        mock_runway.le_ident = "09"
        mock_runway.he_ident = "27"
        mock_runway.le_heading_deg = 90.0
        mock_runway.he_heading_deg = 270.0
        mock_runway.le_latitude = 37.5
        mock_runway.le_longitude = -122.01
        mock_runway.he_latitude = 37.5
        mock_runway.he_longitude = -122.0
        mock_runway.width_ft = 75.0
        mock_runway.length_ft = 3000.0

        mock_db.get_runways.return_value = [mock_runway]
        mock_db.get_airport.return_value = mock_airport
        mock_db.get_gateway_data.return_value = None

        loader = AirportLayoutLoader()
        layout = loader.load("TEST", mock_db)

        assert layout.is_generated is True
        assert len(layout.parking) == 1

        hangar = layout.parking[0]
        # Hangar should be north of runway (higher latitude)
        runway = layout.get_runway("09")
        assert hangar.position.z > runway.threshold_pos.z

    def test_hangar_placement_high_numbers_first(self) -> None:
        """Test hangar placement when high number comes first in idents.

        For runway 31/13:
        - Lower number is 13 (heading ~130)
        - Facing 13, left is heading 040 (northeast)
        """
        mock_db = MagicMock()
        mock_airport = MagicMock()
        mock_airport.position = Vector3(-122.0, 10.0, 37.5)

        # Runway 31/13 (northwest-southeast)
        mock_runway = MagicMock()
        mock_runway.le_ident = "31"
        mock_runway.he_ident = "13"
        mock_runway.le_heading_deg = 310.0
        mock_runway.he_heading_deg = 130.0
        mock_runway.le_latitude = 37.51
        mock_runway.le_longitude = -122.01
        mock_runway.he_latitude = 37.49
        mock_runway.he_longitude = -121.99
        mock_runway.width_ft = 60.0
        mock_runway.length_ft = 2500.0

        mock_db.get_runways.return_value = [mock_runway]
        mock_db.get_airport.return_value = mock_airport
        mock_db.get_gateway_data.return_value = None

        loader = AirportLayoutLoader()
        layout = loader.load("TEST", mock_db)

        assert layout.is_generated is True
        assert len(layout.runways) == 2
        assert len(layout.taxiways) == 1
        assert len(layout.hold_short_points) == 1

    def test_generate_creates_taxiway(self) -> None:
        """Test that generated layout includes taxiway from hangar to runway."""
        mock_db = MagicMock()
        mock_airport = MagicMock()
        mock_airport.position = Vector3(-122.0, 10.0, 37.5)

        mock_runway = MagicMock()
        mock_runway.le_ident = "18"
        mock_runway.he_ident = "36"
        mock_runway.le_heading_deg = 180.0
        mock_runway.he_heading_deg = 360.0
        mock_runway.le_latitude = 37.49
        mock_runway.le_longitude = -122.0
        mock_runway.he_latitude = 37.51
        mock_runway.he_longitude = -122.0
        mock_runway.width_ft = 50.0
        mock_runway.length_ft = 4000.0

        mock_db.get_runways.return_value = [mock_runway]
        mock_db.get_airport.return_value = mock_airport
        mock_db.get_gateway_data.return_value = None

        loader = AirportLayoutLoader()
        layout = loader.load("TEST", mock_db)

        # Should have taxiway A
        taxiway = layout.get_taxiway("A")
        assert taxiway is not None
        assert len(taxiway.segments) == 1

        # Taxiway should connect hangar to near runway
        hangar = layout.parking[0]
        segment = taxiway.segments[0]

        # Start should be at hangar
        dx = abs(segment.start_pos.x - hangar.position.x) * 111000
        dz = abs(segment.start_pos.z - hangar.position.z) * 111000
        assert math.sqrt(dx * dx + dz * dz) < 1  # Within 1 meter

    def test_generate_creates_hold_short(self) -> None:
        """Test that generated layout includes hold short point."""
        mock_db = MagicMock()
        mock_airport = MagicMock()
        mock_airport.position = Vector3(-122.0, 10.0, 37.5)

        mock_runway = MagicMock()
        mock_runway.le_ident = "09"
        mock_runway.he_ident = "27"
        mock_runway.le_heading_deg = 90.0
        mock_runway.he_heading_deg = 270.0
        mock_runway.le_latitude = 37.5
        mock_runway.le_longitude = -122.01
        mock_runway.he_latitude = 37.5
        mock_runway.he_longitude = -122.0
        mock_runway.width_ft = 75.0

        mock_db.get_runways.return_value = [mock_runway]
        mock_db.get_airport.return_value = mock_airport
        mock_db.get_gateway_data.return_value = None

        loader = AirportLayoutLoader()
        layout = loader.load("TEST", mock_db)

        assert len(layout.hold_short_points) == 1
        hold_short = layout.hold_short_points[0]
        assert hold_short.taxiway_name == "A"
        assert "09" in hold_short.runway_id or "27" in hold_short.runway_id

    def test_no_runway_raises_error(self) -> None:
        """Test that loading airport with no runways raises error."""
        mock_db = MagicMock()
        mock_db.get_runways.return_value = []
        mock_db.get_gateway_data.return_value = None

        loader = AirportLayoutLoader()

        with pytest.raises(ValueError, match="No runway data"):
            loader.load("TEST", mock_db)


class TestAirportLayoutLoaderGateway:
    """Test AirportLayoutLoader with Gateway data."""

    def test_load_from_gateway(self) -> None:
        """Test loading layout from Gateway data."""
        mock_db = MagicMock()

        # Create mock gateway data
        mock_gateway = MagicMock()
        mock_gateway.elevation_ft = 100.0

        # Mock runway
        mock_gw_runway = MagicMock()
        mock_gw_runway.id1 = "13"
        mock_gw_runway.id2 = "31"
        mock_gw_runway.width_m = 23.0
        mock_gw_runway.lat1 = 37.46
        mock_gw_runway.lon1 = -122.12
        mock_gw_runway.lat2 = 37.47
        mock_gw_runway.lon2 = -122.10
        mock_gw_runway.heading1 = 130.0
        mock_gw_runway.heading2 = 310.0
        mock_gateway.runways = [mock_gw_runway]

        # Mock taxi nodes
        mock_node_1 = MagicMock()
        mock_node_1.id = 1
        mock_node_1.latitude = 37.465
        mock_node_1.longitude = -122.11
        mock_node_1.is_hold_short = False
        mock_node_1.on_runway = ""

        mock_node_2 = MagicMock()
        mock_node_2.id = 2
        mock_node_2.latitude = 37.465
        mock_node_2.longitude = -122.115
        mock_node_2.is_hold_short = True
        mock_node_2.on_runway = "13/31"

        mock_gateway.taxi_nodes = {1: mock_node_1, 2: mock_node_2}

        # Mock taxi edges
        mock_edge = MagicMock()
        mock_edge.node_begin = 1
        mock_edge.node_end = 2
        mock_edge.name = "A"
        mock_edge.is_runway = False
        mock_edge.width_code = "C"
        mock_gateway.taxi_edges = [mock_edge]

        # Mock parking
        mock_parking = MagicMock()
        mock_parking.id = "N17"
        mock_parking.latitude = 37.464
        mock_parking.longitude = -122.116
        mock_parking.heading = 130.0
        mock_parking.type = "tie_down"
        mock_gateway.parking_positions = [mock_parking]

        mock_db.get_gateway_data.return_value = mock_gateway

        loader = AirportLayoutLoader()
        layout = loader.load("KPAO", mock_db)

        assert layout.is_generated is False
        assert layout.icao == "KPAO"

        # Check runways (both directions)
        assert len(layout.runways) == 2
        rwy13 = layout.get_runway("13")
        rwy31 = layout.get_runway("31")
        assert rwy13 is not None
        assert rwy31 is not None

        # Check taxiway
        assert len(layout.taxiways) == 1
        taxiway_a = layout.get_taxiway("A")
        assert taxiway_a is not None
        assert len(taxiway_a.segments) == 1
        assert taxiway_a.segments[0].width_m == 15.0  # Width code C

        # Check parking
        assert len(layout.parking) == 1
        assert layout.parking[0].id == "N17"

        # Check hold short
        assert len(layout.hold_short_points) == 1
        assert layout.hold_short_points[0].runway_id == "13/31"
        assert layout.hold_short_points[0].taxiway_name == "A"
