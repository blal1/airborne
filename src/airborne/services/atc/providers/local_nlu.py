"""Local NLU provider using llama-cpp-python.

This module provides intent extraction from transcribed pilot speech using
a local Llama model via llama-cpp-python. It uses structured prompting
to produce reliable JSON output for slot filling.

Typical usage:
    nlu = LocalNLUProvider()
    nlu.initialize({"model_path": "/path/to/llama-3.2-3B.gguf"})

    intent = nlu.extract_intent("november one two three four request taxi")
    print(f"Intent: {intent.intent_type}, Callsign: {intent.callsign}")
"""

import json
import logging
import re
from typing import Any

from airborne.services.atc.providers.base import ATCIntent, ATCIntentType, INLUProvider

logger = logging.getLogger(__name__)

# Try to import llama-cpp-python
try:
    from llama_cpp import Llama

    LLAMA_CPP_AVAILABLE = True
except ImportError:
    LLAMA_CPP_AVAILABLE = False
    Llama = None  # type: ignore[assignment,misc]


# System prompt for ATC intent extraction
SYSTEM_PROMPT = """You are an aviation ATC intent parser. Extract the intent and slots from pilot radio communications.

Output ONLY a valid JSON object with these fields:
- intent: One of the intent types listed below
- confidence: Float 0.0-1.0 indicating confidence
- callsign: Aircraft callsign if mentioned (e.g., "N12345", "Delta 456")
- runway: Runway designator if mentioned (e.g., "27L", "09", "36")
- taxiway: Taxiway if mentioned (e.g., "A", "B1", "C")
- altitude: Altitude in feet if mentioned (integer)
- heading: Heading in degrees if mentioned (integer)
- frequency: Radio frequency if mentioned (e.g., "121.9")
- position: Position report if mentioned (e.g., "downwind", "final", "10 miles out")
- destination: Destination airport/fix if mentioned

Intent types:
- request_taxi: Requesting taxi clearance
- request_pushback: Requesting pushback clearance
- ready_for_departure: Reporting ready at runway
- request_takeoff: Requesting takeoff clearance
- request_landing: Requesting landing clearance
- report_downwind: Position report on downwind leg
- report_base: Position report on base leg
- report_final: Position report on final approach
- report_short_final: Position report on short final
- request_go_around: Requesting/announcing go-around
- request_touch_and_go: Requesting touch-and-go
- report_clear_of_runway: Reporting clear of runway
- request_departure_frequency: Requesting departure frequency
- report_airborne: Reporting airborne
- request_approach: Requesting approach clearance
- request_altitude_change: Requesting altitude change
- request_direct: Requesting direct routing
- report_position: General position report
- readback: Reading back instructions
- roger: Acknowledging
- wilco: Will comply
- negative: Declining/unable
- say_again: Requesting repeat
- unknown: Cannot determine intent

Example input: "November one two three four five requesting taxi to runway two seven"
Example output: {"intent": "request_taxi", "confidence": 0.95, "callsign": "N12345", "runway": "27", "taxiway": null, "altitude": null, "heading": null, "frequency": null, "position": null, "destination": null}
"""

USER_PROMPT_TEMPLATE = """Parse this pilot transmission and output JSON only:
"{text}"

JSON:"""


