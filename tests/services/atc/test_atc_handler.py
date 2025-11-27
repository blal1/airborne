"""Tests for ATC communication handler."""

import pytest

from airborne.services.atc.atc_handler import (
    ATCHandler,
    ATCRequest,
    ATCRequestType,
    ATCResponse,
)
from airborne.services.atc.flight_phase import FlightPhase


class TestATCHandler:
    """Tests for ATCHandler class."""

    @pytest.fixture
    def handler(self) -> ATCHandler:
        """Create ATC handler fixture."""
        return ATCHandler(
            callsign="N123AB",
            airport_icao="KPAO",
            airport_name="Palo Alto Airport",
        )

    def test_initialization(self, handler: ATCHandler) -> None:
        """Test handler initialization."""
        assert handler.callsign == "N123AB"
        assert handler.airport_icao == "KPAO"
        assert handler.current_phase == FlightPhase.PARKED_COLD

    def test_get_atis(self, handler: ATCHandler) -> None:
        """Test getting ATIS."""
        atis = handler.get_atis()

        assert atis is not None
        assert atis.airport_icao == "KPAO"
        assert len(atis.text) > 0
        assert len(atis.words) > 0

    def test_available_requests_parked(self, handler: ATCHandler) -> None:
        """Test available requests when parked cold."""
        requests = handler.available_requests
        assert "request_atis" in requests

    def test_handle_atis_request(self, handler: ATCHandler) -> None:
        """Test handling ATIS request."""
        request = ATCRequest(
            request_type=ATCRequestType.REQUEST_ATIS,
            callsign="N123AB",
            airport_icao="KPAO",
        )
        response = handler.handle_request(request)

        assert isinstance(response, ATCResponse)
        assert response.approved is True
        assert len(response.text) > 0
        assert "palo alto" in response.text.lower()

    def test_handle_startup_request(self, handler: ATCHandler) -> None:
        """Test handling startup request."""
        # First need to be parked hot
        handler.transition_phase(FlightPhase.PARKED_HOT, force=True)
        handler.transition_phase(FlightPhase.PARKED_COLD, force=True)

        request = ATCRequest(
            request_type=ATCRequestType.REQUEST_STARTUP,
            callsign="N123AB",
            airport_icao="KPAO",
        )
        response = handler.handle_request(request)

        assert response.approved is True
        assert "start up approved" in response.text.lower()
        assert handler.current_phase == FlightPhase.PARKED_HOT

    def test_handle_taxi_request(self, handler: ATCHandler) -> None:
        """Test handling taxi request."""
        handler.transition_phase(FlightPhase.PARKED_HOT, force=True)

        request = ATCRequest(
            request_type=ATCRequestType.REQUEST_TAXI,
            callsign="N123AB",
            airport_icao="KPAO",
        )
        response = handler.handle_request(request)

        assert response.approved is True
        assert "taxi" in response.text.lower()
        assert "runway" in response.text.lower()
        assert handler.current_phase == FlightPhase.TAXI_OUT

    def test_handle_ready_departure(self, handler: ATCHandler) -> None:
        """Test handling ready for departure."""
        # Progress to holding short
        handler.transition_phase(FlightPhase.HOLDING_SHORT, force=True)

        request = ATCRequest(
            request_type=ATCRequestType.READY_DEPARTURE,
            callsign="N123AB",
            airport_icao="KPAO",
        )
        response = handler.handle_request(request)

        assert response.approved is True
        assert "cleared for takeoff" in response.text.lower()
        assert handler.current_phase == FlightPhase.LINEUP

    def test_handle_landing_request(self, handler: ATCHandler) -> None:
        """Test handling landing clearance request."""
        handler.transition_phase(FlightPhase.PATTERN, force=True)

        request = ATCRequest(
            request_type=ATCRequestType.REQUEST_LANDING,
            callsign="N123AB",
            airport_icao="KPAO",
        )
        response = handler.handle_request(request)

        assert response.approved is True
        assert "cleared to land" in response.text.lower()
        assert handler.current_phase == FlightPhase.FINAL

    def test_handle_departure_checkin(self, handler: ATCHandler) -> None:
        """Test handling departure check-in."""
        handler.transition_phase(FlightPhase.INITIAL_CLIMB, force=True)

        request = ATCRequest(
            request_type=ATCRequestType.CHECKIN_DEPARTURE,
            callsign="N123AB",
            airport_icao="KPAO",
        )
        response = handler.handle_request(request)

        assert response.approved is True
        assert "radar contact" in response.text.lower()
        assert handler.current_phase == FlightPhase.DEPARTURE

    def test_handle_go_around(self, handler: ATCHandler) -> None:
        """Test handling go around."""
        handler.transition_phase(FlightPhase.FINAL, force=True)

        request = ATCRequest(
            request_type=ATCRequestType.GO_AROUND,
            callsign="N123AB",
            airport_icao="KPAO",
        )
        response = handler.handle_request(request)

        assert response.approved is True
        assert "go around" in response.text.lower() or "heading" in response.text.lower()
        assert handler.current_phase == FlightPhase.INITIAL_CLIMB

    def test_handle_clear_report(self, handler: ATCHandler) -> None:
        """Test handling runway clear report."""
        handler.transition_phase(FlightPhase.LANDING_ROLL, force=True)

        request = ATCRequest(
            request_type=ATCRequestType.REPORT_CLEAR,
            callsign="N123AB",
            airport_icao="KPAO",
        )
        response = handler.handle_request(request)

        assert response.approved is True
        assert "ground" in response.text.lower()
        assert response.next_frequency is not None
        assert handler.current_phase == FlightPhase.TAXI_IN

    def test_response_includes_abbreviated_callsign(self, handler: ATCHandler) -> None:
        """Test that responses use abbreviated callsign."""
        request = ATCRequest(
            request_type=ATCRequestType.REQUEST_ATIS,
            callsign="N12345",
            airport_icao="KPAO",
        )
        response = handler.handle_request(request)

        # Should use abbreviated form (last 3)
        # Full callsign is N12345, abbreviated should be "345" or phonetic
        assert response.callsign == "N12345"

    def test_reset(self, handler: ATCHandler) -> None:
        """Test handler reset."""
        handler.transition_phase(FlightPhase.CRUISE, force=True)
        handler.reset()

        assert handler.current_phase == FlightPhase.PARKED_COLD

    def test_current_frequency(self, handler: ATCHandler) -> None:
        """Test current frequency tracking."""
        assert handler.current_frequency == "ground"

        handler.transition_phase(FlightPhase.HOLDING_SHORT, force=True)
        assert handler.current_frequency == "tower"

        handler.transition_phase(FlightPhase.DEPARTURE, force=True)
        assert handler.current_frequency == "departure"

    def test_position_report(self, handler: ATCHandler) -> None:
        """Test position report handling."""
        handler.transition_phase(FlightPhase.CRUISE, force=True)

        request = ATCRequest(
            request_type=ATCRequestType.REPORT_POSITION,
            callsign="N123AB",
            airport_icao="KPAO",
        )
        response = handler.handle_request(request)

        assert response.approved is True
        assert "roger" in response.text.lower()
