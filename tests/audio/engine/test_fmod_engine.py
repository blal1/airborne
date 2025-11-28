"""Tests for FMOD audio engine."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from airborne.audio.engine.fmod_engine import FMODEngine


class TestFMODEnginePublicAccessors:
    """Test suite for FMODEngine public accessor methods."""

    @pytest.fixture
    def mock_fmod(self) -> MagicMock:
        """Create mock pyfmodex module."""
        mock = MagicMock()
        mock.System.return_value = Mock()
        return mock

    @pytest.fixture
    def engine(self, mock_fmod: MagicMock) -> FMODEngine:
        """Create FMODEngine instance with mocked FMOD."""
        with (
            patch("airborne.audio.engine.fmod_engine.pyfmodex", mock_fmod),
            patch("airborne.audio.engine.fmod_engine.FMOD_AVAILABLE", True),
        ):
            engine = FMODEngine()
            engine.initialize({"max_channels": 32})
            return engine

    def test_get_channel_returns_valid_channel(self, engine: FMODEngine) -> None:
        """Test get_channel returns channel for active source."""
        # Arrange: Create mock channel and add to internal channels dict
        mock_channel = Mock()
        engine._channels[42] = mock_channel

        # Act: Get the channel
        channel = engine.get_channel(42)

        # Assert: Should return the mock channel
        assert channel is mock_channel

    def test_get_channel_returns_none_for_invalid_id(self, engine: FMODEngine) -> None:
        """Test get_channel returns None for invalid source ID."""
        # Act: Try to get channel for non-existent source
        channel = engine.get_channel(999)

        # Assert: Should return None
        assert channel is None

    def test_get_channel_returns_none_for_stopped(self, engine: FMODEngine) -> None:
        """Test get_channel returns None for stopped source."""
        # Arrange: Add channel then remove it (simulating stopped source)
        engine._channels[42] = Mock()
        del engine._channels[42]

        # Act: Try to get the stopped channel
        channel = engine.get_channel(42)

        # Assert: Should return None
        assert channel is None

    def test_get_system_returns_system_when_initialized(self, engine: FMODEngine) -> None:
        """Test get_system returns FMOD system when initialized."""
        # Act: Get the system
        system = engine.get_system()

        # Assert: Should return the system instance
        assert system is not None
        assert system is engine._system

    def test_get_system_returns_none_when_not_initialized(self, mock_fmod: MagicMock) -> None:
        """Test get_system returns None when not initialized."""
        # Arrange: Create engine but don't initialize
        with (
            patch("airborne.audio.engine.fmod_engine.pyfmodex", mock_fmod),
            patch("airborne.audio.engine.fmod_engine.FMOD_AVAILABLE", True),
        ):
            engine = FMODEngine()

        # Act: Try to get system before initialization
        system = engine.get_system()

        # Assert: Should return None
        assert system is None
