"""Flight instructor plugin.

Provides real-time coaching and feedback on flight technique.
Monitors aircraft state and provides progressive feedback on:
- Post-takeoff pitch management
- Stall recovery
- Airspeed management

Typical usage:
    Plugin is loaded automatically by plugin loader.
    Enable: Shift+F9, Disable: Ctrl+F9, Assessment: F9
"""

from typing import Any

from airborne.core.i18n import t
from airborne.core.input import InputActionEvent
from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessagePriority, MessageTopic
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType

logger = get_logger(__name__)


class FlightInstructorPlugin(IPlugin):
    """Flight instructor plugin.

    Monitors flight parameters and provides coaching feedback.
    Disabled by default, can be enabled/disabled with key bindings.
    """

    def __init__(self):
        """Initialize flight instructor plugin."""
        self.context: PluginContext | None = None
        self.enabled = False  # Disabled by default

        # Flight state tracking
        self.airspeed = 0.0  # knots
        self.altitude_agl = 0.0  # feet above ground level
        self.pitch_angle = 0.0  # degrees
        self.is_on_ground = True
        self.stall_warning_active = False

        # Instructor feedback timers (to avoid spam)
        self.pitch_feedback_timer = 0.0
        self.airspeed_feedback_timer = 0.0
        self.stall_feedback_timer = 0.0
        self.feedback_cooldown = 10.0  # seconds between similar messages

        # Takeoff detection
        self.just_took_off = False
        self.takeoff_altitude_threshold = 50.0  # feet AGL

        # Phase 1 thresholds
        self.post_takeoff_pitch_max = 15.0  # degrees (Cessna 172 typical climb: 7-10°)
        self.post_takeoff_pitch_min = 0.0  # degrees
        self.stall_warning_speed = 55.0  # knots (Vs0 for Cessna 172)
        self.cruise_speed_min = 70.0  # knots
        self.cruise_speed_max = 140.0  # knots (Vne approach)

    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata.

        Returns:
            PluginMetadata describing this flight instructor plugin.
        """
        return PluginMetadata(
            name="flight_instructor_plugin",
            version="1.0.0",
            author="AirBorne Team",
            plugin_type=PluginType.AVIONICS,
            dependencies=["physics_plugin", "audio_plugin"],
            provides=["flight_instructor"],
            optional=True,
            update_priority=80,  # Update after physics
            requires_physics=True,
            description="Flight instructor providing real-time coaching and feedback",
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize the flight instructor plugin.

        Args:
            context: Plugin context with access to core systems.
        """
        self.context = context

        # Subscribe to relevant messages
        context.message_queue.subscribe("physics.state", self.handle_message)
        context.message_queue.subscribe("input.action", self.handle_message)

        # Subscribe to input action events from event bus
        context.event_bus.subscribe(InputActionEvent, self._handle_input_action_event)

        logger.info("Flight instructor plugin initialized (disabled by default)")

    def handle_message(self, message: Message) -> None:
        """Handle incoming messages.

        Args:
            message: The message to handle.
        """
        if message.topic == "physics.state":
            self._handle_physics_state(message.data)
        elif message.topic == "input.action":
            self._handle_input_action(message.data)

    def _handle_physics_state(self, data: dict[str, Any]) -> None:
        """Handle physics state updates.

        Args:
            data: Physics state data.
        """
        if not self.enabled:
            return

        # Extract flight parameters
        self.airspeed = data.get("airspeed_kts", 0.0)
        self.altitude_agl = data.get("altitude_agl_ft", 0.0)
        self.pitch_angle = data.get("pitch_deg", 0.0)
        was_on_ground = self.is_on_ground
        self.is_on_ground = data.get("on_ground", True)

        # Detect takeoff
        if was_on_ground and not self.is_on_ground:
            self.just_took_off = True
            logger.debug("Takeoff detected")

        # Track stall warning
        stall_warning = data.get("stall_warning", False)
        if stall_warning and not self.stall_warning_active:
            self.stall_warning_active = True
        elif not stall_warning and self.stall_warning_active:
            self.stall_warning_active = False

    def _handle_input_action(self, data: dict[str, Any]) -> None:
        """Handle input action events (key bindings).

        Args:
            data: Input action data.
        """
        action = data.get("action")

        if action == "instructor_enable":
            self._enable_instructor()
        elif action == "instructor_disable":
            self._disable_instructor()
        elif action == "instructor_assessment":
            self._provide_assessment()

    def _handle_input_action_event(self, event: InputActionEvent) -> None:
        """Handle input action events from event bus.

        Args:
            event: Input action event.
        """
        if event.action == "instructor_enable":
            self._enable_instructor()
        elif event.action == "instructor_disable":
            self._disable_instructor()
        elif event.action == "instructor_assessment":
            self._provide_assessment()

    def _enable_instructor(self) -> None:
        """Enable the flight instructor."""
        if not self.enabled:
            self.enabled = True
            logger.info("Flight instructor enabled")
            self._speak(t("instructor.enabled"))

    def _disable_instructor(self) -> None:
        """Disable the flight instructor."""
        if self.enabled:
            self.enabled = False
            logger.info("Flight instructor disabled")
            self._speak(t("instructor.disabled"))

    def _provide_assessment(self) -> None:
        """Provide on-demand flight performance assessment (F9)."""
        if not self.enabled:
            # Enable temporarily for assessment
            logger.info("Providing one-time assessment")

        self._speak(t("instructor.assessment"))
        # TODO: Analyze recent flight data and provide detailed feedback

    def _speak(self, message_id: str, priority: MessagePriority = MessagePriority.NORMAL) -> None:
        """Request speech output.

        Args:
            message_id: Speech message identifier.
            priority: Message priority.
        """
        if not self.context:
            return

        self.context.message_queue.publish(
            Message(
                sender="flight_instructor_plugin",
                recipients=["*"],
                topic=MessageTopic.TTS_SPEAK,
                priority=priority,
                data={"text": message_id, "priority": "normal", "interrupt": False},
            )
        )

    def update(self, dt: float) -> None:
        """Update flight instructor monitoring.

        Args:
            dt: Delta time in seconds since last update.
        """
        if not self.context or not self.enabled:
            return

        # Update feedback timers
        self.pitch_feedback_timer = max(0.0, self.pitch_feedback_timer - dt)
        self.airspeed_feedback_timer = max(0.0, self.airspeed_feedback_timer - dt)
        self.stall_feedback_timer = max(0.0, self.stall_feedback_timer - dt)

        # Phase 1 monitoring: Post-takeoff pitch
        if self.just_took_off and self.altitude_agl < 500.0:
            self._monitor_post_takeoff_pitch()

        # Reset takeoff flag after reaching safe altitude
        if self.just_took_off and self.altitude_agl >= 500.0:
            self.just_took_off = False

        # Phase 1 monitoring: Stall recovery
        if self.stall_warning_active:
            self._monitor_stall_warning()

        # Phase 1 monitoring: Airspeed management
        if not self.is_on_ground:
            self._monitor_airspeed()

    def _monitor_post_takeoff_pitch(self) -> None:
        """Monitor pitch angle immediately after takeoff."""
        if self.pitch_feedback_timer > 0:
            return  # Cooldown active

        # Check for excessive pitch up (too steep)
        if self.pitch_angle > self.post_takeoff_pitch_max:
            self._speak(t("instructor.pitch_too_high"), MessagePriority.HIGH)
            self.pitch_feedback_timer = self.feedback_cooldown
            logger.debug(f"Pitch too high: {self.pitch_angle:.1f}°")

        # Check for insufficient pitch (nose too low)
        elif self.pitch_angle < self.post_takeoff_pitch_min:
            self._speak(t("instructor.pitch_too_low"), MessagePriority.HIGH)
            self.pitch_feedback_timer = self.feedback_cooldown
            logger.debug(f"Pitch too low: {self.pitch_angle:.1f}°")

    def _monitor_stall_warning(self) -> None:
        """Monitor stall warning and provide recovery guidance."""
        if self.stall_feedback_timer > 0:
            return  # Cooldown active

        self._speak(t("instructor.stall_warning"), MessagePriority.CRITICAL)
        self.stall_feedback_timer = self.feedback_cooldown
        logger.debug("Stall warning active, providing guidance")

    def _monitor_airspeed(self) -> None:
        """Monitor airspeed and provide feedback."""
        if self.airspeed_feedback_timer > 0:
            return  # Cooldown active

        # Check for dangerously low airspeed
        if self.airspeed < self.stall_warning_speed + 10.0:
            self._speak(t("instructor.airspeed_low"), MessagePriority.HIGH)
            self.airspeed_feedback_timer = self.feedback_cooldown
            logger.debug(f"Airspeed too low: {self.airspeed:.1f} kts")

        # Check for excessive airspeed
        elif self.airspeed > self.cruise_speed_max:
            self._speak(t("instructor.airspeed_high"), MessagePriority.HIGH)
            self.airspeed_feedback_timer = self.feedback_cooldown
            logger.debug(f"Airspeed too high: {self.airspeed:.1f} kts")

    def shutdown(self) -> None:
        """Shutdown the flight instructor plugin."""
        logger.info("Flight instructor plugin shutdown")
