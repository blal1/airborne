"""Centerline tracking audio feedback for ground navigation.

Provides panned audio beeps to help pilots maintain centerline position
on taxiways and runways. When drifting left, beeps come from the left
speaker; when drifting right, beeps come from the right speaker.

Typical usage:
    from airborne.audio.centerline import CenterlineBeepManager

    manager = CenterlineBeepManager(message_queue)
    manager.enable()

    # In update loop:
    deviation = position_tracker.get_centerline_deviation()
    manager.update(deviation, current_time)
"""

import logging
from dataclasses import dataclass

from airborne.core.messaging import Message, MessagePriority, MessageQueue, MessageTopic

logger = logging.getLogger(__name__)


@dataclass
class CenterlineConfig:
    """Configuration for centerline tracking beeps.

    Attributes:
        beep_interval_s: Time between beeps in seconds.
        max_deviation_m: Deviation distance for maximum pan (full L/R).
        deviation_threshold_m: Minimum deviation to trigger off-center beep.
        on_centerline_beep: Whether to beep when on centerline (centered).
    """

    beep_interval_s: float = 0.5
    max_deviation_m: float = 5.0
    deviation_threshold_m: float = 0.3
    on_centerline_beep: bool = True


class CenterlineBeepManager:
    """Manages panned beeps for centerline tracking.

    Provides audio feedback about aircraft position relative to taxiway/runway
    centerline. Uses spatially panned beeps - drifting left causes beeps from
    the left speaker, drifting right from the right speaker.

    Examples:
        >>> manager = CenterlineBeepManager(message_queue)
        >>> manager.enable()
        >>> deviation = (2.5, "left")  # 2.5m left of centerline
        >>> manager.update(deviation, current_time)
        # Plays beep from left speaker
    """

    def __init__(
        self,
        message_queue: MessageQueue | None = None,
        config: CenterlineConfig | None = None,
    ) -> None:
        """Initialize centerline beep manager.

        Args:
            message_queue: Message queue for audio playback requests.
            config: Configuration for beep behavior.
        """
        self.message_queue = message_queue
        self.config = config or CenterlineConfig()

        self._enabled = False
        self._last_beep_time = 0.0

        logger.info(
            "CenterlineBeepManager initialized (interval=%.2fs, max_dev=%.1fm)",
            self.config.beep_interval_s,
            self.config.max_deviation_m,
        )

    @property
    def enabled(self) -> bool:
        """Check if centerline tracking is enabled."""
        return self._enabled

    def enable(self) -> None:
        """Enable centerline tracking beeps."""
        self._enabled = True
        logger.info("Centerline tracking enabled")

    def disable(self) -> None:
        """Disable centerline tracking beeps."""
        self._enabled = False
        logger.info("Centerline tracking disabled")

    def toggle(self) -> bool:
        """Toggle centerline tracking on/off.

        Returns:
            New enabled state.
        """
        if self._enabled:
            self.disable()
        else:
            self.enable()
        return self._enabled

    def update(
        self,
        deviation: tuple[float, str] | None,
        current_time: float,
    ) -> bool:
        """Update centerline tracking and play beeps as needed.

        Should be called regularly (e.g., every frame) with current deviation.

        Args:
            deviation: Tuple of (deviation_meters, direction) from PositionTracker,
                      or None if not on taxiway/runway.
            current_time: Current simulation time in seconds.

        Returns:
            True if a beep was played, False otherwise.

        Examples:
            >>> manager.update((2.0, "left"), time.time())
            True  # Beep played from left
        """
        if not self._enabled:
            return False

        # Check if enough time has passed since last beep
        if current_time - self._last_beep_time < self.config.beep_interval_s:
            return False

        if deviation is None:
            # Not on taxiway/runway - no beep
            return False

        distance_m, direction = deviation

        # Check if deviation is significant
        if distance_m < self.config.deviation_threshold_m:
            if not self.config.on_centerline_beep:
                return False
            # On centerline - centered beep
            pan = 0.0
        else:
            # Calculate pan position (-1 = full left, +1 = full right)
            pan = min(distance_m / self.config.max_deviation_m, 1.0)
            if direction == "left":
                pan = -pan

        # Play panned beep
        self._play_panned_beep(pan)
        self._last_beep_time = current_time

        return True

    def _play_panned_beep(self, pan: float) -> None:
        """Play a beep with the specified pan position.

        Args:
            pan: -1.0 (full left) to +1.0 (full right), 0.0 = center
        """
        if not self.message_queue:
            logger.warning("Cannot play beep: no message queue")
            return

        # Convert pan to 3D position relative to listener
        # Listener is at origin, facing forward (+Z in our coordinate system)
        # Left is -X, Right is +X
        x_offset = pan * 10.0  # 10 meters for full pan
        position = {"x": x_offset, "y": 0.0, "z": 1.0}  # Slightly in front

        # Send spatial beep request
        message = Message(
            sender="centerline_beep",
            recipients=["audio_plugin"],
            topic=MessageTopic.PLAY_SOUND_SPATIAL,
            data={
                "sound_id": "centerline_beep",
                "position": position,
                "volume": 0.7,
            },
            priority=MessagePriority.NORMAL,
        )

        self.message_queue.publish(message)

        # Log for debugging
        if abs(pan) < 0.1:
            logger.debug("Centerline beep: centered")
        else:
            direction = "left" if pan < 0 else "right"
            logger.debug("Centerline beep: %.1f %s", abs(pan), direction)
