"""Tests for Ground Navigation Manager."""

from unittest.mock import MagicMock

import pytest

from airborne.airports.layout import (
    AirportLayout,
    LayoutRunway,
    LayoutTaxiway,
    TaxiwaySegment,
)
from airborne.audio.centerline import CenterlineBeepManager
from airborne.audio.orientation import OrientationAudioManager
from airborne.navigation.ground_navigation import (
    GroundNavigationConfig,
    GroundNavigationManager,
)
from airborne.physics.vectors import Vector3
from airborne.plugins.navigation.position_tracker import (
    ApproachingJunction,
    HoldShortPoint,
    LocationType,
    PositionTracker,
)


@pytest.fixture
def mock_position_tracker() -> MagicMock:
    """Create mock position tracker."""
    tracker = MagicMock(spec=PositionTracker)
    tracker.position_history = [(Vector3(-122.0, 10.0, 37.5), 270.0)]
    tracker.get_current_location.return_value = (LocationType.TAXIWAY, "A")
    tracker.get_centerline_deviation.return_value = (1.0, "left")
    tracker.get_approaching_junctions.return_value = []
    tracker.get_approaching_hold_short.return_value = None
    return tracker


@pytest.fixture
def mock_orientation_audio() -> MagicMock:
    """Create mock orientation audio manager."""
    return MagicMock(spec=OrientationAudioManager)


@pytest.fixture
def mock_centerline_beep() -> MagicMock:
    """Create mock centerline beep manager."""
    return MagicMock(spec=CenterlineBeepManager)


@pytest.fixture
def sample_layout() -> AirportLayout:
    """Create sample airport layout."""
    layout = AirportLayout(icao="TEST")

    layout.runways.append(
        LayoutRunway(
            id="27",
            threshold_pos=Vector3(-122.01, 10.0, 37.5),
            end_pos=Vector3(-121.99, 10.0, 37.5),
            width_m=30.0,
            heading=270.0,
        )
    )

    layout.taxiways.append(
        LayoutTaxiway(
            name="A",
            segments=[
                TaxiwaySegment(
                    start_pos=Vector3(-122.005, 10.0, 37.501),
                    end_pos=Vector3(-122.005, 10.0, 37.5),
                    width_m=15.0,
                )
            ],
        )
    )

    return layout


@pytest.fixture
def manager(
    mock_position_tracker: MagicMock,
    mock_orientation_audio: MagicMock,
    mock_centerline_beep: MagicMock,
    sample_layout: AirportLayout,
) -> GroundNavigationManager:
    """Create ground navigation manager with mocks."""
    return GroundNavigationManager(
        position_tracker=mock_position_tracker,
        orientation_audio=mock_orientation_audio,
        centerline_beep=mock_centerline_beep,
        layout=sample_layout,
    )


