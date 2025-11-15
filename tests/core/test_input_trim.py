"""Tests for trim input controls (pitch and rudder trim)."""

from unittest.mock import Mock, patch

import pygame
import pytest

from airborne.core.event_bus import EventBus
from airborne.core.input import InputActionEvent, InputManager

# Patch path for pygame.key.get_mods in the input module
PATCH_GET_MODS = "airborne.core.input.pygame.key.get_mods"


class TestPitchTrimControls:
    """Test pitch trim control functionality."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        """Create event bus."""
        return EventBus()

    @pytest.fixture
    def manager(self, event_bus: EventBus) -> InputManager:
        """Create input manager."""
        # Initialize pygame to avoid errors
        if not pygame.get_init():
            pygame.init()
        return InputManager(event_bus)

    def test_pitch_trim_starts_at_neutral(self, manager: InputManager) -> None:
        """Test pitch trim starts at neutral position (0.0)."""
        assert manager.state.pitch_trim == 0.0

    def test_pitch_trim_up_with_shift_period(
        self, manager: InputManager, event_bus: EventBus
    ) -> None:
        """Test Shift+Semicolon increases pitch trim."""
        received_events = []

        def handler(event: InputActionEvent) -> None:
            received_events.append(event)

        event_bus.subscribe(InputActionEvent, handler)

        # Mock pygame.key.get_mods() to return SHIFT and keep patch active during update
        with patch(PATCH_GET_MODS, return_value=pygame.KMOD_SHIFT):
            keydown = Mock()
            keydown.type = pygame.KEYDOWN
            keydown.key = pygame.K_SEMICOLON
            manager.process_events([keydown])

            # Update to process trim change (within patch context)
            manager.update(0.11)  # Wait for rate limiting

        # Trim should have increased (2.5% increment)
        assert manager.state.pitch_trim > 0.0
        assert manager.state.pitch_trim == pytest.approx(0.025, abs=0.001)

        # Should have published trim adjusted event
        trim_events = [e for e in received_events if e.action == "trim_pitch_adjusted"]
        assert len(trim_events) > 0

    def test_pitch_trim_down_with_ctrl_period(
        self, manager: InputManager, event_bus: EventBus
    ) -> None:
        """Test Ctrl+Semicolon decreases pitch trim."""
        # Start with some positive trim
        manager.state.pitch_trim = 0.5

        received_events = []

        def handler(event: InputActionEvent) -> None:
            received_events.append(event)

        event_bus.subscribe(InputActionEvent, handler)

        # Mock pygame.key.get_mods() to return CTRL
        with patch(PATCH_GET_MODS, return_value=pygame.KMOD_CTRL):
            keydown = Mock()
            keydown.type = pygame.KEYDOWN
            keydown.key = pygame.K_SEMICOLON
            manager.process_events([keydown])

        # Update to process trim change
        manager.update(0.11)

        # Trim should have decreased (2.5% decrement)
        assert manager.state.pitch_trim < 0.5
        assert manager.state.pitch_trim == pytest.approx(0.475, abs=0.001)

        # Should have published trim adjusted event
        trim_events = [e for e in received_events if e.action == "trim_pitch_adjusted"]
        assert len(trim_events) > 0

    def test_pitch_trim_clamps_at_maximum(self, manager: InputManager) -> None:
        """Test pitch trim clamps at +1.0."""
        # Start near maximum
        manager.state.pitch_trim = 0.98

        # Mock pygame.key.get_mods() to return SHIFT
        with patch(PATCH_GET_MODS, return_value=pygame.KMOD_SHIFT):
            keydown = Mock()
            keydown.type = pygame.KEYDOWN
            keydown.key = pygame.K_SEMICOLON

            for _ in range(10):
                manager.process_events([keydown])
                manager.update(0.11)

        # Should clamp at 1.0
        assert manager.state.pitch_trim == 1.0

    def test_pitch_trim_clamps_at_minimum(self, manager: InputManager) -> None:
        """Test pitch trim clamps at -1.0."""
        # Start near minimum
        manager.state.pitch_trim = -0.98

        # Mock pygame.key.get_mods() to return CTRL
        with patch(PATCH_GET_MODS, return_value=pygame.KMOD_CTRL):
            keydown = Mock()
            keydown.type = pygame.KEYDOWN
            keydown.key = pygame.K_SEMICOLON

            for _ in range(10):
                manager.process_events([keydown])
                manager.update(0.11)

        # Should clamp at -1.0
        assert manager.state.pitch_trim == -1.0

    def test_pitch_trim_rate_limiting(self, manager: InputManager) -> None:
        """Test pitch trim has rate limiting (10 clicks/second max)."""
        with patch(PATCH_GET_MODS, return_value=pygame.KMOD_SHIFT):
            keydown = Mock()
            keydown.type = pygame.KEYDOWN
            keydown.key = pygame.K_SEMICOLON
            manager.process_events([keydown])

            # First update should apply trim (2.5% increment)
            manager.update(0.016)
            assert manager.state.pitch_trim == pytest.approx(0.025, abs=0.001)

            # Immediate second update should NOT apply trim (rate limited)
            manager.update(0.016)
            assert manager.state.pitch_trim == pytest.approx(0.025, abs=0.001)

            # After 0.1s, should allow another click
            manager.update(0.1)
            assert manager.state.pitch_trim == pytest.approx(0.05, abs=0.001)

    def test_pitch_trim_increment_size(self, manager: InputManager) -> None:
        """Test pitch trim uses 2.5% (0.025) increments."""
        with patch(PATCH_GET_MODS, return_value=pygame.KMOD_SHIFT):
            keydown = Mock()
            keydown.type = pygame.KEYDOWN
            keydown.key = pygame.K_SEMICOLON
            manager.process_events([keydown])
            manager.update(0.11)

        # Each click should be 2.5% (0.025)
        assert manager.state.pitch_trim == pytest.approx(0.025, abs=0.001)

    def test_pitch_trim_event_contains_percentage(
        self, manager: InputManager, event_bus: EventBus
    ) -> None:
        """Test pitch trim event contains percentage value."""
        received_events = []

        def handler(event: InputActionEvent) -> None:
            received_events.append(event)

        event_bus.subscribe(InputActionEvent, handler)

        # Set trim to neutral (0.0, which is 50% in 0-100 scale)
        manager.state.pitch_trim = 0.0

        with patch(PATCH_GET_MODS, return_value=pygame.KMOD_SHIFT):
            keydown = Mock()
            keydown.type = pygame.KEYDOWN
            keydown.key = pygame.K_SEMICOLON
            manager.process_events([keydown])
            manager.update(0.11)

        # Find trim adjusted event
        trim_events = [e for e in received_events if e.action == "trim_pitch_adjusted"]
        assert len(trim_events) > 0

        # Event should contain percentage (0.025 = 51.25% = 51 int)
        # Formula: (trim + 1.0) * 50 = (0.025 + 1.0) * 50 = 51.25 = 51 (int)
        assert trim_events[0].value == 51


class TestRudderTrimControls:
    """Test rudder trim control functionality."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        """Create event bus."""
        return EventBus()

    @pytest.fixture
    def manager(self, event_bus: EventBus) -> InputManager:
        """Create input manager."""
        # Initialize pygame
        if not pygame.get_init():
            pygame.init()
        return InputManager(event_bus)

    def test_rudder_trim_starts_at_neutral(self, manager: InputManager) -> None:
        """Test rudder trim starts at neutral position (0.0)."""
        assert manager.state.rudder_trim == 0.0

    def test_rudder_trim_right_with_shift_comma(
        self, manager: InputManager, event_bus: EventBus
    ) -> None:
        """Test Shift+Comma increases rudder trim (right)."""
        received_events = []

        def handler(event: InputActionEvent) -> None:
            received_events.append(event)

        event_bus.subscribe(InputActionEvent, handler)

        with patch(PATCH_GET_MODS, return_value=pygame.KMOD_SHIFT):
            keydown = Mock()
            keydown.type = pygame.KEYDOWN
            keydown.key = pygame.K_COMMA
            manager.process_events([keydown])
            manager.update(0.11)

        # Trim should have increased (right) by 2.5%
        assert manager.state.rudder_trim > 0.0
        assert manager.state.rudder_trim == pytest.approx(0.025, abs=0.001)

        # Should have published trim adjusted event
        trim_events = [e for e in received_events if e.action == "trim_rudder_adjusted"]
        assert len(trim_events) > 0

    def test_rudder_trim_left_with_ctrl_comma(
        self, manager: InputManager, event_bus: EventBus
    ) -> None:
        """Test Ctrl+Comma decreases rudder trim (left)."""
        # Start with some right trim
        manager.state.rudder_trim = 0.5

        received_events = []

        def handler(event: InputActionEvent) -> None:
            received_events.append(event)

        event_bus.subscribe(InputActionEvent, handler)

        with patch(PATCH_GET_MODS, return_value=pygame.KMOD_CTRL):
            keydown = Mock()
            keydown.type = pygame.KEYDOWN
            keydown.key = pygame.K_COMMA
            manager.process_events([keydown])
            manager.update(0.11)

        # Trim should have decreased (left) by 2.5%
        assert manager.state.rudder_trim < 0.5
        assert manager.state.rudder_trim == pytest.approx(0.475, abs=0.001)

        # Should have published trim adjusted event
        trim_events = [e for e in received_events if e.action == "trim_rudder_adjusted"]
        assert len(trim_events) > 0

    def test_rudder_trim_clamps_at_maximum(self, manager: InputManager) -> None:
        """Test rudder trim clamps at +1.0 (full right)."""
        # Start near maximum
        manager.state.rudder_trim = 0.98

        with patch(PATCH_GET_MODS, return_value=pygame.KMOD_SHIFT):
            keydown = Mock()
            keydown.type = pygame.KEYDOWN
            keydown.key = pygame.K_COMMA

            for _ in range(10):
                manager.process_events([keydown])
                manager.update(0.11)

        # Should clamp at 1.0
        assert manager.state.rudder_trim == 1.0

    def test_rudder_trim_clamps_at_minimum(self, manager: InputManager) -> None:
        """Test rudder trim clamps at -1.0 (full left)."""
        # Start near minimum
        manager.state.rudder_trim = -0.98

        with patch(PATCH_GET_MODS, return_value=pygame.KMOD_CTRL):
            keydown = Mock()
            keydown.type = pygame.KEYDOWN
            keydown.key = pygame.K_COMMA

            for _ in range(10):
                manager.process_events([keydown])
                manager.update(0.11)

        # Should clamp at -1.0
        assert manager.state.rudder_trim == -1.0

    def test_rudder_trim_rate_limiting(self, manager: InputManager) -> None:
        """Test rudder trim has rate limiting (10 clicks/second max)."""
        with patch(PATCH_GET_MODS, return_value=pygame.KMOD_SHIFT):
            keydown = Mock()
            keydown.type = pygame.KEYDOWN
            keydown.key = pygame.K_COMMA
            manager.process_events([keydown])

            # First update should apply trim (2.5% increment)
            manager.update(0.016)
            assert manager.state.rudder_trim == pytest.approx(0.025, abs=0.001)

            # Immediate second update should NOT apply trim (rate limited)
            manager.update(0.016)
            assert manager.state.rudder_trim == pytest.approx(0.025, abs=0.001)

            # After 0.1s, should allow another click
            manager.update(0.1)
            assert manager.state.rudder_trim == pytest.approx(0.05, abs=0.001)

    def test_rudder_trim_increment_size(self, manager: InputManager) -> None:
        """Test rudder trim uses 2.5% (0.025) increments."""
        with patch(PATCH_GET_MODS, return_value=pygame.KMOD_SHIFT):
            keydown = Mock()
            keydown.type = pygame.KEYDOWN
            keydown.key = pygame.K_COMMA
            manager.process_events([keydown])
            manager.update(0.11)

        # Each click should be 2.5% (0.025)
        assert manager.state.rudder_trim == pytest.approx(0.025, abs=0.001)

    def test_rudder_trim_event_contains_percentage(
        self, manager: InputManager, event_bus: EventBus
    ) -> None:
        """Test rudder trim event contains percentage value."""
        received_events = []

        def handler(event: InputActionEvent) -> None:
            received_events.append(event)

        event_bus.subscribe(InputActionEvent, handler)

        # Set trim to neutral (0.0, which is 50% in 0-100 scale)
        manager.state.rudder_trim = 0.0

        with patch(PATCH_GET_MODS, return_value=pygame.KMOD_SHIFT):
            keydown = Mock()
            keydown.type = pygame.KEYDOWN
            keydown.key = pygame.K_COMMA
            manager.process_events([keydown])
            manager.update(0.11)

        # Find trim adjusted event
        trim_events = [e for e in received_events if e.action == "trim_rudder_adjusted"]
        assert len(trim_events) > 0

        # Event should contain percentage (0.025 = 51.25% = 51 int)
        assert trim_events[0].value == 51

    def test_comma_without_modifier_triggers_yaw_left(self, manager: InputManager) -> None:
        """Test plain comma key (no modifier) triggers yaw left, not rudder trim."""
        # Mock no modifiers pressed
        with patch(PATCH_GET_MODS, return_value=0):
            keydown = Mock()
            keydown.type = pygame.KEYDOWN
            keydown.key = pygame.K_COMMA
            manager.process_events([keydown])
            manager.update(0.016)

        # Should trigger yaw, not trim
        assert manager.state.yaw < 0.0  # Yaw left
        assert manager.state.rudder_trim == 0.0  # Trim unchanged


class TestTrimToPercentConversion:
    """Test the trim-to-percentage conversion helper method."""

    def test_trim_minimum_value(self):
        """Test trim value at minimum (-1.0) converts to 0%."""
        result = InputManager._trim_to_percent(-1.0)
        assert result == 0, "Minimum trim (-1.0) should be 0%"

    def test_trim_neutral_value(self):
        """Test trim value at neutral (0.0) converts to 50%."""
        result = InputManager._trim_to_percent(0.0)
        assert result == 50, "Neutral trim (0.0) should be 50%"

    def test_trim_maximum_value(self):
        """Test trim value at maximum (+1.0) converts to 100%."""
        result = InputManager._trim_to_percent(1.0)
        assert result == 100, "Maximum trim (+1.0) should be 100%"

    def test_trim_positive_mid_range(self):
        """Test trim value at +0.5 converts to 75%."""
        result = InputManager._trim_to_percent(0.5)
        assert result == 75, "Trim value +0.5 should be 75%"

    def test_trim_negative_mid_range(self):
        """Test trim value at -0.5 converts to 25%."""
        result = InputManager._trim_to_percent(-0.5)
        assert result == 25, "Trim value -0.5 should be 25%"

    def test_trim_small_positive(self):
        """Test trim value at +0.1 converts to 55%."""
        result = InputManager._trim_to_percent(0.1)
        assert result == 55, "Trim value +0.1 should be 55%"

    def test_trim_small_negative(self):
        """Test trim value at -0.1 converts to 45%."""
        result = InputManager._trim_to_percent(-0.1)
        assert result == 45, "Trim value -0.1 should be 45%"

    def test_trim_quarter_positive(self):
        """Test trim value at +0.25 converts to 62% (rounded down from 62.5)."""
        result = InputManager._trim_to_percent(0.25)
        assert result == 62, "Trim value +0.25 should be 62%"

    def test_trim_quarter_negative(self):
        """Test trim value at -0.25 converts to 37% (rounded down from 37.5)."""
        result = InputManager._trim_to_percent(-0.25)
        assert result == 37, "Trim value -0.25 should be 37%"

    def test_trim_three_quarters_positive(self):
        """Test trim value at +0.75 converts to 87% (rounded down from 87.5)."""
        result = InputManager._trim_to_percent(0.75)
        assert result == 87, "Trim value +0.75 should be 87%"

    def test_trim_three_quarters_negative(self):
        """Test trim value at -0.75 converts to 12% (rounded down from 12.5)."""
        result = InputManager._trim_to_percent(-0.75)
        assert result == 12, "Trim value -0.75 should be 12%"

    def test_trim_return_type_is_int(self):
        """Test that the method returns an integer, not a float."""
        result = InputManager._trim_to_percent(0.5)
        assert isinstance(result, int), "Result should be an integer"

    def test_trim_range_validation(self):
        """Test various values across the entire range to ensure consistent behavior."""
        # Calculate expected values using the actual formula to ensure test accuracy
        test_cases = [
            (-1.0, int((-1.0 + 1.0) / 2.0 * 100)),  # 0
            (-0.8, int((-0.8 + 1.0) / 2.0 * 100)),  # 9 (rounded down from 10.0)
            (-0.6, int((-0.6 + 1.0) / 2.0 * 100)),  # 20
            (-0.4, int((-0.4 + 1.0) / 2.0 * 100)),  # 30
            (-0.2, int((-0.2 + 1.0) / 2.0 * 100)),  # 40
            (0.0, int((0.0 + 1.0) / 2.0 * 100)),  # 50
            (0.2, int((0.2 + 1.0) / 2.0 * 100)),  # 60
            (0.4, int((0.4 + 1.0) / 2.0 * 100)),  # 70
            (0.6, int((0.6 + 1.0) / 2.0 * 100)),  # 80
            (0.8, int((0.8 + 1.0) / 2.0 * 100)),  # 90
            (1.0, int((1.0 + 1.0) / 2.0 * 100)),  # 100
        ]

        for trim_value, expected_percent in test_cases:
            result = InputManager._trim_to_percent(trim_value)
            assert result == expected_percent, (
                f"Trim value {trim_value} should convert to {expected_percent}%, but got {result}%"
            )

    def test_trim_formula_accuracy(self):
        """Test that the formula (trim + 1.0) / 2.0 * 100 is correctly implemented."""
        # Manually calculate expected value for a random trim value
        trim_value = 0.3
        expected = int((trim_value + 1.0) / 2.0 * 100)  # Should be 65
        result = InputManager._trim_to_percent(trim_value)
        assert result == expected, (
            f"Formula verification failed: expected {expected}%, got {result}%"
        )

    def test_user_reported_72_percent(self):
        """Test the user's reported 72% trim case."""
        # User reported 72%, which should correspond to trim value of ~0.44
        # Let's verify what 72% should actually be in trim value
        # 72% = (trim + 1.0) / 2.0 * 100
        # 0.72 = (trim + 1.0) / 2.0
        # 1.44 = trim + 1.0
        # trim = 0.44
        result = InputManager._trim_to_percent(0.44)
        assert result == 72, "Trim value 0.44 should convert to 72%"

    def test_user_reported_75_percent(self):
        """Test the user's reported 75% trim case."""
        # User reported 75%, which should correspond to trim value of 0.5
        result = InputManager._trim_to_percent(0.5)
        assert result == 75, "Trim value 0.5 should convert to 75%"

    def test_trim_increment_from_neutral(self):
        """Test incrementing trim from neutral (50%) by 5% clicks."""
        # Start at neutral (0.0 = 50%)
        # Each click adds 0.05 (5% of the range)
        # After 1 click: 0.05 → 52% (rounded down from 52.5%)
        # After 2 clicks: 0.10 → 55%
        # After 5 clicks: 0.25 → 62% (rounded down from 62.5%)
        # After 10 clicks: 0.50 → 75%

        assert InputManager._trim_to_percent(0.00) == 50
        assert InputManager._trim_to_percent(0.05) == 52
        assert InputManager._trim_to_percent(0.10) == 55
        assert InputManager._trim_to_percent(0.25) == 62
        assert InputManager._trim_to_percent(0.50) == 75

    def test_trim_decrement_from_neutral(self):
        """Test decrementing trim from neutral (50%) by 5% clicks."""
        # Start at neutral (0.0 = 50%)
        # Each click subtracts 0.05 (5% of the range)
        # After 1 click: -0.05 → 47% (rounded down from 47.5%)
        # After 2 clicks: -0.10 → 45%
        # After 5 clicks: -0.25 → 37% (rounded down from 37.5%)
        # After 10 clicks: -0.50 → 25%

        assert InputManager._trim_to_percent(0.00) == 50
        assert InputManager._trim_to_percent(-0.05) == 47
        assert InputManager._trim_to_percent(-0.10) == 45
        assert InputManager._trim_to_percent(-0.25) == 37
        assert InputManager._trim_to_percent(-0.50) == 25

    def test_trim_full_range_clicks(self):
        """Test clicking through the full range from -1.0 to +1.0."""
        # From -1.0 to +1.0 with 0.05 increments should be 40 clicks
        current_trim = -1.0
        for i in range(41):  # 0 to 40 inclusive = 41 steps
            percent = InputManager._trim_to_percent(current_trim)
            expected = int((current_trim + 1.0) / 2.0 * 100)
            assert percent == expected, (
                f"Click {i}: trim={current_trim:.2f} should be {expected}%, got {percent}%"
            )
            current_trim = min(1.0, current_trim + 0.05)


