"""Audio orientation cues for ground navigation.

This module provides audio announcements for position awareness on taxiways,
runways, and parking areas. Announces location changes, approaching events,
and provides manual position queries for blind pilot navigation.

Typical usage:
    from airborne.audio.orientation import OrientationAudioManager

    manager = OrientationAudioManager(message_queue)
    manager.subscribe_to_events()
    manager.handle_location_change(location_type, location_id)
"""

import logging
import math
import time
from dataclasses import dataclass

from airborne.core.messaging import Message, MessagePriority, MessageQueue, MessageTopic
from airborne.physics.vectors import Vector3
from airborne.plugins.navigation.position_tracker import (
    ApproachingJunction,
    HoldShortPoint,
    LocationType,
)

logger = logging.getLogger(__name__)


@dataclass
class ProximityAlert:
    """Alert configuration for approaching features.

    Attributes:
        feature_type: Type of feature (runway, intersection, etc.)
        feature_id: Identifier of the feature
        distances_m: List of distances (meters) to trigger announcements
        last_announced_distance: Last distance at which announcement was made
        last_announce_time: Timestamp of last announcement

    Examples:
        >>> alert = ProximityAlert("runway", "31", [100, 50, 20])
    """

    feature_type: str
    feature_id: str
    distances_m: list[float]
    last_announced_distance: float | None = None
    last_announce_time: float = 0.0