class TestGroundNavigationConfig:
    """Test GroundNavigationConfig."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = GroundNavigationConfig()

        assert config.junction_announce_distance_m == 50.0
        assert config.hold_short_thresholds_m == (50.0, 20.0, 10.0)
        assert config.enable_centerline_on_start is False

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = GroundNavigationConfig(
            junction_announce_distance_m=100.0,
            hold_short_thresholds_m=(75.0, 30.0, 15.0),
            enable_centerline_on_start=True,
        )

        assert config.junction_announce_distance_m == 100.0
        assert config.hold_short_thresholds_m == (75.0, 30.0, 15.0)
        assert config.enable_centerline_on_start is True


class TestGroundNavigationManager:
    """Test GroundNavigationManager."""

    def test_create_manager(self, manager: GroundNavigationManager) -> None:
        """Test creating manager."""
        assert manager.layout.icao == "TEST"
        assert not manager.enabled

    def test_enable_disable(self, manager: GroundNavigationManager) -> None:
        """Test enable/disable functionality."""
        assert not manager.enabled

        manager.enable()
        assert manager.enabled

        manager.disable()
        assert not manager.enabled

    def test_update_when_disabled(
        self,
        manager: GroundNavigationManager,
        mock_position_tracker: MagicMock,
    ) -> None:
        """Test that update does nothing when disabled."""
        manager.update(Vector3(-122.0, 10.0, 37.5), 270.0, 100.0)

        # Position tracker should not be updated
        mock_position_tracker.update.assert_not_called()

    def test_update_when_enabled(
        self,
        manager: GroundNavigationManager,
        mock_position_tracker: MagicMock,
        mock_centerline_beep: MagicMock,
    ) -> None:
        """Test that update works when enabled."""
        manager.enable()
        manager.update(Vector3(-122.0, 10.0, 37.5), 270.0, 100.0)

        # Position tracker should be updated
        mock_position_tracker.update.assert_called_once()

        # Centerline beep should be updated
        mock_centerline_beep.update.assert_called_once()

    def test_junction_announcement(
        self,
        manager: GroundNavigationManager,
        mock_position_tracker: MagicMock,
        mock_orientation_audio: MagicMock,
    ) -> None:
        """Test junction announcements."""
        # Set up mock junction
        junction = ApproachingJunction(
            name="B",
            junction_type="taxiway",
            distance_m=40.0,
            direction="left",
            position=Vector3(-122.001, 10.0, 37.5),
        )
        mock_position_tracker.get_approaching_junctions.return_value = [junction]

        manager.enable()
        manager.update(Vector3(-122.0, 10.0, 37.5), 270.0, 100.0)

        # Should announce junction
        mock_orientation_audio.announce_junction_spatial.assert_called_once()

    def test_junction_not_announced_twice(
        self,
        manager: GroundNavigationManager,
        mock_position_tracker: MagicMock,
        mock_orientation_audio: MagicMock,
    ) -> None:
        """Test that same junction isn't announced twice."""
        junction = ApproachingJunction(
            name="B",
            junction_type="taxiway",
            distance_m=40.0,
            direction="left",
            position=Vector3(-122.001, 10.0, 37.5),
        )
        mock_position_tracker.get_approaching_junctions.return_value = [junction]

        manager.enable()

        # First update - should announce
        manager.update(Vector3(-122.0, 10.0, 37.5), 270.0, 100.0)
        assert mock_orientation_audio.announce_junction_spatial.call_count == 1

        # Second update - should not announce again
        manager.update(Vector3(-122.0, 10.0, 37.5), 270.0, 101.0)
        assert mock_orientation_audio.announce_junction_spatial.call_count == 1

    def test_hold_short_announcement(
        self,
        manager: GroundNavigationManager,
        mock_position_tracker: MagicMock,
        mock_orientation_audio: MagicMock,
    ) -> None:
        """Test hold short announcements."""
        hold_short = HoldShortPoint(
            runway_id="27",
            position=Vector3(-122.005, 10.0, 37.5),
            taxiway_name="A",
            distance_m=45.0,
        )
        mock_position_tracker.get_approaching_hold_short.return_value = hold_short

        manager.enable()
        manager.update(Vector3(-122.0, 10.0, 37.5), 270.0, 100.0)

        # Should announce hold short
        mock_orientation_audio.announce_hold_short.assert_called_once()

    def test_hold_short_threshold_progression(
        self,
        manager: GroundNavigationManager,
        mock_position_tracker: MagicMock,
        mock_orientation_audio: MagicMock,
    ) -> None:
        """Test hold short announcements at different thresholds."""
        manager.enable()

        # At 45m - announce at 50m threshold
        hold_short_50 = HoldShortPoint(
            runway_id="27",
            position=Vector3(-122.005, 10.0, 37.5),
            taxiway_name="A",
            distance_m=45.0,
        )
        mock_position_tracker.get_approaching_hold_short.return_value = hold_short_50
        manager.update(Vector3(-122.0, 10.0, 37.5), 270.0, 100.0)
        assert mock_orientation_audio.announce_hold_short.call_count == 1

        # At 18m - announce at 20m threshold
        hold_short_20 = HoldShortPoint(
            runway_id="27",
            position=Vector3(-122.005, 10.0, 37.5),
            taxiway_name="A",
            distance_m=18.0,
        )
        mock_position_tracker.get_approaching_hold_short.return_value = hold_short_20
        manager.update(Vector3(-122.0, 10.0, 37.5), 270.0, 101.0)
        assert mock_orientation_audio.announce_hold_short.call_count == 2

        # At 8m - announce at 10m threshold
        hold_short_10 = HoldShortPoint(
            runway_id="27",
            position=Vector3(-122.005, 10.0, 37.5),
            taxiway_name="A",
            distance_m=8.0,
        )
        mock_position_tracker.get_approaching_hold_short.return_value = hold_short_10
        manager.update(Vector3(-122.0, 10.0, 37.5), 270.0, 102.0)
        assert mock_orientation_audio.announce_hold_short.call_count == 3

    def test_where_am_i(
        self,
        manager: GroundNavigationManager,
        mock_position_tracker: MagicMock,
        mock_orientation_audio: MagicMock,
    ) -> None:
        """Test 'where am I' query."""
        manager.where_am_i()

        # Should call detailed position announcement
        mock_orientation_audio.announce_detailed_position.assert_called_once()

    def test_where_am_i_no_position(
        self,
        manager: GroundNavigationManager,
        mock_position_tracker: MagicMock,
        mock_orientation_audio: MagicMock,
    ) -> None:
        """Test 'where am I' with no position history."""
        mock_position_tracker.position_history = []

        manager.where_am_i()

        # Should not announce
        mock_orientation_audio.announce_detailed_position.assert_not_called()

    def test_enable_centerline_tracking(
        self,
        manager: GroundNavigationManager,
        mock_centerline_beep: MagicMock,
    ) -> None:
        """Test enabling centerline tracking."""
        manager.enable_centerline_tracking(True)
        mock_centerline_beep.enable.assert_called_once()

        manager.enable_centerline_tracking(False)
        mock_centerline_beep.disable.assert_called_once()

    def test_toggle_centerline_tracking(
        self,
        manager: GroundNavigationManager,
        mock_centerline_beep: MagicMock,
    ) -> None:
        """Test toggling centerline tracking."""
        mock_centerline_beep.toggle.return_value = True

        result = manager.toggle_centerline_tracking()

        mock_centerline_beep.toggle.assert_called_once()
        assert result is True

    def test_find_nearest_runway(self, manager: GroundNavigationManager) -> None:
        """Test finding nearest runway."""
        position = Vector3(-122.005, 10.0, 37.5)

        result = manager._find_nearest_runway(position)

        assert result is not None
        runway_id, distance = result
        assert runway_id == "27"
        assert distance > 0

    def test_calculate_distance(self) -> None:
        """Test distance calculation."""
        pos1 = Vector3(-122.0, 10.0, 37.5)
        pos2 = Vector3(-122.001, 10.0, 37.5)

        distance = GroundNavigationManager._calculate_distance(pos1, pos2)

        # 0.001 degrees × 111000 = ~111m
        assert 100 < distance < 120

    def test_disable_disables_centerline(
        self,
        manager: GroundNavigationManager,
        mock_centerline_beep: MagicMock,
    ) -> None:
        """Test that disabling manager disables centerline tracking."""
        manager.enable()
        manager.disable()

        mock_centerline_beep.disable.assert_called_once()

    def test_config_enable_centerline_on_start(
        self,
        mock_position_tracker: MagicMock,
        mock_orientation_audio: MagicMock,
        mock_centerline_beep: MagicMock,
        sample_layout: AirportLayout,
    ) -> None:
        """Test that centerline is enabled on start if configured."""
        config = GroundNavigationConfig(enable_centerline_on_start=True)

        manager = GroundNavigationManager(
            position_tracker=mock_position_tracker,
            orientation_audio=mock_orientation_audio,
            centerline_beep=mock_centerline_beep,
            layout=sample_layout,
            config=config,
        )

        mock_centerline_beep.enable.assert_called_once()
