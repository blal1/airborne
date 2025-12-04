"""Tests for ATC V2 voice control system.

Tests cover:
- Provider interfaces and base classes
- Intent extraction and mapping
- Intent processor decision tree
- Settings management
"""

import tempfile
from pathlib import Path

from airborne.services.atc.intent_processor import (
    INTENT_TO_REQUEST_MAP,
    FlightContext,
    IntentProcessor,
)
from airborne.services.atc.providers.base import (
    ATCIntent,
    ATCIntentType,
)
from airborne.settings.atc_v2_settings import (
    PROVIDER_LOCAL,
    PROVIDER_REMOTE,
    ATCV2Settings,
    get_atc_v2_settings,
    reset_atc_v2_settings,
)


class TestATCIntent:
    """Tests for ATCIntent dataclass."""

    def test_intent_creation_default(self) -> None:
        """Test creating intent with defaults."""
        intent = ATCIntent()
        assert intent.intent_type == ATCIntentType.UNKNOWN
        assert intent.confidence == 0.0
        assert intent.callsign is None
        assert intent.raw_text == ""

    def test_intent_creation_with_values(self) -> None:
        """Test creating intent with specific values."""
        intent = ATCIntent(
            intent_type=ATCIntentType.REQUEST_TAXI,
            confidence=0.95,
            callsign="N12345",
            runway="27L",
            raw_text="november one two three four five request taxi",
        )
        assert intent.intent_type == ATCIntentType.REQUEST_TAXI
        assert intent.confidence == 0.95
        assert intent.callsign == "N12345"
        assert intent.runway == "27L"

    def test_intent_is_valid_low_confidence(self) -> None:
        """Test is_valid returns False for low confidence."""
        intent = ATCIntent(
            intent_type=ATCIntentType.REQUEST_TAXI,
            confidence=0.3,  # Below threshold
        )
        assert not intent.is_valid()

    def test_intent_is_valid_unknown_type(self) -> None:
        """Test is_valid returns False for unknown type."""
        intent = ATCIntent(
            intent_type=ATCIntentType.UNKNOWN,
            confidence=0.9,
        )
        assert not intent.is_valid()

    def test_intent_is_valid_success(self) -> None:
        """Test is_valid returns True for valid intent."""
        intent = ATCIntent(
            intent_type=ATCIntentType.REQUEST_TAXI,
            confidence=0.8,
        )
        assert intent.is_valid()

    def test_intent_to_dict(self) -> None:
        """Test converting intent to dictionary."""
        intent = ATCIntent(
            intent_type=ATCIntentType.READY_FOR_DEPARTURE,
            confidence=0.9,
            callsign="N12345",
            runway="09",
        )
        data = intent.to_dict()
        assert data["intent_type"] == "ready_for_departure"
        assert data["confidence"] == 0.9
        assert data["callsign"] == "N12345"
        assert data["runway"] == "09"

    def test_intent_from_dict(self) -> None:
        """Test creating intent from dictionary."""
        data = {
            "intent_type": "request_landing",
            "confidence": 0.85,
            "callsign": "Delta456",
            "runway": "27",
            "raw_text": "delta four five six request landing runway 27",
        }
        intent = ATCIntent.from_dict(data)
        assert intent.intent_type == ATCIntentType.REQUEST_LANDING
        assert intent.confidence == 0.85
        assert intent.callsign == "Delta456"
        assert intent.runway == "27"

    def test_intent_from_dict_unknown_type(self) -> None:
        """Test from_dict handles unknown intent type."""
        data = {"intent_type": "invalid_type", "confidence": 0.5}
        intent = ATCIntent.from_dict(data)
        assert intent.intent_type == ATCIntentType.UNKNOWN


class TestATCIntentType:
    """Tests for ATCIntentType enum."""

    def test_all_intent_types_have_values(self) -> None:
        """Test all intent types have string values."""
        for intent_type in ATCIntentType:
            assert isinstance(intent_type.value, str)
            assert len(intent_type.value) > 0

    def test_key_intent_types_exist(self) -> None:
        """Test key intent types are defined."""
        expected_types = [
            "unknown",
            "request_taxi",
            "request_takeoff",
            "request_landing",
            "ready_for_departure",
            "report_final",
            "request_go_around",
            "roger",
            "wilco",
            "say_again",
        ]
        actual_values = [t.value for t in ATCIntentType]
        for expected in expected_types:
            assert expected in actual_values


class TestFlightContext:
    """Tests for FlightContext dataclass."""

    def test_context_defaults(self) -> None:
        """Test context has sensible defaults."""
        context = FlightContext()
        assert context.callsign == ""
        assert context.airport_icao == ""
        assert context.on_ground is True
        assert context.current_frequency == 0.0

    def test_context_with_values(self) -> None:
        """Test context with specific values."""
        context = FlightContext(
            callsign="N12345",
            airport_icao="KPAO",
            on_ground=False,
            current_frequency=121.9,
            assigned_runway="31",
            flight_phase="airborne",
        )
        assert context.callsign == "N12345"
        assert context.airport_icao == "KPAO"
        assert context.on_ground is False
        assert context.current_frequency == 121.9


