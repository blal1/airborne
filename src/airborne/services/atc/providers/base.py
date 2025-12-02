"""Abstract base classes for ATC V2 ASR and NLU providers.

This module defines the interfaces that allow swapping between local
and remote implementations of speech recognition and natural language
understanding for voice-controlled ATC.

The design supports future network offloading to a global ATC server
for multiplayer scenarios.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ATCIntentType(Enum):
    """Types of ATC intents recognized by the NLU system."""

    # Unknown/unrecognized
    UNKNOWN = "unknown"

    # Ground operations
    REQUEST_TAXI = "request_taxi"
    REQUEST_PUSHBACK = "request_pushback"
    REPORT_READY_FOR_TAXI = "report_ready_for_taxi"
    REQUEST_TAXI_TO_RUNWAY = "request_taxi_to_runway"
    REQUEST_TAXI_TO_PARKING = "request_taxi_to_parking"

    # Tower operations
    READY_FOR_DEPARTURE = "ready_for_departure"
    REQUEST_TAKEOFF = "request_takeoff"
    REQUEST_LANDING = "request_landing"
    REPORT_DOWNWIND = "report_downwind"
    REPORT_BASE = "report_base"
    REPORT_FINAL = "report_final"
    REPORT_SHORT_FINAL = "report_short_final"
    REQUEST_GO_AROUND = "request_go_around"
    REQUEST_TOUCH_AND_GO = "request_touch_and_go"
    REPORT_CLEAR_OF_RUNWAY = "report_clear_of_runway"

    # Departure operations
    REQUEST_DEPARTURE_FREQUENCY = "request_departure_frequency"
    REPORT_AIRBORNE = "report_airborne"
    REQUEST_FLIGHT_FOLLOWING = "request_flight_following"

    # Approach operations
    REQUEST_APPROACH = "request_approach"
    REQUEST_ILS_APPROACH = "request_ils_approach"
    REQUEST_VISUAL_APPROACH = "request_visual_approach"
    REPORT_FIELD_IN_SIGHT = "report_field_in_sight"

    # Center/en-route operations
    REQUEST_ALTITUDE_CHANGE = "request_altitude_change"
    REQUEST_DIRECT = "request_direct"
    REPORT_POSITION = "report_position"

    # Common
    READBACK = "readback"
    ROGER = "roger"
    WILCO = "wilco"
    NEGATIVE = "negative"
    SAY_AGAIN = "say_again"
    STANDBY = "standby"


@dataclass
class ATCIntent:
    """Structured intent extracted from pilot speech.

    This dataclass represents the parsed result of NLU processing,
    containing the recognized intent and extracted slot values.

    Attributes:
        intent_type: The type of ATC request/response.
        confidence: Confidence score from NLU (0.0 to 1.0).
        callsign: Aircraft callsign if mentioned.
        runway: Runway designator if mentioned (e.g., "27L", "09").
        taxiway: Taxiway designator if mentioned (e.g., "A", "B1").
        altitude: Altitude if mentioned (in feet).
        heading: Heading if mentioned (in degrees).
        frequency: Frequency if mentioned (e.g., "121.9").
        position: Position report if mentioned (e.g., "downwind", "final").
        destination: Destination if mentioned (ICAO or fix name).
        raw_text: Original transcribed text.
        slots: Additional extracted slot values.
    """

    intent_type: ATCIntentType = ATCIntentType.UNKNOWN
    confidence: float = 0.0
    callsign: str | None = None
    runway: str | None = None
    taxiway: str | None = None
    altitude: int | None = None
    heading: int | None = None
    frequency: str | None = None
    position: str | None = None
    destination: str | None = None
    raw_text: str = ""
    slots: dict[str, Any] = field(default_factory=dict)

    def is_valid(self) -> bool:
        """Check if the intent is valid for processing.

        Returns:
            True if intent is recognized with sufficient confidence.
        """
        return (
            self.intent_type != ATCIntentType.UNKNOWN
            and self.confidence >= 0.5
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation suitable for JSON.
        """
        return {
            "intent_type": self.intent_type.value,
            "confidence": self.confidence,
            "callsign": self.callsign,
            "runway": self.runway,
            "taxiway": self.taxiway,
            "altitude": self.altitude,
            "heading": self.heading,
            "frequency": self.frequency,
            "position": self.position,
            "destination": self.destination,
            "raw_text": self.raw_text,
            "slots": self.slots,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ATCIntent":
        """Create from dictionary.

        Args:
            data: Dictionary with intent data.

        Returns:
            ATCIntent instance.
        """
        intent_type_str = data.get("intent_type", "unknown")
        try:
            intent_type = ATCIntentType(intent_type_str)
        except ValueError:
            intent_type = ATCIntentType.UNKNOWN

        return cls(
            intent_type=intent_type,
            confidence=data.get("confidence", 0.0),
            callsign=data.get("callsign"),
            runway=data.get("runway"),
            taxiway=data.get("taxiway"),
            altitude=data.get("altitude"),
            heading=data.get("heading"),
            frequency=data.get("frequency"),
            position=data.get("position"),
            destination=data.get("destination"),
            raw_text=data.get("raw_text", ""),
            slots=data.get("slots", {}),
        )


class IASRProvider(ABC):
    """Abstract interface for Automatic Speech Recognition providers.

    Implementations can be local (faster-whisper) or remote (network).
    The interface is designed to be async-friendly for network operations.
    """

    @abstractmethod
    def initialize(self, config: dict[str, Any]) -> None:
        """Initialize the ASR provider.

        Args:
            config: Provider-specific configuration.
                   For local: model name, device, compute type.
                   For remote: server URL, API key.
        """
        pass

    @abstractmethod
    def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> str:
        """Transcribe audio to text.

        Args:
            audio_data: Raw PCM audio bytes (16-bit signed, mono).
            sample_rate: Audio sample rate in Hz.

        Returns:
            Transcribed text string.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is ready for use.

        Returns:
            True if provider is initialized and operational.
        """
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Release provider resources."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Get provider name for logging/display."""
        pass


class INLUProvider(ABC):
    """Abstract interface for Natural Language Understanding providers.

    Implementations can be local (llama-cpp) or remote (network).
    The interface extracts structured intents from transcribed text.
    """

    @abstractmethod
    def initialize(self, config: dict[str, Any]) -> None:
        """Initialize the NLU provider.

        Args:
            config: Provider-specific configuration.
                   For local: model path, context size, temperature.
                   For remote: server URL, API key.
        """
        pass

    @abstractmethod
    def extract_intent(self, text: str, context: dict[str, Any] | None = None) -> ATCIntent:
        """Extract structured intent from transcribed text.

        Args:
            text: Transcribed pilot speech.
            context: Optional flight context (phase, position, frequencies).

        Returns:
            ATCIntent with extracted slots and confidence.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is ready for use.

        Returns:
            True if provider is initialized and operational.
        """
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Release provider resources."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Get provider name for logging/display."""
        pass
