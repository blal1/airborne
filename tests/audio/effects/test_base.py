"""Tests for audio effect protocol and effect manager."""

from unittest.mock import Mock

import pytest

from airborne.audio.effects.base import EffectManager, IAudioEffect


class MockEffect:
    """Mock effect for testing IAudioEffect protocol."""

    def __init__(self) -> None:
        """Initialize mock effect with tracking."""
        self.applied_channels: list = []
        self.removed_channels: list = []

    def apply_to_channel(self, channel) -> None:  # type: ignore[no-untyped-def]
        """Track channel applications."""
        self.applied_channels.append(channel)

    def remove_from_channel(self, channel) -> None:  # type: ignore[no-untyped-def]
        """Track channel removals."""
        self.removed_channels.append(channel)


class TestIAudioEffectProtocol:
    """Test suite for IAudioEffect protocol."""

    def test_protocol_requires_apply_to_channel(self) -> None:
        """Test that protocol requires apply_to_channel method."""
        effect = MockEffect()
        assert hasattr(effect, "apply_to_channel")
        assert callable(effect.apply_to_channel)

    def test_protocol_requires_remove_from_channel(self) -> None:
        """Test that protocol requires remove_from_channel method."""
        effect = MockEffect()
        assert hasattr(effect, "remove_from_channel")
        assert callable(effect.remove_from_channel)

    def test_mock_effect_implements_protocol(self) -> None:
        """Test that MockEffect implements IAudioEffect protocol."""
        effect: IAudioEffect = MockEffect()
        channel = Mock()

        effect.apply_to_channel(channel)
        effect.remove_from_channel(channel)

        # MockEffect tracks calls
        assert isinstance(effect, MockEffect)
        assert channel in effect.applied_channels
        assert channel in effect.removed_channels


