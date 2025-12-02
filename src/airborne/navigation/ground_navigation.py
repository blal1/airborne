"""Ground navigation manager for airport surface movement.

This module provides the main integration layer for ground navigation features,
coordinating centerline tracking, junction announcements, hold short warnings,
and position queries.

Typical usage:
    from airborne.navigation.ground_navigation import GroundNavigationManager

    manager = GroundNavigationManager(
        position_tracker=position_tracker,
        orientation_audio=orientation_audio,
        centerline_beep=centerline_beep,
        layout=layout,
    )
    manager.enable()

    # In update loop:
    manager.update(position, heading, timestamp)
"""

import logging
from dataclasses import dataclass

from airborne.airports.layout import AirportLayout
from airborne.audio.centerline import CenterlineBeepManager
from airborne.audio.orientation import OrientationAudioManager
from airborne.physics.vectors import Vector3
from airborne.plugins.navigation.position_tracker import PositionTracker

logger = logging.getLogger(__name__)


@dataclass
class GroundNavigationConfig:
    """Configuration for ground navigation.

    Attributes:
        junction_announce_distance_m: Distance at which to announce junctions.
        hold_short_thresholds_m: Distance thresholds for hold short announcements.
        enable_centerline_on_start: Whether to enable centerline tracking automatically.
    """

    junction_announce_distance_m: float = 50.0
    hold_short_thresholds_m: tuple[float, float, float] = (50.0, 20.0, 10.0)
    enable_centerline_on_start: bool = False