class LocalNLUProvider(INLUProvider):
    """Local NLU provider using llama-cpp-python.

    This provider uses a local Llama model to extract structured intents
    from transcribed pilot speech. It works offline with GGUF model files.
    """

    def __init__(self) -> None:
        """Initialize the local NLU provider."""
        self._model: Any = None
        self._model_path: str = ""
        self._n_ctx: int = 2048
        self._n_threads: int = 4
        self._initialized = False

    def initialize(self, config: dict[str, Any]) -> None:
        """Initialize the NLU provider with configuration.

        Args:
            config: Configuration dictionary with keys:
                - model_path: Path to GGUF model file (required)
                - n_ctx: Context size (default: 2048)
                - n_threads: Number of CPU threads (default: 4)
                - n_gpu_layers: GPU layers to offload (default: 0)

        Raises:
            ImportError: If llama-cpp-python is not installed.
            ValueError: If model_path is not provided.
            RuntimeError: If model loading fails.
        """
        if not LLAMA_CPP_AVAILABLE:
            raise ImportError(
                "llama-cpp-python is required for local NLU. "
                "Install with: uv add llama-cpp-python"
            )

        self._model_path = config.get("model_path", "")
        if not self._model_path:
            raise ValueError("model_path is required for LocalNLUProvider")

        self._n_ctx = config.get("n_ctx", 2048)
        self._n_threads = config.get("n_threads", 4)
        n_gpu_layers = config.get("n_gpu_layers", 0)

        logger.info(f"Loading Llama model from '{self._model_path}'...")

        try:
            self._model = Llama(
                model_path=self._model_path,
                n_ctx=self._n_ctx,
                n_threads=self._n_threads,
                n_gpu_layers=n_gpu_layers,
                verbose=False,
            )
            self._initialized = True
            logger.info("Llama model loaded successfully")

        except Exception as e:
            logger.error(f"Failed to load Llama model: {e}")
            raise RuntimeError(f"Failed to load Llama model: {e}") from e

    def extract_intent(
        self, text: str, context: dict[str, Any] | None = None
    ) -> ATCIntent:
        """Extract structured intent from transcribed text.

        Args:
            text: Transcribed pilot speech.
            context: Optional flight context (not currently used).

        Returns:
            ATCIntent with extracted slots and confidence.
        """
        if not self._initialized or not self._model:
            logger.error("NLU provider not initialized")
            return ATCIntent(raw_text=text)

        if not text or not text.strip():
            logger.warning("Empty text provided to NLU")
            return ATCIntent(raw_text=text)

        try:
            # Build the prompt
            user_prompt = USER_PROMPT_TEMPLATE.format(text=text.strip())

            # Generate response
            response = self._model.create_chat_completion(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=256,
                temperature=0.1,  # Low temperature for consistent output
                stop=["```", "\n\n"],
            )

            # Extract the generated text
            generated = response["choices"][0]["message"]["content"].strip()
            logger.debug(f"NLU raw response: {generated}")

            # Parse JSON from response
            intent = self._parse_json_response(generated, text)
            return intent

        except Exception as e:
            logger.error(f"Intent extraction failed: {e}")
            return ATCIntent(raw_text=text)

    def _parse_json_response(self, response: str, original_text: str) -> ATCIntent:
        """Parse JSON response from the model.

        Args:
            response: Raw model output.
            original_text: Original transcribed text.

        Returns:
            Parsed ATCIntent.
        """
        # Try to extract JSON from the response
        json_match = re.search(r"\{[^}]+\}", response, re.DOTALL)
        if not json_match:
            logger.warning(f"No JSON found in NLU response: {response}")
            return ATCIntent(raw_text=original_text)

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in NLU response: {e}")
            return ATCIntent(raw_text=original_text)

        # Map intent string to enum
        intent_str = data.get("intent", "unknown")
        try:
            intent_type = ATCIntentType(intent_str)
        except ValueError:
            logger.warning(f"Unknown intent type: {intent_str}")
            intent_type = ATCIntentType.UNKNOWN

        return ATCIntent(
            intent_type=intent_type,
            confidence=float(data.get("confidence", 0.0)),
            callsign=data.get("callsign"),
            runway=data.get("runway"),
            taxiway=data.get("taxiway"),
            altitude=self._parse_int(data.get("altitude")),
            heading=self._parse_int(data.get("heading")),
            frequency=data.get("frequency"),
            position=data.get("position"),
            destination=data.get("destination"),
            raw_text=original_text,
        )

    @staticmethod
    def _parse_int(value: Any) -> int | None:
        """Safely parse an integer value.

        Args:
            value: Value to parse.

        Returns:
            Integer or None.
        """
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def is_available(self) -> bool:
        """Check if the provider is ready for use.

        Returns:
            True if the model is loaded and ready.
        """
        return self._initialized and self._model is not None

    def shutdown(self) -> None:
        """Release provider resources."""
        if self._model is not None:
            # llama-cpp models are garbage collected
            self._model = None
            self._initialized = False
            logger.info("Local NLU provider shutdown")

    @property
    def name(self) -> str:
        """Get provider name."""
        model_name = self._model_path.split("/")[-1] if self._model_path else "unknown"
        return f"LocalNLU(llama-cpp/{model_name})"

    @staticmethod
    def is_library_available() -> bool:
        """Check if llama-cpp-python library is installed.

        Returns:
            True if llama-cpp-python is available.
        """
        return LLAMA_CPP_AVAILABLE