class TestEffectManager:
    """Test suite for EffectManager class."""

    @pytest.fixture
    def audio_engine(self) -> Mock:
        """Create mock audio engine."""
        engine = Mock()
        engine.get_channel = Mock(return_value=None)
        return engine

    @pytest.fixture
    def manager(self, audio_engine: Mock) -> EffectManager:
        """Create EffectManager instance."""
        return EffectManager(audio_engine)

    @pytest.fixture
    def mock_effect(self) -> MockEffect:
        """Create mock effect."""
        return MockEffect()

    def test_register_effect(self, manager: EffectManager, mock_effect: MockEffect) -> None:
        """Test registering a named effect."""
        manager.register_effect("test_effect", mock_effect)
        assert manager._effects["test_effect"] is mock_effect

    def test_unregister_effect(self, manager: EffectManager, mock_effect: MockEffect) -> None:
        """Test unregistering a named effect."""
        manager.register_effect("test_effect", mock_effect)
        manager.unregister_effect("test_effect")
        assert "test_effect" not in manager._effects

    def test_unregister_nonexistent_effect(self, manager: EffectManager) -> None:
        """Test unregistering an effect that doesn't exist."""
        # Should not raise error
        manager.unregister_effect("nonexistent")

    def test_apply_effect_success(
        self, manager: EffectManager, audio_engine: Mock, mock_effect: MockEffect
    ) -> None:
        """Test applying an effect to a channel."""
        # Arrange
        mock_channel = Mock()
        audio_engine.get_channel.return_value = mock_channel
        manager.register_effect("test_effect", mock_effect)

        # Act
        result = manager.apply_effect("test_effect", 42)

        # Assert
        assert result is True
        audio_engine.get_channel.assert_called_once_with(42)
        assert mock_channel in mock_effect.applied_channels
        assert manager.get_applied_effect(42) == "test_effect"

    def test_apply_effect_unregistered_effect(
        self, manager: EffectManager, audio_engine: Mock
    ) -> None:
        """Test applying an unregistered effect."""
        result = manager.apply_effect("nonexistent", 42)
        assert result is False
        audio_engine.get_channel.assert_not_called()

    def test_apply_effect_channel_not_found(
        self, manager: EffectManager, audio_engine: Mock, mock_effect: MockEffect
    ) -> None:
        """Test applying effect when channel doesn't exist."""
        # Arrange
        audio_engine.get_channel.return_value = None
        manager.register_effect("test_effect", mock_effect)

        # Act
        result = manager.apply_effect("test_effect", 42)

        # Assert
        assert result is False
        assert len(mock_effect.applied_channels) == 0

    def test_apply_effect_replaces_existing(
        self, manager: EffectManager, audio_engine: Mock
    ) -> None:
        """Test that applying a new effect removes the old one."""
        # Arrange
        mock_channel = Mock()
        audio_engine.get_channel.return_value = mock_channel
        effect1 = MockEffect()
        effect2 = MockEffect()
        manager.register_effect("effect1", effect1)
        manager.register_effect("effect2", effect2)

        # Apply first effect
        manager.apply_effect("effect1", 42)
        assert manager.get_applied_effect(42) == "effect1"

        # Apply second effect (should remove first)
        manager.apply_effect("effect2", 42)

        # Assert
        assert manager.get_applied_effect(42) == "effect2"
        assert mock_channel in effect1.removed_channels
        assert mock_channel in effect2.applied_channels

    def test_remove_effect_success(
        self, manager: EffectManager, audio_engine: Mock, mock_effect: MockEffect
    ) -> None:
        """Test removing an effect from a channel."""
        # Arrange
        mock_channel = Mock()
        audio_engine.get_channel.return_value = mock_channel
        manager.register_effect("test_effect", mock_effect)
        manager.apply_effect("test_effect", 42)

        # Act
        result = manager.remove_effect(42)

        # Assert
        assert result is True
        assert mock_channel in mock_effect.removed_channels
        assert manager.get_applied_effect(42) is None

    def test_remove_effect_no_effect_applied(self, manager: EffectManager) -> None:
        """Test removing effect when none is applied."""
        result = manager.remove_effect(42)
        assert result is False

    def test_remove_effect_effect_unregistered(
        self, manager: EffectManager, audio_engine: Mock, mock_effect: MockEffect
    ) -> None:
        """Test removing effect after it was unregistered."""
        # Arrange
        mock_channel = Mock()
        audio_engine.get_channel.return_value = mock_channel
        manager.register_effect("test_effect", mock_effect)
        manager.apply_effect("test_effect", 42)
        manager.unregister_effect("test_effect")

        # Act
        result = manager.remove_effect(42)

        # Assert - should clean up tracking even though effect is gone
        assert result is False
        assert manager.get_applied_effect(42) is None

    def test_remove_effect_channel_not_found(
        self, manager: EffectManager, audio_engine: Mock, mock_effect: MockEffect
    ) -> None:
        """Test removing effect when channel no longer exists."""
        # Arrange
        mock_channel = Mock()
        audio_engine.get_channel.return_value = mock_channel
        manager.register_effect("test_effect", mock_effect)
        manager.apply_effect("test_effect", 42)

        # Channel disappears
        audio_engine.get_channel.return_value = None

        # Act
        result = manager.remove_effect(42)

        # Assert - should clean up tracking even though channel is gone
        assert result is True
        assert manager.get_applied_effect(42) is None

    def test_get_applied_effect(
        self, manager: EffectManager, audio_engine: Mock, mock_effect: MockEffect
    ) -> None:
        """Test querying applied effect."""
        # No effect applied
        assert manager.get_applied_effect(42) is None

        # Apply effect
        audio_engine.get_channel.return_value = Mock()
        manager.register_effect("test_effect", mock_effect)
        manager.apply_effect("test_effect", 42)

        # Effect applied
        assert manager.get_applied_effect(42) == "test_effect"

    def test_clear_all_effects(self, manager: EffectManager, audio_engine: Mock) -> None:
        """Test clearing all effects from all channels."""
        # Arrange
        mock_channel1 = Mock()
        mock_channel2 = Mock()
        effect1 = MockEffect()
        effect2 = MockEffect()

        audio_engine.get_channel.side_effect = [mock_channel1, mock_channel2]
        manager.register_effect("effect1", effect1)
        manager.register_effect("effect2", effect2)
        manager.apply_effect("effect1", 1)
        manager.apply_effect("effect2", 2)

        # Reset mock for removal phase
        audio_engine.get_channel.side_effect = [mock_channel1, mock_channel2]

        # Act
        manager.clear_all_effects()

        # Assert
        assert manager.get_applied_effect(1) is None
        assert manager.get_applied_effect(2) is None
        assert mock_channel1 in effect1.removed_channels
        assert mock_channel2 in effect2.removed_channels

    def test_multiple_channels_different_effects(
        self, manager: EffectManager, audio_engine: Mock
    ) -> None:
        """Test applying different effects to different channels."""
        # Arrange
        channel1 = Mock()
        channel2 = Mock()
        effect1 = MockEffect()
        effect2 = MockEffect()

        def get_channel_side_effect(source_id: int):  # type: ignore[no-untyped-def]
            return channel1 if source_id == 1 else channel2

        audio_engine.get_channel.side_effect = get_channel_side_effect
        manager.register_effect("effect1", effect1)
        manager.register_effect("effect2", effect2)

        # Act
        manager.apply_effect("effect1", 1)
        manager.apply_effect("effect2", 2)

        # Assert
        assert manager.get_applied_effect(1) == "effect1"
        assert manager.get_applied_effect(2) == "effect2"
        assert channel1 in effect1.applied_channels
        assert channel2 in effect2.applied_channels
        assert channel1 not in effect2.applied_channels
        assert channel2 not in effect1.applied_channels
