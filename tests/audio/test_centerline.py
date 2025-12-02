"""Tests for Centerline Beep Manager."""

from unittest.mock import MagicMock

import pytest

from airborne.audio.centerline import CenterlineBeepManager, CenterlineConfig
from airborne.core.messaging import MessageQueue, MessageTopic


class TestCenterlineConfig:
    """Test CenterlineConfig defaults."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = CenterlineConfig()

        assert config.beep_interval_s == 0.5
        assert config.max_deviation_m == 5.0
        assert config.deviation_threshold_m == 0.3
        assert config.on_centerline_beep is True

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = CenterlineConfig(
            beep_interval_s=1.0,
            max_deviation_m=3.0,
            deviation_threshold_m=0.5,
            on_centerline_beep=False,
        )

        assert config.beep_interval_s == 1.0
        assert config.max_deviation_m == 3.0
        assert config.deviation_threshold_m == 0.5
        assert config.on_centerline_beep is False


class TestCenterlineBeepManager:
    """Test CenterlineBeepManager."""

    @pytest.fixture
    def mock_queue(self) -> MagicMock:
        """Create mock message queue."""
        return MagicMock(spec=MessageQueue)

    @pytest.fixture
    def manager(self, mock_queue: MagicMock) -> CenterlineBeepManager:
        """Create beep manager with default config."""
        return CenterlineBeepManager(mock_queue)

    def test_init_disabled(self, manager: CenterlineBeepManager) -> None:
        """Test that manager starts disabled."""
        assert not manager.enabled

    def test_enable_disable(self, manager: CenterlineBeepManager) -> None:
        """Test enable/disable functionality."""
        manager.enable()
        assert manager.enabled

        manager.disable()
        assert not manager.enabled

    def test_toggle(self, manager: CenterlineBeepManager) -> None:
        """Test toggle functionality."""
        assert not manager.enabled

        result = manager.toggle()
        assert result is True
        assert manager.enabled

        result = manager.toggle()
        assert result is False
        assert not manager.enabled

    def test_no_beep_when_disabled(
        self, manager: CenterlineBeepManager, mock_queue: MagicMock
    ) -> None:
        """Test that no beeps occur when disabled."""
        # Manager starts disabled
        result = manager.update((2.0, "left"), 1.0)

        assert result is False
        mock_queue.publish.assert_not_called()

    def test_no_beep_when_no_deviation(
        self, manager: CenterlineBeepManager, mock_queue: MagicMock
    ) -> None:
        """Test no beep when deviation is None (not on taxiway)."""
        manager.enable()
        result = manager.update(None, 1.0)

        assert result is False
        mock_queue.publish.assert_not_called()

    def test_beep_interval_respected(
        self, manager: CenterlineBeepManager, mock_queue: MagicMock
    ) -> None:
        """Test that beep interval is respected."""
        manager.enable()

        # First beep should occur (time 1.0, last_beep_time 0.0 -> diff 1.0 > 0.5)
        result1 = manager.update((2.0, "left"), 1.0)
        assert result1 is True
        assert mock_queue.publish.call_count == 1

        # Second beep too soon - should not occur (1.3 - 1.0 = 0.3 < 0.5)
        result2 = manager.update((2.0, "left"), 1.3)
        assert result2 is False
        assert mock_queue.publish.call_count == 1  # Still 1

        # Third beep after interval - should occur (1.6 - 1.0 = 0.6 > 0.5)
        result3 = manager.update((2.0, "left"), 1.6)
        assert result3 is True
        assert mock_queue.publish.call_count == 2

    def test_beep_panned_left(self, manager: CenterlineBeepManager, mock_queue: MagicMock) -> None:
        """Test that left deviation produces left-panned beep."""
        manager.enable()
        manager.update((2.5, "left"), 1.0)  # 2.5m left, max is 5m

        mock_queue.publish.assert_called_once()
        message = mock_queue.publish.call_args[0][0]

        assert message.topic == MessageTopic.PLAY_SOUND_SPATIAL
        # Pan should be negative (left) and proportional to deviation
        # 2.5m / 5.0m = 0.5, so position.x should be -5.0 (0.5 * 10)
        position = message.data["position"]
        assert position["x"] == pytest.approx(-5.0)

    def test_beep_panned_right(self, manager: CenterlineBeepManager, mock_queue: MagicMock) -> None:
        """Test that right deviation produces right-panned beep."""
        manager.enable()
        manager.update((3.0, "right"), 1.0)  # 3m right

        mock_queue.publish.assert_called_once()
        message = mock_queue.publish.call_args[0][0]

        # 3m / 5m = 0.6, position.x = 6.0
        position = message.data["position"]
        assert position["x"] == pytest.approx(6.0)

    def test_beep_centered(self, manager: CenterlineBeepManager, mock_queue: MagicMock) -> None:
        """Test that on-centerline produces centered beep."""
        manager.enable()
        manager.update((0.1, "left"), 1.0)  # 0.1m < 0.3m threshold

        mock_queue.publish.assert_called_once()
        message = mock_queue.publish.call_args[0][0]

        # Should be centered
        position = message.data["position"]
        assert position["x"] == pytest.approx(0.0)

    def test_no_beep_on_centerline_when_disabled(self, mock_queue: MagicMock) -> None:
        """Test no centered beep when on_centerline_beep is False."""
        config = CenterlineConfig(on_centerline_beep=False)
        manager = CenterlineBeepManager(mock_queue, config)
        manager.enable()

        result = manager.update((0.1, "left"), 1.0)  # On centerline

        assert result is False
        mock_queue.publish.assert_not_called()

    def test_max_deviation_clamped(
        self, manager: CenterlineBeepManager, mock_queue: MagicMock
    ) -> None:
        """Test that deviation beyond max is clamped."""
        manager.enable()
        manager.update((10.0, "right"), 1.0)  # 10m > 5m max

        mock_queue.publish.assert_called_once()
        message = mock_queue.publish.call_args[0][0]

        # Should be clamped to max (pan = 1.0, position.x = 10.0)
        position = message.data["position"]
        assert position["x"] == pytest.approx(10.0)

    def test_beep_sound_id(self, manager: CenterlineBeepManager, mock_queue: MagicMock) -> None:
        """Test that beep uses correct sound ID."""
        manager.enable()
        manager.update((2.0, "left"), 1.0)

        message = mock_queue.publish.call_args[0][0]
        assert message.data["sound_id"] == "centerline_beep"

    def test_beep_volume(self, manager: CenterlineBeepManager, mock_queue: MagicMock) -> None:
        """Test beep volume."""
        manager.enable()
        manager.update((2.0, "left"), 1.0)

        message = mock_queue.publish.call_args[0][0]
        assert message.data["volume"] == 0.7

    def test_no_message_queue(self) -> None:
        """Test graceful handling when no message queue."""
        manager = CenterlineBeepManager(message_queue=None)
        manager.enable()

        # Should not raise, just log warning
        result = manager.update((2.0, "left"), 1.0)
        assert result is True  # Would have beeped if queue existed