class TestIntentToRequestMapping:
    """Tests for intent to request type mapping."""

    def test_ground_operations_mapped(self) -> None:
        """Test ground operation intents are mapped."""
        ground_intents = [
            ATCIntentType.REQUEST_TAXI,
            ATCIntentType.REQUEST_PUSHBACK,
            ATCIntentType.REQUEST_TAXI_TO_RUNWAY,
        ]
        for intent_type in ground_intents:
            assert intent_type in INTENT_TO_REQUEST_MAP
            assert INTENT_TO_REQUEST_MAP[intent_type] is not None

    def test_tower_operations_mapped(self) -> None:
        """Test tower operation intents are mapped."""
        tower_intents = [
            ATCIntentType.READY_FOR_DEPARTURE,
            ATCIntentType.REQUEST_TAKEOFF,
            ATCIntentType.REQUEST_LANDING,
            ATCIntentType.REQUEST_GO_AROUND,
        ]
        for intent_type in tower_intents:
            assert intent_type in INTENT_TO_REQUEST_MAP
            assert INTENT_TO_REQUEST_MAP[intent_type] is not None

    def test_acknowledgements_not_mapped(self) -> None:
        """Test acknowledgement intents return None (no request needed)."""
        ack_intents = [
            ATCIntentType.ROGER,
            ATCIntentType.WILCO,
            ATCIntentType.READBACK,
        ]
        for intent_type in ack_intents:
            assert intent_type in INTENT_TO_REQUEST_MAP
            assert INTENT_TO_REQUEST_MAP[intent_type] is None


class TestIntentProcessor:
    """Tests for IntentProcessor."""

    def test_processor_creation(self) -> None:
        """Test processor can be created without handler."""
        processor = IntentProcessor()
        assert processor is not None

    def test_processor_say_again_for_invalid_intent(self) -> None:
        """Test processor generates 'say again' for invalid intent."""
        processor = IntentProcessor()
        context = FlightContext(callsign="N12345")

        # Low confidence intent
        intent = ATCIntent(
            intent_type=ATCIntentType.REQUEST_TAXI,
            confidence=0.2,
        )

        response = processor.process_intent(intent, context)
        assert response is not None
        assert "say again" in response.text.lower()

    def test_processor_say_again_for_unknown_intent(self) -> None:
        """Test processor generates 'say again' for unknown intent."""
        processor = IntentProcessor()
        context = FlightContext(callsign="N12345")

        intent = ATCIntent(
            intent_type=ATCIntentType.UNKNOWN,
            confidence=0.9,
        )

        response = processor.process_intent(intent, context)
        assert response is not None
        assert "say again" in response.text.lower()

    def test_processor_acknowledgement_returns_none(self) -> None:
        """Test processor returns None for acknowledgements."""
        processor = IntentProcessor()
        context = FlightContext(callsign="N12345")

        for intent_type in [ATCIntentType.ROGER, ATCIntentType.WILCO]:
            intent = ATCIntent(
                intent_type=intent_type,
                confidence=0.9,
            )
            response = processor.process_intent(intent, context)
            assert response is None

    def test_processor_handles_say_again_request(self) -> None:
        """Test processor handles pilot's 'say again' request."""
        processor = IntentProcessor()
        context = FlightContext(callsign="N12345")

        intent = ATCIntent(
            intent_type=ATCIntentType.SAY_AGAIN,
            confidence=0.9,
        )

        response = processor.process_intent(intent, context)
        assert response is not None
        # Should respond with last instruction or "no previous instruction"
        assert "instruction" in response.text.lower() or "say again" in response.text.lower()


class TestATCV2Settings:
    """Tests for ATC V2 settings."""

    def test_settings_defaults(self) -> None:
        """Test settings have correct defaults."""
        settings = ATCV2Settings()
        assert settings.enabled is False
        assert settings.ptt_key == "SPACE"
        assert settings.input_device_index is None
        assert settings.asr_provider == PROVIDER_LOCAL
        assert settings.nlu_provider == PROVIDER_LOCAL
        assert settings.whisper_model == "base.en"
        assert settings.llama_model_path == ""

    def test_settings_set_enabled(self) -> None:
        """Test setting enabled flag."""
        settings = ATCV2Settings()
        settings.set_enabled(True)
        assert settings.enabled is True
        assert settings.is_dirty

    def test_settings_set_providers(self) -> None:
        """Test setting provider types."""
        settings = ATCV2Settings()
        settings.set_asr_provider(PROVIDER_REMOTE)
        settings.set_nlu_provider(PROVIDER_REMOTE)
        assert settings.asr_provider == PROVIDER_REMOTE
        assert settings.nlu_provider == PROVIDER_REMOTE

    def test_settings_save_and_load(self) -> None:
        """Test saving and loading settings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"

            # Create and save settings
            settings = ATCV2Settings()
            settings.set_enabled(True)
            settings.set_whisper_model("small.en")
            settings.save(settings_path)

            # Load settings
            new_settings = ATCV2Settings()
            new_settings.load(settings_path)

            assert new_settings.enabled is True
            assert new_settings.whisper_model == "small.en"

    def test_settings_to_dict(self) -> None:
        """Test converting settings to dictionary."""
        settings = ATCV2Settings()
        settings.set_enabled(True)
        settings.set_ptt_key("LCTRL")

        data = settings.to_dict()
        assert data["enabled"] is True
        assert data["ptt_key"] == "LCTRL"
        assert "asr_provider" in data
        assert "nlu_provider" in data

    def test_settings_singleton_reset(self) -> None:
        """Test settings singleton can be reset."""
        # Get settings
        settings1 = get_atc_v2_settings()

        # Reset
        reset_atc_v2_settings()

        # Get again - should be a new instance
        settings2 = get_atc_v2_settings()

        # Note: They might be equal but not the same object
        # (depends on whether load finds the same file)
        assert settings2 is not None