class OrientationAudioManager:
    """Manages audio cues for ground orientation and navigation.

    Provides automatic announcements when entering new areas, approaching
    runways/intersections, and manual position queries. Includes cooldown
    periods to prevent duplicate announcements.

    Attributes:
        message_queue: Queue for publishing TTS messages
        cooldown_seconds: Minimum time between duplicate announcements
        last_location_type: Last announced location type
        last_location_id: Last announced location ID
        last_announcement_time: Timestamp of last announcement
        proximity_alerts: Active proximity alerts for approaching features

    Examples:
        >>> manager = OrientationAudioManager(message_queue)
        >>> manager.subscribe_to_events()
        >>> manager.handle_location_change(LocationType.TAXIWAY, "A")
        Announces: "On taxiway Alpha"
    """

    def __init__(
        self, message_queue: MessageQueue | None = None, cooldown_seconds: float = 5.0
    ) -> None:
        """Initialize orientation audio manager.

        Args:
            message_queue: Message queue for publishing TTS messages
            cooldown_seconds: Minimum seconds between duplicate announcements
        """
        self.message_queue = message_queue
        self.cooldown_seconds = cooldown_seconds

        # Current state
        self.last_location_type: LocationType | None = None
        self.last_location_id: str = ""
        self.last_announcement_time = 0.0

        # Proximity tracking
        self.proximity_alerts: dict[str, ProximityAlert] = {}

        logger.info("OrientationAudioManager initialized (cooldown=%.1fs)", cooldown_seconds)

    def subscribe_to_events(self) -> None:
        """Subscribe to position tracking events.

        Must be called after initialization to receive location change events.
        """
        if not self.message_queue:
            logger.warning("Cannot subscribe to events: no message queue")
            return

        # Subscribe to location change events
        self.message_queue.subscribe("navigation.entered_taxiway", self._on_location_changed)
        self.message_queue.subscribe("navigation.entered_runway", self._on_location_changed)
        self.message_queue.subscribe("navigation.entered_parking", self._on_location_changed)
        self.message_queue.subscribe("navigation.entered_apron", self._on_location_changed)
        self.message_queue.subscribe("navigation.location_changed", self._on_location_changed)

        logger.info("Subscribed to position tracking events")

    def unsubscribe_from_events(self) -> None:
        """Unsubscribe from position tracking events."""
        if not self.message_queue:
            return

        self.message_queue.unsubscribe("navigation.entered_taxiway", self._on_location_changed)
        self.message_queue.unsubscribe("navigation.entered_runway", self._on_location_changed)
        self.message_queue.unsubscribe("navigation.entered_parking", self._on_location_changed)
        self.message_queue.unsubscribe("navigation.entered_apron", self._on_location_changed)
        self.message_queue.unsubscribe("navigation.location_changed", self._on_location_changed)

        logger.info("Unsubscribed from position tracking events")

    def handle_location_change(self, location_type: LocationType, location_id: str) -> None:
        """Handle location change event.

        Args:
            location_type: New location type
            location_id: New location identifier

        Examples:
            >>> manager.handle_location_change(LocationType.TAXIWAY, "A")
        """
        current_time = time.time()

        # Check cooldown
        if not self._check_cooldown(current_time):
            logger.debug("Announcement suppressed by cooldown")
            return

        # Check if this is a duplicate
        if location_type == self.last_location_type and location_id == self.last_location_id:
            logger.debug("Duplicate location announcement suppressed")
            return

        # Update state
        self.last_location_type = location_type
        self.last_location_id = location_id
        self.last_announcement_time = current_time

        # Generate and announce message
        message = self._generate_location_message(location_type, location_id)
        self._announce(message)

    def handle_approaching_feature(
        self, feature_type: str, feature_id: str, distance_m: float
    ) -> None:
        """Handle approaching feature event.

        Announces at configured distances (100m, 50m, 20m by default).

        Args:
            feature_type: Type of feature (runway, intersection, etc.)
            feature_id: Identifier of the feature
            distance_m: Current distance to feature in meters

        Examples:
            >>> manager.handle_approaching_feature("runway", "31", 75.0)
            Announces: "Approaching runway 31, 50 meters"
        """
        alert_id = f"{feature_type}:{feature_id}"

        # Create alert if it doesn't exist
        if alert_id not in self.proximity_alerts:
            self.proximity_alerts[alert_id] = ProximityAlert(
                feature_type=feature_type,
                feature_id=feature_id,
                distances_m=[100.0, 50.0, 20.0],
            )

        alert = self.proximity_alerts[alert_id]

        # Find the appropriate distance threshold
        for threshold in sorted(alert.distances_m, reverse=True):
            if distance_m <= threshold and (
                alert.last_announced_distance is None or threshold < alert.last_announced_distance
            ):
                # Announce at this threshold
                message = self._generate_approaching_message(feature_type, feature_id, threshold)
                self._announce(message)

                alert.last_announced_distance = threshold
                alert.last_announce_time = time.time()
                break

        # Clear alert if we've passed all thresholds
        if distance_m < min(alert.distances_m):
            del self.proximity_alerts[alert_id]

    def announce_current_position(
        self, location_type: LocationType, location_id: str, position: Vector3 | None = None
    ) -> None:
        """Manually announce current position.

        Used for user-initiated position queries (e.g., P key press).

        Args:
            location_type: Current location type
            location_id: Current location identifier
            position: Optional current position for additional context

        Examples:
            >>> manager.announce_current_position(LocationType.TAXIWAY, "A")
        """
        message = self._generate_location_message(location_type, location_id)

        # Add position details if available
        if position:
            # Could add heading, altitude, etc. here if needed
            pass

        self._announce(message, priority=MessagePriority.HIGH)
        logger.info("Manual position query: %s at %s", location_type.value, location_id)

    def announce_directional_cue(self, direction: str, taxiway_name: str) -> None:
        """Announce directional taxiway information.

        Args:
            direction: Direction (left/right)
            taxiway_name: Name of taxiway

        Examples:
            >>> manager.announce_directional_cue("left", "B")
            Announces: "Taxiway Bravo on your left"
        """
        taxiway_phonetic = self._to_phonetic(taxiway_name)
        message = f"Taxiway {taxiway_phonetic} on your {direction}"
        self._announce(message)

    def announce_junction_spatial(
        self,
        junction: ApproachingJunction,
        listener_pos: Vector3,
        listener_heading: float,
    ) -> None:
        """Announce junction with spatial audio (panned TTS).

        The announcement will come from the direction of the junction,
        providing an intuitive spatial cue for navigation.

        Args:
            junction: The approaching junction to announce.
            listener_pos: Current aircraft position.
            listener_heading: Current aircraft heading in degrees.

        Examples:
            >>> manager.announce_junction_spatial(junction, position, heading)
            # If junction is on left, announcement comes from left speaker
        """
        # Calculate 3D position relative to listener
        relative_pos = self._get_relative_position(
            listener_pos, listener_heading, junction.position
        )

        # Generate message
        name_phonetic = self._to_phonetic(junction.name)
        if junction.junction_type == "runway":
            message = f"Runway {name_phonetic}"
        else:
            message = f"Taxiway {name_phonetic}"

        # Queue spatial TTS
        self._announce_spatial(message, relative_pos)

    def _get_relative_position(
        self,
        listener_pos: Vector3,
        listener_heading: float,
        target_pos: Vector3,
    ) -> Vector3:
        """Convert world position to listener-relative position.

        Args:
            listener_pos: Listener's world position.
            listener_heading: Listener's heading in degrees.
            target_pos: Target's world position.

        Returns:
            Position relative to listener (x=right, z=forward).
        """
        # Calculate offset in meters
        # x is longitude (positive = east), z is latitude (positive = north)
        dx = (target_pos.x - listener_pos.x) * 111000.0  # East-west offset
        dz = (target_pos.z - listener_pos.z) * 111000.0  # North-south offset

        # Convert to relative position based on heading
        # Heading 0 = north, 90 = east
        # We want: forward (+z_rel) = in direction of heading
        #          right (+x_rel) = 90 degrees clockwise from heading
        heading_rad = math.radians(listener_heading)

        # For heading 0 (north): forward=north(dz), right=east(dx)
        # For heading 90 (east): forward=east(dx), right=south(-dz)
        # Standard rotation: rotate world coords by -heading to get relative
        cos_h = math.cos(heading_rad)
        sin_h = math.sin(heading_rad)

        # World to relative rotation (clockwise by heading angle)
        rel_x = dx * cos_h - dz * sin_h  # Right component
        rel_z = dx * sin_h + dz * cos_h  # Forward component

        # Normalize distance for audio (cap at reasonable distance)
        distance = math.sqrt(rel_x * rel_x + rel_z * rel_z)
        if distance > 0:
            scale = min(distance, 50.0) / distance  # Cap at 50m for audio
            rel_x *= scale
            rel_z *= scale

        return Vector3(rel_x, 0.0, rel_z)

    def _announce_spatial(
        self, message: str, position: Vector3, priority: MessagePriority = MessagePriority.HIGH
    ) -> None:
        """Announce message from a specific 3D position.

        Args:
            message: Text to announce.
            position: 3D position relative to listener.
            priority: Message priority.
        """
        if not self.message_queue:
            logger.warning("Cannot announce spatial: no message queue")
            return

        tts_message = Message(
            sender="orientation_audio",
            recipients=["audio_plugin"],
            topic=MessageTopic.TTS_SPEAK_SPATIAL,
            data={
                "text": message,
                "voice": "cockpit",
                "position": {"x": position.x, "y": position.y, "z": position.z},
            },
            priority=priority,
        )

        self.message_queue.publish(tts_message)
        logger.info("Announced spatial: %s (pos: %.1f, %.1f)", message, position.x, position.z)

    def announce_hold_short(self, hold_short: HoldShortPoint) -> None:
        """Announce hold short warning.

        Announces at different urgency levels based on distance:
        - 50m: Normal awareness
        - 20m: High urgency
        - 10m: Critical warning

        Args:
            hold_short: The hold short point information.

        Examples:
            >>> manager.announce_hold_short(hold_short_point)
            # "Hold short runway 31" at critical priority
        """
        runway_phonetic = self._to_phonetic(hold_short.runway_id)
        distance = hold_short.distance_m

        if distance <= 10:
            message = f"Hold short runway {runway_phonetic}"
            priority = MessagePriority.CRITICAL
        elif distance <= 20:
            message = f"Approaching hold short, runway {runway_phonetic}"
            priority = MessagePriority.HIGH
        else:  # 50m
            message = f"Hold short runway {runway_phonetic} ahead"
            priority = MessagePriority.NORMAL

        self._announce(message, priority)

    def _on_location_changed(self, msg: Message) -> None:
        """Handle location change message from message queue.

        Args:
            msg: Location change message
        """
        data = msg.data
        location_type_str = data.get("location_type", "unknown")
        location_id = data.get("location_id", "")

        try:
            location_type = LocationType(location_type_str)
        except ValueError:
            logger.warning("Invalid location type: %s", location_type_str)
            return

        self.handle_location_change(location_type, location_id)

    def _generate_location_message(self, location_type: LocationType, location_id: str) -> str:
        """Generate audio message for location.

        Args:
            location_type: Location type
            location_id: Location identifier

        Returns:
            Audio message text
        """
        if location_type == LocationType.TAXIWAY:
            taxiway_phonetic = self._to_phonetic(location_id) if location_id else "unknown"
            return f"On taxiway {taxiway_phonetic}"
        if location_type == LocationType.RUNWAY:
            runway_phonetic = self._to_phonetic(location_id) if location_id else "unknown"
            return f"On runway {runway_phonetic}"
        if location_type == LocationType.PARKING:
            return f"At parking position {location_id}"
        if location_type == LocationType.APRON:
            return "On apron"
        if location_type == LocationType.GRASS:
            return "Off pavement"
        return "Location unknown"

    def _generate_approaching_message(
        self, feature_type: str, feature_id: str, distance_m: float
    ) -> str:
        """Generate approaching feature message.

        Args:
            feature_type: Type of feature
            feature_id: Feature identifier
            distance_m: Distance in meters

        Returns:
            Audio message text
        """
        feature_phonetic = self._to_phonetic(feature_id)

        if feature_type == "runway":
            return f"Approaching runway {feature_phonetic}, {int(distance_m)} meters"
        if feature_type == "intersection":
            return f"Approaching {feature_phonetic} intersection, {int(distance_m)} meters"
        return f"Approaching {feature_type} {feature_phonetic}, {int(distance_m)} meters"

    def _announce(self, message: str, priority: MessagePriority = MessagePriority.NORMAL) -> None:
        """Publish TTS announcement message.

        Args:
            message: Text to announce
            priority: Message priority
        """
        if not self.message_queue:
            logger.warning("Cannot announce: no message queue")
            return

        tts_message = Message(
            sender="orientation_audio",
            recipients=["audio_plugin"],
            topic=MessageTopic.TTS_SPEAK,
            data={"text": message, "voice": "cockpit", "interrupt": False},
            priority=priority,
        )

        self.message_queue.publish(tts_message)
        logger.info("Announced: %s", message)

    def _check_cooldown(self, current_time: float) -> bool:
        """Check if cooldown period has passed.

        Args:
            current_time: Current timestamp

        Returns:
            True if announcement is allowed, False if in cooldown
        """
        time_since_last = current_time - self.last_announcement_time
        return time_since_last >= self.cooldown_seconds

    @staticmethod
    def _to_phonetic(identifier: str) -> str:
        """Convert identifier to phonetic pronunciation.

        Args:
            identifier: Taxiway/runway identifier

        Returns:
            Phonetic pronunciation

        Examples:
            >>> OrientationAudioManager._to_phonetic("A")
            'Alpha'
            >>> OrientationAudioManager._to_phonetic("31")
            '31'
        """
        # Phonetic alphabet mapping
        phonetic_map = {
            "A": "Alpha",
            "B": "Bravo",
            "C": "Charlie",
            "D": "Delta",
            "E": "Echo",
            "F": "Foxtrot",
            "G": "Golf",
            "H": "Hotel",
            "I": "India",
            "J": "Juliet",
            "K": "Kilo",
            "L": "Lima",
            "M": "Mike",
            "N": "November",
            "O": "Oscar",
            "P": "Papa",
            "Q": "Quebec",
            "R": "Romeo",
            "S": "Sierra",
            "T": "Tango",
            "U": "Uniform",
            "V": "Victor",
            "W": "Whiskey",
            "X": "X-ray",
            "Y": "Yankee",
            "Z": "Zulu",
        }

        # Handle single letter taxiways
        if len(identifier) == 1 and identifier.upper() in phonetic_map:
            return phonetic_map[identifier.upper()]

        # Handle multi-character identifiers (e.g., "A1", "B2")
        result = ""
        for char in identifier.upper():
            if char in phonetic_map:
                result += phonetic_map[char] + " "
            else:
                result += char + " "

        return result.strip()