class TestTrimSharedBehavior:
    """Test shared behavior between pitch and rudder trim."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        """Create event bus."""
        return EventBus()

    @pytest.fixture
    def manager(self, event_bus: EventBus) -> InputManager:
        """Create input manager."""
        # Initialize pygame
        if not pygame.get_init():
            pygame.init()
        return InputManager(event_bus)

    def test_trim_values_persist_across_updates(self, manager: InputManager) -> None:
        """Test trim values persist across multiple updates."""
        # Set some trim
        manager.state.pitch_trim = 0.3
        manager.state.rudder_trim = -0.2

        # Update multiple times
        for _ in range(10):
            manager.update(0.016)

        # Values should persist
        assert manager.state.pitch_trim == 0.3
        assert manager.state.rudder_trim == -0.2

    def test_trim_values_published_in_state_event(
        self, manager: InputManager, event_bus: EventBus
    ) -> None:
        """Test trim values are published in InputStateEvent."""
        from airborne.core.input import InputStateEvent

        received_events = []

        def handler(event: InputStateEvent) -> None:
            received_events.append(event)

        event_bus.subscribe(InputStateEvent, handler)

        # Set some trim
        manager.state.pitch_trim = 0.5
        manager.state.rudder_trim = -0.3

        # Update to publish state
        manager.update(0.016)

        # Check event contains trim values
        assert len(received_events) > 0
        event = received_events[0]
        assert event.pitch_trim == 0.5
        assert event.rudder_trim == -0.3

    def test_trim_and_flight_controls_independent(self, manager: InputManager) -> None:
        """Test trim controls don't interfere with flight controls."""
        # Set some trim
        manager.state.pitch_trim = 0.5
        manager.state.rudder_trim = -0.3

        # Apply pitch and yaw inputs (without modifiers)
        with patch(PATCH_GET_MODS, return_value=0):
            keydown_pitch = Mock()
            keydown_pitch.type = pygame.KEYDOWN
            keydown_pitch.key = pygame.K_UP

            keydown_yaw = Mock()
            keydown_yaw.type = pygame.KEYDOWN
            keydown_yaw.key = pygame.K_COMMA

            manager.process_events([keydown_pitch, keydown_yaw])
            manager.update(0.016)

        # Flight controls should work
        assert manager.state.pitch != 0.0
        assert manager.state.yaw != 0.0

        # Trim should be unchanged
        assert manager.state.pitch_trim == 0.5
        assert manager.state.rudder_trim == -0.3
