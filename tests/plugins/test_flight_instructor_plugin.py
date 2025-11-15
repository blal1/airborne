"""Tests for flight instructor plugin."""

import pytest

from airborne.core.event_bus import EventBus
from airborne.core.input import InputActionEvent
from airborne.core.messaging import Message, MessageQueue
from airborne.core.plugin import PluginContext
from airborne.plugins.training.flight_instructor_plugin import FlightInstructorPlugin


class TestFlightInstructorPlugin:
    """Test flight instructor plugin functionality."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        """Create event bus."""
        return EventBus()

    @pytest.fixture
    def message_queue(self) -> MessageQueue:
        """Create message queue."""
        return MessageQueue()

    @pytest.fixture
    def context(self, event_bus: EventBus, message_queue: MessageQueue) -> PluginContext:
        """Create plugin context."""
        return PluginContext(
            event_bus=event_bus,
            message_queue=message_queue,
            config={},
            plugin_registry=None,
        )

    @pytest.fixture
    def plugin(self) -> FlightInstructorPlugin:
        """Create flight instructor plugin."""
        return FlightInstructorPlugin()

    def test_plugin_starts_disabled(self, plugin: FlightInstructorPlugin) -> None:
        """Test plugin is disabled by default."""
        assert plugin.enabled is False

    def test_plugin_initialize(
        self, plugin: FlightInstructorPlugin, context: PluginContext
    ) -> None:
        """Test plugin initialization."""
        plugin.initialize(context)
        assert plugin.context == context

    def test_enable_instructor_via_event(
        self,
        plugin: FlightInstructorPlugin,
        context: PluginContext,
        event_bus: EventBus,
    ) -> None:
        """Test enabling instructor via input action event."""
        plugin.initialize(context)

        # Trigger enable action
        event = InputActionEvent(action="instructor_enable")
        event_bus.publish(event)

        # Should now be enabled
        assert plugin.enabled is True

    def test_disable_instructor_via_event(
        self,
        plugin: FlightInstructorPlugin,
        context: PluginContext,
        event_bus: EventBus,
    ) -> None:
        """Test disabling instructor via input action event."""
        plugin.initialize(context)
        plugin.enabled = True  # Start enabled

        # Trigger disable action
        event = InputActionEvent(action="instructor_disable")
        event_bus.publish(event)

        # Should now be disabled
        assert plugin.enabled is False

    def test_assessment_request(
        self,
        plugin: FlightInstructorPlugin,
        context: PluginContext,
        event_bus: EventBus,
        message_queue: MessageQueue,
    ) -> None:
        """Test on-demand assessment request."""
        plugin.initialize(context)

        # Subscribe to audio commands
        messages = []

        def capture_message(msg: Message) -> None:
            messages.append(msg)

        message_queue.subscribe("audio.command", capture_message)

        # Trigger assessment
        event = InputActionEvent(action="instructor_assessment")
        event_bus.publish(event)

        # Process message queue to deliver messages
        message_queue.process()

        # Should have sent assessment message
        assert len(messages) > 0
        assert any(m.data.get("message_id") == "MSG_INSTRUCTOR_ASSESSMENT" for m in messages)

    def test_post_takeoff_pitch_too_high(
        self, plugin: FlightInstructorPlugin, context: PluginContext
    ) -> None:
        """Test warning for excessive pitch after takeoff."""
        plugin.initialize(context)
        plugin.enabled = True

        # Simulate just took off
        plugin.just_took_off = True
        plugin.altitude_agl = 100.0  # Low altitude (post-takeoff)

        messages = []

        def capture_message(msg: Message) -> None:
            messages.append(msg)

        context.message_queue.subscribe("audio.command", capture_message)

        # Set pitch too high
        plugin.pitch_angle = 20.0  # Above 15° threshold

        # Update should trigger warning
        plugin.update(0.1)
        context.message_queue.process()

        # Should have sent pitch warning
        assert len(messages) > 0
        assert any(m.data.get("message_id") == "MSG_INSTRUCTOR_PITCH_TOO_HIGH" for m in messages)

    def test_post_takeoff_pitch_too_low(
        self, plugin: FlightInstructorPlugin, context: PluginContext
    ) -> None:
        """Test warning for insufficient pitch after takeoff."""
        plugin.initialize(context)
        plugin.enabled = True

        # Simulate just took off
        plugin.just_took_off = True
        plugin.altitude_agl = 100.0

        messages = []

        def capture_message(msg: Message) -> None:
            messages.append(msg)

        context.message_queue.subscribe("audio.command", capture_message)

        # Set pitch too low (negative)
        plugin.pitch_angle = -5.0  # Below 0° threshold

        # Update should trigger warning
        context.message_queue.process()
        plugin.update(0.1)
        context.message_queue.process()

        # Should have sent pitch warning
        assert len(messages) > 0
        assert any(m.data.get("message_id") == "MSG_INSTRUCTOR_PITCH_TOO_LOW" for m in messages)

    def test_stall_warning_guidance(
        self, plugin: FlightInstructorPlugin, context: PluginContext
    ) -> None:
        """Test stall warning provides recovery guidance."""
        plugin.initialize(context)
        plugin.enabled = True
        plugin.stall_warning_active = True
        plugin.is_on_ground = False

        messages = []

        def capture_message(msg: Message) -> None:
            messages.append(msg)

        context.message_queue.subscribe("audio.command", capture_message)

        # Update should trigger stall warning
        context.message_queue.process()
        plugin.update(0.1)
        context.message_queue.process()

        # Should have sent stall warning
        assert len(messages) > 0
        assert any(m.data.get("message_id") == "MSG_INSTRUCTOR_STALL_WARNING" for m in messages)

    def test_airspeed_too_low_warning(
        self, plugin: FlightInstructorPlugin, context: PluginContext
    ) -> None:
        """Test warning for dangerously low airspeed."""
        plugin.initialize(context)
        plugin.enabled = True
        plugin.is_on_ground = False

        messages = []

        def capture_message(msg: Message) -> None:
            messages.append(msg)

        context.message_queue.subscribe("audio.command", capture_message)

        # Set airspeed dangerously low (55 + 10 = 65 kts threshold)
        plugin.airspeed = 60.0  # Below threshold

        # Update should trigger warning
        context.message_queue.process()
        plugin.update(0.1)
        context.message_queue.process()

        # Should have sent airspeed warning
        assert len(messages) > 0
        assert any(m.data.get("message_id") == "MSG_INSTRUCTOR_AIRSPEED_LOW" for m in messages)

    def test_airspeed_too_high_warning(
        self, plugin: FlightInstructorPlugin, context: PluginContext
    ) -> None:
        """Test warning for excessive airspeed."""
        plugin.initialize(context)
        plugin.enabled = True
        plugin.is_on_ground = False

        messages = []

        def capture_message(msg: Message) -> None:
            messages.append(msg)

        context.message_queue.subscribe("audio.command", capture_message)

        # Set airspeed too high
        plugin.airspeed = 150.0  # Above 140 kts threshold

        # Update should trigger warning
        context.message_queue.process()
        plugin.update(0.1)
        context.message_queue.process()

        # Should have sent airspeed warning
        assert len(messages) > 0
        assert any(m.data.get("message_id") == "MSG_INSTRUCTOR_AIRSPEED_HIGH" for m in messages)

    def test_feedback_cooldown(
        self, plugin: FlightInstructorPlugin, context: PluginContext
    ) -> None:
        """Test feedback has cooldown to avoid spam."""
        plugin.initialize(context)
        plugin.enabled = True
        plugin.is_on_ground = False

        messages = []

        def capture_message(msg: Message) -> None:
            messages.append(msg)

        context.message_queue.subscribe("audio.command", capture_message)

        # Trigger airspeed warning
        plugin.airspeed = 60.0  # Too low
        plugin.update(0.1)
        context.message_queue.process()

        initial_count = len(messages)
        assert initial_count > 0

        # Immediate second update should NOT trigger (cooldown active)
        plugin.update(0.1)
        context.message_queue.process()
        assert len(messages) == initial_count  # No new messages

        # After cooldown period (10s), should allow another warning
        plugin.update(10.0)
        context.message_queue.process()  # Advance time past cooldown
        assert len(messages) > initial_count  # New message sent

    def test_disabled_plugin_no_monitoring(
        self, plugin: FlightInstructorPlugin, context: PluginContext
    ) -> None:
        """Test disabled plugin doesn't send feedback."""
        plugin.initialize(context)
        plugin.enabled = False  # Disabled

        messages = []

        def capture_message(msg: Message) -> None:
            messages.append(msg)

        context.message_queue.subscribe("audio.command", capture_message)

        # Set conditions that would trigger warnings if enabled
        plugin.airspeed = 60.0  # Too low
        plugin.pitch_angle = 20.0  # Too high
        plugin.just_took_off = True
        plugin.altitude_agl = 100.0

        # Update should NOT trigger any warnings
        plugin.update(0.1)
        context.message_queue.process()

        # Should have no messages (disabled)
        assert len(messages) == 0

    def test_takeoff_detection(
        self, plugin: FlightInstructorPlugin, context: PluginContext
    ) -> None:
        """Test takeoff detection logic."""
        plugin.initialize(context)
        plugin.enabled = True

        # Start on ground
        plugin.is_on_ground = True

        # Simulate physics state update for takeoff
        physics_data = {
            "airspeed_kts": 70.0,
            "altitude_agl_ft": 10.0,
            "pitch_deg": 10.0,
            "on_ground": False,  # Just lifted off
            "stall_warning": False,
        }

        message = Message(
            sender="physics_plugin",
            recipients=["flight_instructor_plugin"],
            topic="physics.state",
            data=physics_data,
        )

        plugin.handle_message(message)

        # Should detect takeoff
        assert plugin.just_took_off is True

    def test_takeoff_flag_clears_at_safe_altitude(
        self, plugin: FlightInstructorPlugin, context: PluginContext
    ) -> None:
        """Test takeoff flag clears after reaching safe altitude."""
        plugin.initialize(context)
        plugin.enabled = True
        plugin.just_took_off = True
        plugin.altitude_agl = 600.0  # Above 500 ft threshold

        # Update should clear takeoff flag
        plugin.update(0.1)
        context.message_queue.process()

        assert plugin.just_took_off is False

    def test_metadata(self, plugin: FlightInstructorPlugin) -> None:
        """Test plugin metadata."""
        metadata = plugin.get_metadata()

        assert metadata.name == "flight_instructor_plugin"
        assert metadata.optional is True
        assert metadata.requires_physics is True
        assert "physics_plugin" in metadata.dependencies
        assert "audio_plugin" in metadata.dependencies
