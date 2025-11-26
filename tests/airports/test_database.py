"""Tests for Airport Database with X-Plane Gateway integration."""

from unittest.mock import patch

import pytest

from airborne.airports.database import (
    AirportDatabase,
    AirportType,
    FrequencyType,
    SurfaceType,
)
from airborne.physics.vectors import Vector3
from airborne.services.atc.gateway_loader import (
    GatewayAirportData,
    GatewayFrequency,
    GatewayRunway,
)
from airborne.services.atc.gateway_loader import (
    ParkingPosition as GatewayParkingPosition,
)


class TestAirportDatabaseGatewayLoading:
    """Test loading airport data from X-Plane Gateway."""

    @pytest.fixture
    def mock_gateway_data(self) -> GatewayAirportData:
        """Create mock gateway airport data."""
        return GatewayAirportData(
            icao="KSFO",
            name="San Francisco International",
            latitude=37.618972,
            longitude=-122.374889,
            elevation_ft=13.0,
            transition_altitude=18000,
            has_atc=True,
            runways=[
                GatewayRunway(
                    id1="28L",
                    id2="10R",
                    width_m=60.0,
                    lat1=37.617222,
                    lon1=-122.396111,
                    lat2=37.620278,
                    lon2=-122.359444,
                    heading1=284.0,
                    heading2=104.0,
                    surface=1,
                ),
            ],
            frequencies=[
                GatewayFrequency(type="TOWER", frequency_mhz=120.5, name="SFO Tower"),
                GatewayFrequency(type="GROUND", frequency_mhz=121.8, name="SFO Ground"),
                GatewayFrequency(type="ATIS", frequency_mhz=118.85, name="SFO ATIS"),
            ],
            parking_positions=[
                GatewayParkingPosition(
                    id="Gate A1",
                    latitude=37.615,
                    longitude=-122.390,
                    heading=90.0,
                    type="gate",
                ),
            ],
        )

    def test_load_airport_from_gateway(self, mock_gateway_data: GatewayAirportData) -> None:
        """Test loading airport data from Gateway."""
        db = AirportDatabase()

        with patch.object(db.gateway_loader, "get_airport", return_value=mock_gateway_data):
            airport = db.get_airport("KSFO")

        assert airport is not None
        assert airport.icao == "KSFO"
        assert airport.name == "San Francisco International"

    def test_airport_cached_after_load(self, mock_gateway_data: GatewayAirportData) -> None:
        """Test airport is cached after first load."""
        db = AirportDatabase()

        with patch.object(db.gateway_loader, "get_airport", return_value=mock_gateway_data) as mock:
            # First call loads from gateway
            db.get_airport("KSFO")
            # Second call should use cache
            db.get_airport("KSFO")

        # Should only have been called once
        assert mock.call_count == 1

    def test_airport_position_correct(self, mock_gateway_data: GatewayAirportData) -> None:
        """Test airport position is correctly parsed."""
        db = AirportDatabase()

        with patch.object(db.gateway_loader, "get_airport", return_value=mock_gateway_data):
            airport = db.get_airport("KSFO")

        assert airport is not None
        # x = longitude, z = latitude, y = elevation in meters
        assert abs(airport.position.x - (-122.374889)) < 0.001
        assert abs(airport.position.z - 37.618972) < 0.001
        elevation_m = 13.0 * 0.3048
        assert abs(airport.position.y - elevation_m) < 0.1

    def test_airport_type_from_atc(self, mock_gateway_data: GatewayAirportData) -> None:
        """Test airport type determined from ATC presence."""
        db = AirportDatabase()

        with patch.object(db.gateway_loader, "get_airport", return_value=mock_gateway_data):
            airport = db.get_airport("KSFO")

        assert airport is not None
        assert airport.airport_type == AirportType.MEDIUM_AIRPORT

    def test_airport_without_atc_is_small(self) -> None:
        """Test airport without ATC is classified as small."""
        db = AirportDatabase()
        data = GatewayAirportData(
            icao="KPAO",
            name="Palo Alto Airport",
            latitude=37.461111,
            longitude=-122.115000,
            elevation_ft=7.0,
            transition_altitude=18000,
            has_atc=False,
            runways=[],
            frequencies=[],
            parking_positions=[],
        )

        with patch.object(db.gateway_loader, "get_airport", return_value=data):
            airport = db.get_airport("KPAO")

        assert airport is not None
        assert airport.airport_type == AirportType.SMALL_AIRPORT


