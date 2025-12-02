"""Intent processor for ATC V2 voice commands.

This module maps NLU-extracted intents to ATC requests and generates
appropriate responses using the existing ATCHandler system.

The processor acts as a bridge between the NLU output (ATCIntent)
and the existing ATC communication system (ATCHandler).

Typical usage:
    processor = IntentProcessor(atc_handler)
    response = processor.process_intent(intent, flight_context)
"""

import logging
from dataclasses import dataclass
from typing import Any

from airborne.services.atc.atc_handler import ATCHandler, ATCRequest, ATCRequestType, ATCResponse
from airborne.services.atc.providers.base import ATCIntent, ATCIntentType

logger = logging.getLogger(__name__)


@dataclass
class FlightContext:
    """Current flight context for intent processing.

    Provides state information to help the processor make
    appropriate decisions about how to handle intents.

    Attributes:
        callsign: Aircraft callsign.
        airport_icao: Current/nearest airport ICAO.
        on_ground: Whether aircraft is on the ground.
        current_frequency: Currently tuned frequency.
        assigned_runway: Currently assigned runway.
        assigned_taxiway: Currently assigned taxiway route.
        flight_phase: Current phase of flight.
    """

    callsign: str = ""
    airport_icao: str = ""
    on_ground: bool = True
    current_frequency: float = 0.0
    assigned_runway: str = ""
    assigned_taxiway: str = ""
    flight_phase: str = ""


# Mapping from NLU intent types to ATC request types
INTENT_TO_REQUEST_MAP: dict[ATCIntentType, ATCRequestType | None] = {
    # Ground operations
    ATCIntentType.REQUEST_TAXI: ATCRequestType.REQUEST_TAXI,
    ATCIntentType.REQUEST_PUSHBACK: ATCRequestType.REQUEST_PUSHBACK,
    ATCIntentType.REPORT_READY_FOR_TAXI: ATCRequestType.REQUEST_STARTUP,
    ATCIntentType.REQUEST_TAXI_TO_RUNWAY: ATCRequestType.REQUEST_TAXI,
    ATCIntentType.REQUEST_TAXI_TO_PARKING: ATCRequestType.REQUEST_PARKING,

    # Tower operations
    ATCIntentType.READY_FOR_DEPARTURE: ATCRequestType.READY_DEPARTURE,
    ATCIntentType.REQUEST_TAKEOFF: ATCRequestType.REQUEST_TAKEOFF,
    ATCIntentType.REQUEST_LANDING: ATCRequestType.REQUEST_LANDING,
    ATCIntentType.REPORT_DOWNWIND: ATCRequestType.REPORT_POSITION,
    ATCIntentType.REPORT_BASE: ATCRequestType.REPORT_POSITION,
    ATCIntentType.REPORT_FINAL: ATCRequestType.REPORT_FINAL,
    ATCIntentType.REPORT_SHORT_FINAL: ATCRequestType.REPORT_FINAL,
    ATCIntentType.REQUEST_GO_AROUND: ATCRequestType.GO_AROUND,
    ATCIntentType.REQUEST_TOUCH_AND_GO: ATCRequestType.REQUEST_LANDING,
    ATCIntentType.REPORT_CLEAR_OF_RUNWAY: ATCRequestType.REPORT_CLEAR,

    # Departure operations
    ATCIntentType.REQUEST_DEPARTURE_FREQUENCY: ATCRequestType.CHECKIN_DEPARTURE,
    ATCIntentType.REPORT_AIRBORNE: ATCRequestType.CHECKIN_DEPARTURE,
    ATCIntentType.REQUEST_FLIGHT_FOLLOWING: ATCRequestType.REQUEST_FLIGHT_FOLLOWING,

    # Approach operations
    ATCIntentType.REQUEST_APPROACH: ATCRequestType.REQUEST_APPROACH,
    ATCIntentType.REQUEST_ILS_APPROACH: ATCRequestType.REQUEST_APPROACH,
    ATCIntentType.REQUEST_VISUAL_APPROACH: ATCRequestType.REQUEST_APPROACH,
    ATCIntentType.REPORT_FIELD_IN_SIGHT: ATCRequestType.REPORT_POSITION,

    # Center/en-route operations
    ATCIntentType.REQUEST_ALTITUDE_CHANGE: ATCRequestType.REPORT_ALTITUDE,
    ATCIntentType.REQUEST_DIRECT: ATCRequestType.REPORT_POSITION,
    ATCIntentType.REPORT_POSITION: ATCRequestType.REPORT_POSITION,

    # Acknowledgements (no request needed)
    ATCIntentType.READBACK: None,
    ATCIntentType.ROGER: None,
    ATCIntentType.WILCO: None,
    ATCIntentType.NEGATIVE: None,
    ATCIntentType.SAY_AGAIN: None,
    ATCIntentType.STANDBY: None,

    # Unknown
    ATCIntentType.UNKNOWN: None,
}