class GroundNavigationManager:
    """Main ground navigation controller.

    Integrates centerline tracking, junction announcements, hold short warnings,
    and position queries into a unified navigation system.

    The manager coordinates between the position tracker, audio managers, and
    airport layout to provide comprehensive ground navigation assistance.

    Attributes:
        position_tracker: Tracks aircraft position on airport surface.
        orientation_audio: Manages audio announcements.
        centerline_beep: Manages centerline tracking beeps.
        layout: Airport ground layout (runways, taxiways, etc.).
        config: Navigation configuration.
        enabled: Whether navigation is currently enabled.

    Examples:
        >>> manager = GroundNavigationManager(tracker, audio, beep, layout)
        >>> manager.enable()
        >>> manager.update(position, heading, timestamp)
    """

    def __init__(
        self,
        position_tracker: PositionTracker,
        orientation_audio: OrientationAudioManager,
        centerline_beep: CenterlineBeepManager,
        layout: AirportLayout,
        config: GroundNavigationConfig | None = None,
    ) -> None:
        """Initialize ground navigation manager.

        Args:
            position_tracker: Position tracker instance.
            orientation_audio: Orientation audio manager instance.
            centerline_beep: Centerline beep manager instance.
            layout: Airport layout for navigation.
            config: Optional configuration.
        """
        self.position_tracker = position_tracker
        self.orientation_audio = orientation_audio
        self.centerline_beep = centerline_beep
        self.layout = layout
        self.config = config or GroundNavigationConfig()

        # State tracking
        self._enabled = False
        self._announced_junctions: set[str] = set()
        self._last_hold_short_distance: float | None = None
        self._last_hold_short_runway: str = ""

        logger.info(
            "GroundNavigationManager initialized for %s (junction_dist=%.0fm)",
            layout.icao,
            self.config.junction_announce_distance_m,
        )

        if self.config.enable_centerline_on_start:
            self.centerline_beep.enable()

    @property
    def enabled(self) -> bool:
        """Check if ground navigation is enabled."""
        return self._enabled

    def enable(self) -> None:
        """Enable ground navigation."""
        self._enabled = True
        logger.info("Ground navigation enabled")

    def disable(self) -> None:
        """Disable ground navigation."""
        self._enabled = False
        self.centerline_beep.disable()
        logger.info("Ground navigation disabled")

    def update(self, position: Vector3, heading: float, timestamp: float) -> None:
        """Update navigation state and trigger audio cues.

        Should be called regularly (e.g., every frame) with current aircraft state.

        Args:
            position: Current aircraft position (lon, elev, lat).
            heading: Current aircraft heading in degrees.
            timestamp: Current simulation timestamp.
        """
        if not self._enabled:
            return

        # Update position tracker
        self.position_tracker.update(position, heading, timestamp)

        # Centerline tracking
        deviation = self.position_tracker.get_centerline_deviation()
        self.centerline_beep.update(deviation, timestamp)

        # Junction announcements
        self._check_junctions(position, heading)

        # Hold short warnings
        self._check_hold_short(position, heading)

    def _check_junctions(self, position: Vector3, heading: float) -> None:
        """Check for and announce approaching junctions.

        Args:
            position: Current aircraft position.
            heading: Current aircraft heading.
        """
        junctions = self.position_tracker.get_approaching_junctions(
            look_ahead_m=self.config.junction_announce_distance_m
        )

        for junction in junctions:
            # Create unique key for this junction approach
            junction_key = f"{junction.name}"

            # Announce once per junction
            if junction_key not in self._announced_junctions:
                self.orientation_audio.announce_junction_spatial(junction, position, heading)
                self._announced_junctions.add(junction_key)

        # Clear old announcements when we move away from junctions
        # Keep only junctions that are still in the current list
        current_names = {j.name for j in junctions}
        self._announced_junctions = self._announced_junctions.intersection(current_names)

    def _check_hold_short(self, position: Vector3, heading: float) -> None:
        """Check for and announce hold short points.

        Args:
            position: Current aircraft position.
            heading: Current aircraft heading.
        """
        hold_short = self.position_tracker.get_approaching_hold_short()

        if hold_short:
            distance = hold_short.distance_m
            runway = hold_short.runway_id

            # Reset if this is a different runway
            if self._last_hold_short_runway != runway:
                self._last_hold_short_distance = None
                self._last_hold_short_runway = runway

            # Find the appropriate threshold for current distance
            # Thresholds are checked from smallest to largest
            thresholds = sorted(self.config.hold_short_thresholds_m)
            current_threshold = None

            for threshold in thresholds:
                if distance <= threshold:
                    current_threshold = threshold
                    break

            if current_threshold is not None:
                # Announce if we've crossed into a new (smaller) threshold zone
                if (
                    self._last_hold_short_distance is None
                    or current_threshold < self._last_hold_short_distance
                ):
                    self.orientation_audio.announce_hold_short(hold_short)
                    self._last_hold_short_distance = current_threshold
        else:
            # No hold short ahead, reset state
            self._last_hold_short_distance = None
            self._last_hold_short_runway = ""

    def where_am_i(self) -> None:
        """Handle "where am I" voice command.

        Announces current position with nearby features and distance
        to nearest runway threshold.
        """
        if not self.position_tracker.position_history:
            logger.warning("Cannot announce position: no position history")
            return

        location_type, location_id = self.position_tracker.get_current_location()
        position, heading = self.position_tracker.position_history[-1]

        # Find nearest runway
        nearest_runway = self._find_nearest_runway(position)

        # Find nearby features (junctions not on current path)
        nearby_features = self._find_nearby_features(position, location_id)

        self.orientation_audio.announce_detailed_position(
            location_type=location_type,
            location_id=location_id,
            nearest_runway=nearest_runway,
            nearby_features=nearby_features,
        )

    def _find_nearest_runway(self, position: Vector3) -> tuple[str, float] | None:
        """Find nearest runway threshold to position.

        Args:
            position: Current position.

        Returns:
            Tuple of (runway_id, distance_m) or None if no runways.
        """
        nearest: tuple[str, float] | None = None
        min_distance = float("inf")

        for runway in self.layout.runways:
            distance = self._calculate_distance(position, runway.threshold_pos)
            if distance < min_distance:
                min_distance = distance
                nearest = (runway.id, distance)

        return nearest

    def _find_nearby_features(
        self, position: Vector3, exclude_id: str
    ) -> list[tuple[str, str, float]]:
        """Find nearby taxiways/runways for position announcement.

        Args:
            position: Current position.
            exclude_id: Location ID to exclude (current location).

        Returns:
            List of (feature_type, name, distance) tuples.
        """
        features: list[tuple[str, str, float]] = []

        # Check nearby taxiways via junctions
        junctions = self.position_tracker.get_approaching_junctions(look_ahead_m=100.0)
        seen_names: set[str] = set()

        for junction in junctions:
            if junction.name != exclude_id and junction.name not in seen_names:
                features.append((junction.junction_type, junction.name, junction.distance_m))
                seen_names.add(junction.name)

        # Sort by distance and limit
        features.sort(key=lambda x: x[2])
        return features[:3]

    @staticmethod
    def _calculate_distance(pos1: Vector3, pos2: Vector3) -> float:
        """Calculate distance between two positions in meters.

        Args:
            pos1: First position.
            pos2: Second position.

        Returns:
            Distance in meters.
        """
        import math

        dx = (pos2.x - pos1.x) * 111000.0
        dz = (pos2.z - pos1.z) * 111000.0
        return math.sqrt(dx * dx + dz * dz)

    def enable_centerline_tracking(self, enabled: bool = True) -> None:
        """Enable or disable centerline tracking beeps.

        Args:
            enabled: Whether to enable centerline tracking.
        """
        if enabled:
            self.centerline_beep.enable()
        else:
            self.centerline_beep.disable()

    def toggle_centerline_tracking(self) -> bool:
        """Toggle centerline tracking on/off.

        Returns:
            New enabled state.
        """
        return self.centerline_beep.toggle()