class TestRunwayLoading:
    """Test runway data loading from Gateway."""

    @pytest.fixture
    def mock_gateway_data(self) -> GatewayAirportData:
        """Create mock gateway data with runways."""
        runway_28l = GatewayRunway(
            id1="28L",
            id2="10R",
            width_m=60.0,
            lat1=37.617222,
            lon1=-122.396111,
            lat2=37.620278,
            lon2=-122.359444,
            heading1=284.0,
            heading2=104.0,
            surface=1,  # Asphalt
        )
        return GatewayAirportData(
            icao="KSFO",
            name="San Francisco International",
            latitude=37.618972,
            longitude=-122.374889,
            elevation_ft=13.0,
            transition_altitude=18000,
            has_atc=True,
            runways=[runway_28l],
            frequencies=[],
            parking_positions=[],
        )

    def test_get_runways(self, mock_gateway_data: GatewayAirportData) -> None:
        """Test getting runways for an airport."""
        db = AirportDatabase()

        with patch.object(db.gateway_loader, "get_airport", return_value=mock_gateway_data):
            runways = db.get_runways("KSFO")

        assert len(runways) == 1
        assert runways[0].runway_id == "28L/10R"

    def test_runway_surface_type(self, mock_gateway_data: GatewayAirportData) -> None:
        """Test runway surface type is correctly mapped."""
        db = AirportDatabase()

        with patch.object(db.gateway_loader, "get_airport", return_value=mock_gateway_data):
            runways = db.get_runways("KSFO")

        assert runways[0].surface == SurfaceType.ASPH

    def test_runway_headings(self, mock_gateway_data: GatewayAirportData) -> None:
        """Test runway heading data."""
        db = AirportDatabase()

        with patch.object(db.gateway_loader, "get_airport", return_value=mock_gateway_data):
            runways = db.get_runways("KSFO")

        rwy = runways[0]
        assert rwy.le_ident == "28L"
        assert abs(rwy.le_heading_deg - 284.0) < 0.1
        assert rwy.he_ident == "10R"
        assert abs(rwy.he_heading_deg - 104.0) < 0.1

    def test_get_runways_nonexistent_airport(self) -> None:
        """Test getting runways for nonexistent airport returns empty list."""
        db = AirportDatabase()

        with patch.object(db.gateway_loader, "get_airport", return_value=None):
            runways = db.get_runways("XXXX")

        assert runways == []


class TestFrequencyLoading:
    """Test frequency data loading from Gateway."""

    @pytest.fixture
    def mock_gateway_data(self) -> GatewayAirportData:
        """Create mock gateway data with frequencies."""
        return GatewayAirportData(
            icao="KSFO",
            name="San Francisco International",
            latitude=37.618972,
            longitude=-122.374889,
            elevation_ft=13.0,
            transition_altitude=18000,
            has_atc=True,
            runways=[],
            frequencies=[
                GatewayFrequency(type="TOWER", frequency_mhz=120.5, name="SFO Tower"),
                GatewayFrequency(type="GROUND", frequency_mhz=121.8, name="SFO Ground"),
                GatewayFrequency(type="ATIS", frequency_mhz=118.85, name="SFO ATIS"),
                GatewayFrequency(type="APPROACH", frequency_mhz=124.0, name="NorCal Approach"),
            ],
            parking_positions=[],
        )

    def test_get_frequencies(self, mock_gateway_data: GatewayAirportData) -> None:
        """Test getting frequencies for an airport."""
        db = AirportDatabase()

        with patch.object(db.gateway_loader, "get_airport", return_value=mock_gateway_data):
            freqs = db.get_frequencies("KSFO")

        assert len(freqs) == 4

    def test_frequency_conversion(self, mock_gateway_data: GatewayAirportData) -> None:
        """Test frequency type conversion from Gateway format."""
        db = AirportDatabase()

        with patch.object(db.gateway_loader, "get_airport", return_value=mock_gateway_data):
            freqs = db.get_frequencies("KSFO")

        # Find tower frequency
        tower = next((f for f in freqs if f.freq_type == FrequencyType.TWR), None)
        assert tower is not None
        assert tower.frequency_mhz == 120.5
        assert tower.description == "SFO Tower"

        # Find ground frequency
        ground = next((f for f in freqs if f.freq_type == FrequencyType.GND), None)
        assert ground is not None
        assert ground.frequency_mhz == 121.8

    def test_get_frequencies_nonexistent_airport(self) -> None:
        """Test getting frequencies for nonexistent airport returns empty list."""
        db = AirportDatabase()

        with patch.object(db.gateway_loader, "get_airport", return_value=None):
            freqs = db.get_frequencies("XXXX")

        assert freqs == []