class IntentProcessor:
    """Processes NLU intents and generates ATC responses.

    This class bridges the gap between the NLU system (which produces
    ATCIntent objects) and the ATC communication system (which uses
    ATCRequest/ATCResponse).
    """

    def __init__(self, atc_handler: ATCHandler | None = None) -> None:
        """Initialize the intent processor.

        Args:
            atc_handler: ATCHandler instance for generating responses.
        """
        self._atc_handler = atc_handler
        self._last_atc_instruction: str = ""

    def set_atc_handler(self, handler: ATCHandler) -> None:
        """Set the ATC handler.

        Args:
            handler: ATCHandler instance.
        """
        self._atc_handler = handler

    def process_intent(
        self,
        intent: ATCIntent,
        context: FlightContext | None = None,
    ) -> ATCResponse | None:
        """Process an NLU intent and generate an ATC response.

        Args:
            intent: Extracted intent from NLU.
            context: Current flight context.

        Returns:
            ATCResponse if a response should be generated, None otherwise.
        """
        if context is None:
            context = FlightContext()

        logger.info(
            f"Processing intent: {intent.intent_type.value} "
            f"(confidence={intent.confidence:.2f})"
        )

        # Handle low confidence or unknown intents
        if not intent.is_valid():
            return self._generate_say_again_response(context)

        # Handle acknowledgements (no ATC response needed)
        if intent.intent_type in (
            ATCIntentType.READBACK,
            ATCIntentType.ROGER,
            ATCIntentType.WILCO,
        ):
            return self._handle_acknowledgement(intent, context)

        # Handle "say again" request
        if intent.intent_type == ATCIntentType.SAY_AGAIN:
            return self._handle_say_again_request(context)

        # Handle "negative" / unable
        if intent.intent_type == ATCIntentType.NEGATIVE:
            return self._handle_negative(intent, context)

        # Map intent to ATC request type
        request_type = INTENT_TO_REQUEST_MAP.get(intent.intent_type)
        if request_type is None:
            logger.warning(f"No request mapping for intent: {intent.intent_type}")
            return self._generate_say_again_response(context)

        # Build ATC request
        request = self._build_request(intent, context, request_type)

        # Generate response via ATCHandler
        if self._atc_handler is None:
            logger.error("No ATC handler configured")
            return None

        response = self._atc_handler.handle_request(request)

        # Store for "say again" functionality
        if response.text:
            self._last_atc_instruction = response.text

        logger.info(f"ATC Response: {response.text}")
        return response

    def _build_request(
        self,
        intent: ATCIntent,
        context: FlightContext,
        request_type: ATCRequestType,
    ) -> ATCRequest:
        """Build an ATCRequest from intent and context.

        Args:
            intent: NLU intent.
            context: Flight context.
            request_type: Mapped request type.

        Returns:
            ATCRequest ready for the handler.
        """
        # Use callsign from intent if provided, else from context
        callsign = intent.callsign or context.callsign

        # Use runway from intent if provided, else from context
        runway = intent.runway or context.assigned_runway

        # Build additional data
        data: dict[str, Any] = {}
        if intent.altitude:
            data["altitude"] = intent.altitude
        if intent.heading:
            data["heading"] = intent.heading
        if intent.position:
            data["position"] = intent.position
        if intent.frequency:
            data["frequency"] = intent.frequency
        if intent.destination:
            data["destination"] = intent.destination
        if intent.taxiway:
            data["taxiway"] = intent.taxiway

        return ATCRequest(
            request_type=request_type,
            callsign=callsign,
            airport_icao=context.airport_icao,
            runway=runway,
            data=data,
        )

    def _generate_say_again_response(self, context: FlightContext) -> ATCResponse:
        """Generate a 'say again' response for unrecognized input.

        Args:
            context: Flight context.

        Returns:
            ATCResponse asking pilot to repeat.
        """
        callsign = context.callsign or "Aircraft"

        # Abbreviated callsign for response
        if callsign.startswith("N") and len(callsign) >= 5:
            short_callsign = callsign[-3:]
        else:
            short_callsign = callsign

        return ATCResponse(
            request_type=ATCRequestType.REQUEST_ATIS,  # Placeholder
            approved=False,
            callsign=callsign,
            text=f"{short_callsign}, say again",
            words=[short_callsign, "SAY_AGAIN"],
        )

    def _handle_acknowledgement(
        self, intent: ATCIntent, context: FlightContext
    ) -> ATCResponse | None:
        """Handle pilot acknowledgement (roger, wilco, readback).

        Args:
            intent: Acknowledgement intent.
            context: Flight context.

        Returns:
            None - no ATC response needed for acknowledgements.
        """
        logger.debug(f"Pilot acknowledgement: {intent.intent_type.value}")
        # Acknowledgements don't require ATC response
        # Could validate readback here in future
        return None

    def _handle_say_again_request(self, context: FlightContext) -> ATCResponse:
        """Handle pilot's 'say again' request.

        Args:
            context: Flight context.

        Returns:
            ATCResponse repeating the last instruction.
        """
        callsign = context.callsign or "Aircraft"

        if self._last_atc_instruction:
            # Repeat the last instruction
            return ATCResponse(
                request_type=ATCRequestType.REQUEST_ATIS,
                approved=True,
                callsign=callsign,
                text=f"I say again, {self._last_atc_instruction}",
                words=["I_SAY_AGAIN"] + self._last_atc_instruction.split(),
            )
        else:
            return ATCResponse(
                request_type=ATCRequestType.REQUEST_ATIS,
                approved=True,
                callsign=callsign,
                text=f"{callsign}, no previous instruction",
                words=[callsign, "NO_PREVIOUS_INSTRUCTION"],
            )

    def _handle_negative(
        self, intent: ATCIntent, context: FlightContext
    ) -> ATCResponse:
        """Handle pilot's 'negative' / unable response.

        Args:
            intent: Negative intent.
            context: Flight context.

        Returns:
            ATCResponse acknowledging the negative.
        """
        callsign = context.callsign or "Aircraft"

        # Abbreviated callsign
        if callsign.startswith("N") and len(callsign) >= 5:
            short_callsign = callsign[-3:]
        else:
            short_callsign = callsign

        return ATCResponse(
            request_type=ATCRequestType.REQUEST_ATIS,
            approved=True,
            callsign=callsign,
            text=f"{short_callsign}, roger, standby",
            words=[short_callsign, "ROGER", "STANDBY"],
        )

    def get_last_instruction(self) -> str:
        """Get the last ATC instruction for 'say again' functionality.

        Returns:
            Last instruction text, or empty string.
        """
        return self._last_atc_instruction
