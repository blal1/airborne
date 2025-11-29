"""Unit tests for orientation audio manager."""

import time

import pytest

from airborne.audio.orientation import OrientationAudioManager, ProximityAlert
from airborne.core.messaging import Message, MessageQueue, MessageTopic
from airborne.physics.vectors import Vector3
from airborne.plugins.navigation.position_tracker import (
    ApproachingJunction,
    HoldShortPoint,
    LocationType,
)


@pytest.fixture
def message_queue() -> MessageQueue:
    """Create a test message queue."""
    return MessageQueue()


@pytest.fixture
def manager(message_queue: MessageQueue) -> OrientationAudioManager:
    """Create a test orientation audio manager."""
    return OrientationAudioManager(message_queue, cooldown_seconds=2.0)


class TestProximityAlert:
    """Test ProximityAlert dataclass."""

    def test_create_proximity_alert(self) -> None:
        """Test creating a proximity alert."""
        alert = ProximityAlert("runway", "31", [100.0, 50.0, 20.0])

        assert alert.feature_type == "runway"
        assert alert.feature_id == "31"
        assert alert.distances_m == [100.0, 50.0, 20.0]
        assert alert.last_announced_distance is None
        assert alert.last_announce_time == 0.0


class TestOrientationAudioManager:
    """Test OrientationAudioManager class."""

    def test_create_manager(self, message_queue: MessageQueue) -> None:
        """Test creating an orientation audio manager."""
        manager = OrientationAudioManager(message_queue, cooldown_seconds=3.0)

        assert manager.message_queue == message_queue
        assert manager.cooldown_seconds == 3.0
        assert manager.last_location_type is None
        assert manager.last_location_id == ""
        assert len(manager.proximity_alerts) == 0

    def test_create_manager_without_queue(self) -> None:
        """Test creating manager without message queue."""
        manager = OrientationAudioManager(None)

        assert manager.message_queue is None
        assert manager.cooldown_seconds == 5.0

    def test_subscribe_to_events(self, manager: OrientationAudioManager) -> None:
        """Test subscribing to location events."""
        # Should not raise exception
        manager.subscribe_to_events()
        manager.unsubscribe_from_events()

    def test_handle_location_change_taxiway(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test handling taxiway location change."""
        manager.handle_location_change(LocationType.TAXIWAY, "A")

        # Should publish TTS message
        processed = message_queue.process()
        assert processed == 1

        # Verify state updated
        assert manager.last_location_type == LocationType.TAXIWAY
        assert manager.last_location_id == "A"

    def test_handle_location_change_runway(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test handling runway location change."""
        manager.handle_location_change(LocationType.RUNWAY, "31")

        # Should publish TTS message
        processed = message_queue.process()
        assert processed == 1

        assert manager.last_location_type == LocationType.RUNWAY
        assert manager.last_location_id == "31"

    def test_handle_location_change_parking(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test handling parking location change."""
        manager.handle_location_change(LocationType.PARKING, "G1")

        processed = message_queue.process()
        assert processed == 1

        assert manager.last_location_type == LocationType.PARKING
        assert manager.last_location_id == "G1"

    def test_handle_location_change_apron(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test handling apron location change."""
        manager.handle_location_change(LocationType.APRON, "APRON1")

        processed = message_queue.process()
        assert processed == 1

    def test_handle_location_change_grass(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test handling grass location change."""
        manager.handle_location_change(LocationType.GRASS, "")

        processed = message_queue.process()
        assert processed == 1

    def test_cooldown_suppresses_duplicate(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test that cooldown suppresses duplicate announcements."""
        # First announcement should work
        manager.handle_location_change(LocationType.TAXIWAY, "A")
        assert message_queue.process() == 1

        # Second announcement within cooldown should be suppressed
        manager.handle_location_change(LocationType.TAXIWAY, "B")
        assert message_queue.process() == 0

        # Wait for cooldown
        time.sleep(2.1)

        # Third announcement after cooldown should work
        manager.handle_location_change(LocationType.TAXIWAY, "C")
        assert message_queue.process() == 1

    def test_duplicate_location_suppressed(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test that exact duplicate locations are suppressed."""
        manager.handle_location_change(LocationType.TAXIWAY, "A")
        message_queue.process()

        # Wait for cooldown
        time.sleep(2.1)

        # Same location should be suppressed even after cooldown
        manager.handle_location_change(LocationType.TAXIWAY, "A")
        assert message_queue.process() == 0

    def test_handle_approaching_feature_runway(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test approaching runway announcements."""
        # Start at 150m - no announcement
        manager.handle_approaching_feature("runway", "31", 150.0)
        assert message_queue.process() == 0

        # At 100m - should announce
        manager.handle_approaching_feature("runway", "31", 100.0)
        assert message_queue.process() == 1

        # At 75m - no announcement (between thresholds)
        manager.handle_approaching_feature("runway", "31", 75.0)
        assert message_queue.process() == 0

        # At 50m - should announce
        manager.handle_approaching_feature("runway", "31", 50.0)
        assert message_queue.process() == 1

        # At 20m - should announce
        manager.handle_approaching_feature("runway", "31", 20.0)
        assert message_queue.process() == 1

        # At 10m - no announcement (passed all thresholds)
        manager.handle_approaching_feature("runway", "31", 10.0)
        assert message_queue.process() == 0

    def test_approaching_feature_creates_alert(self, manager: OrientationAudioManager) -> None:
        """Test that approaching feature creates proximity alert."""
        assert len(manager.proximity_alerts) == 0

        manager.handle_approaching_feature("runway", "31", 100.0)

        assert len(manager.proximity_alerts) == 1
        assert "runway:31" in manager.proximity_alerts

    def test_approaching_feature_clears_alert_when_passed(
        self, manager: OrientationAudioManager
    ) -> None:
        """Test that proximity alert is cleared after passing."""
        manager.handle_approaching_feature("runway", "31", 100.0)
        assert len(manager.proximity_alerts) == 1

        # Pass all thresholds
        manager.handle_approaching_feature("runway", "31", 10.0)

        # Alert should be cleared
        assert len(manager.proximity_alerts) == 0

    def test_announce_current_position(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test manual position announcement."""
        manager.announce_current_position(LocationType.TAXIWAY, "A")

        # Should publish high-priority message
        processed = message_queue.process()
        assert processed == 1

    def test_announce_current_position_with_vector(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test manual position announcement with position vector."""
        position = Vector3(-122.0, 10.0, 37.5)
        manager.announce_current_position(LocationType.TAXIWAY, "A", position)

        processed = message_queue.process()
        assert processed == 1

    def test_announce_directional_cue(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test directional taxiway announcement."""
        manager.announce_directional_cue("left", "B")

        processed = message_queue.process()
        assert processed == 1

    def test_phonetic_conversion_single_letter(self) -> None:
        """Test converting single letters to phonetic."""
        assert OrientationAudioManager._to_phonetic("A") == "Alpha"
        assert OrientationAudioManager._to_phonetic("B") == "Bravo"
        assert OrientationAudioManager._to_phonetic("C") == "Charlie"
        assert OrientationAudioManager._to_phonetic("Z") == "Zulu"

    def test_phonetic_conversion_lowercase(self) -> None:
        """Test phonetic conversion with lowercase."""
        assert OrientationAudioManager._to_phonetic("a") == "Alpha"
        assert OrientationAudioManager._to_phonetic("z") == "Zulu"

    def test_phonetic_conversion_multi_char(self) -> None:
        """Test phonetic conversion for multi-character identifiers."""
        result = OrientationAudioManager._to_phonetic("A1")
        assert "Alpha" in result
        assert "1" in result

    def test_phonetic_conversion_number(self) -> None:
        """Test phonetic conversion for numbers."""
        result = OrientationAudioManager._to_phonetic("31")
        assert "31" in result or "3 1" in result

    def test_generate_taxiway_message(self, manager: OrientationAudioManager) -> None:
        """Test generating taxiway location message."""
        message = manager._generate_location_message(LocationType.TAXIWAY, "A")
        assert "taxiway" in message.lower()
        assert "Alpha" in message

    def test_generate_runway_message(self, manager: OrientationAudioManager) -> None:
        """Test generating runway location message."""
        message = manager._generate_location_message(LocationType.RUNWAY, "31")
        assert "runway" in message.lower()
        # Runway numbers are converted to phonetic (digits separated by spaces)
        assert "3" in message and "1" in message

    def test_generate_parking_message(self, manager: OrientationAudioManager) -> None:
        """Test generating parking location message."""
        message = manager._generate_location_message(LocationType.PARKING, "G1")
        assert "parking" in message.lower()
        assert "G1" in message

    def test_generate_apron_message(self, manager: OrientationAudioManager) -> None:
        """Test generating apron location message."""
        message = manager._generate_location_message(LocationType.APRON, "")
        assert "apron" in message.lower()

    def test_generate_grass_message(self, manager: OrientationAudioManager) -> None:
        """Test generating grass location message."""
        message = manager._generate_location_message(LocationType.GRASS, "")
        assert "pavement" in message.lower() or "off" in message.lower()

    def test_generate_unknown_message(self, manager: OrientationAudioManager) -> None:
        """Test generating unknown location message."""
        message = manager._generate_location_message(LocationType.UNKNOWN, "")
        assert "unknown" in message.lower()

    def test_generate_approaching_runway_message(self, manager: OrientationAudioManager) -> None:
        """Test generating approaching runway message."""
        message = manager._generate_approaching_message("runway", "31", 50.0)
        assert "approaching" in message.lower()
        assert "runway" in message.lower()
        assert "50" in message

    def test_generate_approaching_intersection_message(
        self, manager: OrientationAudioManager
    ) -> None:
        """Test generating approaching intersection message."""
        message = manager._generate_approaching_message("intersection", "A", 100.0)
        assert "approaching" in message.lower()
        assert "intersection" in message.lower()
        assert "100" in message

    def test_on_location_changed_message(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test handling location changed message from queue."""
        # Create location change message
        msg = Message(
            sender="position_tracker",
            recipients=["orientation_audio"],
            topic="navigation.entered_taxiway",
            data={"location_type": "taxiway", "location_id": "A"},
        )

        # Handle message
        manager._on_location_changed(msg)

        # Should publish announcement
        processed = message_queue.process()
        assert processed == 1

    def test_on_location_changed_invalid_type(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test handling message with invalid location type."""
        msg = Message(
            sender="position_tracker",
            recipients=["orientation_audio"],
            topic="navigation.location_changed",
            data={"location_type": "invalid_type", "location_id": "X"},
        )

        # Should not crash
        manager._on_location_changed(msg)

        # Should not publish announcement
        assert message_queue.process() == 0

    def test_manager_without_queue_does_not_crash(self) -> None:
        """Test that manager without queue handles calls gracefully."""
        manager = OrientationAudioManager(None)

        # Should not crash
        manager.subscribe_to_events()
        manager.handle_location_change(LocationType.TAXIWAY, "A")
        manager.announce_current_position(LocationType.RUNWAY, "31")
        manager.unsubscribe_from_events()

    def test_multiple_proximity_alerts(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test multiple simultaneous proximity alerts."""
        # Add alerts for two different runways
        manager.handle_approaching_feature("runway", "31", 100.0)
        manager.handle_approaching_feature("runway", "13", 100.0)

        # Should have two alerts
        assert len(manager.proximity_alerts) == 2

        # Should publish two messages
        assert message_queue.process() == 2

    def test_approaching_same_feature_multiple_times(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test approaching same feature multiple times."""
        # First approach at 100m
        manager.handle_approaching_feature("runway", "31", 100.0)
        assert message_queue.process() == 1

        # Still at 100m - should not announce again
        manager.handle_approaching_feature("runway", "31", 100.0)
        assert message_queue.process() == 0

        # Getting closer to 50m
        manager.handle_approaching_feature("runway", "31", 60.0)
        assert message_queue.process() == 0

        # Reached 50m threshold
        manager.handle_approaching_feature("runway", "31", 50.0)
        assert message_queue.process() == 1


class TestSpatialAnnouncements:
    """Test spatial (panned) announcements."""

    def test_announce_junction_spatial_taxiway(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test spatial taxiway junction announcement."""
        junction = ApproachingJunction(
            name="B",
            junction_type="taxiway",
            distance_m=50.0,
            direction="left",
            position=Vector3(-122.001, 10.0, 37.5),
        )
        listener_pos = Vector3(-122.0, 10.0, 37.5)
        listener_heading = 0.0  # Facing north

        manager.announce_junction_spatial(junction, listener_pos, listener_heading)

        # Should publish spatial TTS message
        processed = message_queue.process()
        assert processed == 1

    def test_announce_junction_spatial_runway(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test spatial runway junction announcement."""
        junction = ApproachingJunction(
            name="31",
            junction_type="runway",
            distance_m=75.0,
            direction="ahead",
            position=Vector3(-122.0, 10.0, 37.51),
        )
        listener_pos = Vector3(-122.0, 10.0, 37.5)
        listener_heading = 0.0

        manager.announce_junction_spatial(junction, listener_pos, listener_heading)

        processed = message_queue.process()
        assert processed == 1

    def test_relative_position_ahead(self, manager: OrientationAudioManager) -> None:
        """Test relative position calculation for ahead direction."""
        listener_pos = Vector3(-122.0, 10.0, 37.5)
        listener_heading = 0.0  # Facing north
        target_pos = Vector3(-122.0, 10.0, 37.501)  # North of listener

        rel_pos = manager._get_relative_position(listener_pos, listener_heading, target_pos)

        # Target is ahead, so z should be positive, x should be ~0
        assert rel_pos.z > 0
        assert abs(rel_pos.x) < 1.0

    def test_relative_position_left(self, manager: OrientationAudioManager) -> None:
        """Test relative position calculation for left direction."""
        listener_pos = Vector3(-122.0, 10.0, 37.5)
        listener_heading = 0.0  # Facing north
        target_pos = Vector3(-122.001, 10.0, 37.5)  # West of listener

        rel_pos = manager._get_relative_position(listener_pos, listener_heading, target_pos)

        # Target is to the left (west), so x should be negative
        assert rel_pos.x < 0

    def test_relative_position_right(self, manager: OrientationAudioManager) -> None:
        """Test relative position calculation for right direction."""
        listener_pos = Vector3(-122.0, 10.0, 37.5)
        listener_heading = 0.0  # Facing north
        target_pos = Vector3(-121.999, 10.0, 37.5)  # East of listener

        rel_pos = manager._get_relative_position(listener_pos, listener_heading, target_pos)

        # Target is to the right (east), so x should be positive
        assert rel_pos.x > 0

    def test_relative_position_rotated_heading(self, manager: OrientationAudioManager) -> None:
        """Test relative position with rotated heading."""
        listener_pos = Vector3(-122.0, 10.0, 37.5)
        listener_heading = 90.0  # Facing east
        target_pos = Vector3(-122.0, 10.0, 37.501)  # North of listener

        rel_pos = manager._get_relative_position(listener_pos, listener_heading, target_pos)

        # Listener faces east, north is now to the left
        assert rel_pos.x < 0

    def test_relative_position_capped_distance(self, manager: OrientationAudioManager) -> None:
        """Test that relative position distance is capped at 50m."""
        listener_pos = Vector3(-122.0, 10.0, 37.5)
        listener_heading = 0.0
        # Target 1km away (0.01 degrees ≈ 1110m)
        target_pos = Vector3(-122.0, 10.0, 37.51)  # ~1110m north

        rel_pos = manager._get_relative_position(listener_pos, listener_heading, target_pos)

        # Distance should be capped
        import math
        distance = math.sqrt(rel_pos.x**2 + rel_pos.z**2)
        assert distance <= 50.1  # Allow small floating point error

    def test_announce_spatial_without_queue(self) -> None:
        """Test spatial announcement without message queue."""
        manager = OrientationAudioManager(None)

        junction = ApproachingJunction(
            name="A",
            junction_type="taxiway",
            distance_m=50.0,
            direction="left",
            position=Vector3(-122.0, 10.0, 37.5),
        )

        # Should not crash
        manager.announce_junction_spatial(
            junction,
            Vector3(-122.0, 10.0, 37.5),
            0.0
        )


class TestHoldShortAnnouncements:
    """Test hold short warning announcements."""

    def test_announce_hold_short_normal(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test normal hold short announcement (50m distance)."""
        hold_short = HoldShortPoint(
            runway_id="31",
            position=Vector3(-122.0, 10.0, 37.5),
            taxiway_name="A",
            distance_m=50.0,
        )

        manager.announce_hold_short(hold_short)

        processed = message_queue.process()
        assert processed == 1

    def test_announce_hold_short_high(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test high urgency hold short announcement (20m distance)."""
        hold_short = HoldShortPoint(
            runway_id="27L",
            position=Vector3(-122.0, 10.0, 37.5),
            taxiway_name="B",
            distance_m=20.0,
        )

        manager.announce_hold_short(hold_short)

        processed = message_queue.process()
        assert processed == 1

    def test_announce_hold_short_critical(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test critical hold short announcement (10m distance)."""
        hold_short = HoldShortPoint(
            runway_id="09",
            position=Vector3(-122.0, 10.0, 37.5),
            taxiway_name="C",
            distance_m=10.0,
        )

        manager.announce_hold_short(hold_short)

        processed = message_queue.process()
        assert processed == 1

    def test_hold_short_without_queue(self) -> None:
        """Test hold short announcement without message queue."""
        manager = OrientationAudioManager(None)

        hold_short = HoldShortPoint(
            runway_id="31",
            position=Vector3(-122.0, 10.0, 37.5),
            taxiway_name="A",
            distance_m=25.0,
        )

        # Should not crash
        manager.announce_hold_short(hold_short)