class TestParkingLoading:
    """Test parking position loading from Gateway."""

    @pytest.fixture
    def mock_gateway_data(self) -> GatewayAirportData:
        """Create mock gateway data with parking."""
        return GatewayAirportData(
            icao="KSFO",
            name="San Francisco International",
            latitude=37.618972,
            longitude=-122.374889,
            elevation_ft=13.0,
            transition_altitude=18000,
            has_atc=True,
            runways=[],
            frequencies=[],
            parking_positions=[
                GatewayParkingPosition(
                    id="Gate A1",
                    latitude=37.615,
                    longitude=-122.390,
                    heading=90.0,
                    type="gate",
                ),
                GatewayParkingPosition(
                    id="Tie Down 1",
                    latitude=37.614,
                    longitude=-122.391,
                    heading=180.0,
                    type="tie_down",
                ),
            ],
        )

    def test_get_parking(self, mock_gateway_data: GatewayAirportData) -> None:
        """Test getting parking positions for an airport."""
        db = AirportDatabase()

        with patch.object(db.gateway_loader, "get_airport", return_value=mock_gateway_data):
            parking = db.get_parking("KSFO")

        assert len(parking) == 2

    def test_parking_position_data(self, mock_gateway_data: GatewayAirportData) -> None:
        """Test parking position data is correctly parsed."""
        db = AirportDatabase()

        with patch.object(db.gateway_loader, "get_airport", return_value=mock_gateway_data):
            parking = db.get_parking("KSFO")

        gate = parking[0]
        assert gate.position_id == "Gate A1"
        assert gate.parking_type == "gate"
        assert abs(gate.heading - 90.0) < 0.1
        assert abs(gate.position.x - (-122.390)) < 0.001
        assert abs(gate.position.z - 37.615) < 0.001

    def test_get_parking_nonexistent_airport(self) -> None:
        """Test getting parking for nonexistent airport returns empty list."""
        db = AirportDatabase()

        with patch.object(db.gateway_loader, "get_airport", return_value=None):
            parking = db.get_parking("XXXX")

        assert parking == []


class TestDeprecatedCSVLoading:
    """Test deprecated CSV loading raises warning."""

    def test_load_from_csv_raises_deprecation(self) -> None:
        """Test load_from_csv raises deprecation warning."""
        db = AirportDatabase()

        with pytest.warns(DeprecationWarning, match="load_from_csv.*no longer supported"):
            db.load_from_csv("/some/path")


class TestHaversineDistance:
    """Test haversine distance calculation."""

    def test_distance_between_known_points(self) -> None:
        """Test distance calculation between known airports."""
        # KPAO: 37.461111, -122.115000
        # KSFO: 37.618972, -122.374889
        # Known distance: ~15 nm

        kpao_pos = Vector3(-122.115, 0, 37.461111)
        ksfo_pos = Vector3(-122.374889, 0, 37.618972)

        distance = AirportDatabase._haversine_distance_nm(kpao_pos, ksfo_pos)

        # Should be approximately 15 nm
        assert 14 < distance < 16

    def test_distance_to_self_is_zero(self) -> None:
        """Test distance from point to itself is zero."""
        pos = Vector3(-122.115, 0, 37.461111)
        distance = AirportDatabase._haversine_distance_nm(pos, pos)
        assert distance < 0.01  # Very close to zero

    def test_distance_symmetric(self) -> None:
        """Test distance is symmetric."""
        pos1 = Vector3(-122.115, 0, 37.461111)
        pos2 = Vector3(-122.374889, 0, 37.618972)

        dist1 = AirportDatabase._haversine_distance_nm(pos1, pos2)
        dist2 = AirportDatabase._haversine_distance_nm(pos2, pos1)

        assert abs(dist1 - dist2) < 0.001


class TestSurfaceTypeMapping:
    """Test surface type mapping from Gateway format."""

    def test_surface_types(self) -> None:
        """Test various surface type mappings."""
        db = AirportDatabase()

        assert db._map_surface_type("asphalt") == SurfaceType.ASPH
        assert db._map_surface_type("Asphalt") == SurfaceType.ASPH
        assert db._map_surface_type("ASPH") == SurfaceType.ASPH
        assert db._map_surface_type("concrete") == SurfaceType.CONC
        assert db._map_surface_type("grass") == SurfaceType.GRASS
        assert db._map_surface_type("turf") == SurfaceType.TURF
        assert db._map_surface_type("dirt") == SurfaceType.DIRT
        assert db._map_surface_type("gravel") == SurfaceType.GRVL
        assert db._map_surface_type("water") == SurfaceType.WATER
        assert db._map_surface_type("unknown_surface") == SurfaceType.UNKNOWN
