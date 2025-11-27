"""Tests for flight phase state machine."""

import pytest

from airborne.services.atc.flight_phase import FlightPhase, FlightPhaseManager


class TestFlightPhase:
    """Tests for FlightPhase enum."""

    def test_all_phases_exist(self) -> None:
        """Test that all expected phases exist."""
        assert FlightPhase.PARKED_COLD
        assert FlightPhase.PARKED_HOT
        assert FlightPhase.TAXI_OUT
        assert FlightPhase.TAKEOFF_ROLL
        assert FlightPhase.CRUISE
        assert FlightPhase.LANDING_ROLL


class TestFlightPhaseManager:
    """Tests for FlightPhaseManager class."""

    @pytest.fixture
    def manager(self) -> FlightPhaseManager:
        """Create flight phase manager fixture."""
        return FlightPhaseManager()

    def test_initial_phase(self, manager: FlightPhaseManager) -> None:
        """Test initial phase is parked cold."""
        assert manager.current_phase == FlightPhase.PARKED_COLD

    def test_custom_initial_phase(self) -> None:
        """Test custom initial phase."""
        manager = FlightPhaseManager(initial_phase=FlightPhase.CRUISE)
        assert manager.current_phase == FlightPhase.CRUISE

    def test_valid_transition(self, manager: FlightPhaseManager) -> None:
        """Test valid phase transition."""
        assert manager.can_transition_to(FlightPhase.PARKED_HOT)
        result = manager.transition_to(FlightPhase.PARKED_HOT)
        assert result is True
        assert manager.current_phase == FlightPhase.PARKED_HOT

    def test_invalid_transition(self, manager: FlightPhaseManager) -> None:
        """Test invalid phase transition is blocked."""
        # Can't go directly from PARKED_COLD to CRUISE
        assert not manager.can_transition_to(FlightPhase.CRUISE)
        result = manager.transition_to(FlightPhase.CRUISE)
        assert result is False
        assert manager.current_phase == FlightPhase.PARKED_COLD

    def test_forced_transition(self, manager: FlightPhaseManager) -> None:
        """Test forced invalid transition."""
        result = manager.transition_to(FlightPhase.CRUISE, force=True)
        assert result is True
        assert manager.current_phase == FlightPhase.CRUISE

    def test_transition_listener(self, manager: FlightPhaseManager) -> None:
        """Test transition listener callback."""
        transitions = []

        def listener(old_phase: FlightPhase, new_phase: FlightPhase) -> None:
            transitions.append((old_phase, new_phase))

        manager.add_transition_listener(listener)
        manager.transition_to(FlightPhase.PARKED_HOT)

        assert len(transitions) == 1
        assert transitions[0] == (FlightPhase.PARKED_COLD, FlightPhase.PARKED_HOT)

    def test_remove_transition_listener(self, manager: FlightPhaseManager) -> None:
        """Test removing transition listener."""
        transitions = []

        def listener(old_phase: FlightPhase, new_phase: FlightPhase) -> None:
            transitions.append((old_phase, new_phase))

        manager.add_transition_listener(listener)
        manager.remove_transition_listener(listener)
        manager.transition_to(FlightPhase.PARKED_HOT)

        assert len(transitions) == 0

    def test_is_on_ground(self, manager: FlightPhaseManager) -> None:
        """Test is_on_ground detection."""
        assert manager.is_on_ground() is True

        manager.transition_to(FlightPhase.PARKED_HOT)
        assert manager.is_on_ground() is True

    def test_is_airborne(self) -> None:
        """Test is_airborne detection."""
        manager = FlightPhaseManager(initial_phase=FlightPhase.CRUISE)
        assert manager.is_airborne() is True
        assert manager.is_on_ground() is False

    def test_is_departing(self) -> None:
        """Test is_departing detection."""
        manager = FlightPhaseManager(initial_phase=FlightPhase.DEPARTURE)
        assert manager.is_departing() is True

        manager = FlightPhaseManager(initial_phase=FlightPhase.CRUISE)
        assert manager.is_departing() is False

    def test_is_arriving(self) -> None:
        """Test is_arriving detection."""
        manager = FlightPhaseManager(initial_phase=FlightPhase.APPROACH)
        assert manager.is_arriving() is True

        manager = FlightPhaseManager(initial_phase=FlightPhase.CRUISE)
        assert manager.is_arriving() is False

    def test_available_requests(self, manager: FlightPhaseManager) -> None:
        """Test available requests for phase."""
        requests = manager.available_requests
        assert "request_atis" in requests

        manager.transition_to(FlightPhase.PARKED_HOT)
        requests = manager.available_requests
        assert "request_taxi" in requests

    def test_current_frequency(self, manager: FlightPhaseManager) -> None:
        """Test current frequency for phase."""
        assert manager.current_frequency == "ground"

        # Simulate getting to holding short
        manager.transition_to(FlightPhase.PARKED_HOT)
        manager.transition_to(FlightPhase.TAXI_OUT)
        manager.transition_to(FlightPhase.HOLDING_SHORT)
        assert manager.current_frequency == "tower"

    def test_can_request_landing(self) -> None:
        """Test can_request_landing."""
        manager = FlightPhaseManager(initial_phase=FlightPhase.PATTERN)
        assert manager.can_request_landing() is True

        manager = FlightPhaseManager(initial_phase=FlightPhase.PARKED_COLD)
        assert manager.can_request_landing() is False

    def test_can_request_takeoff(self) -> None:
        """Test can_request_takeoff."""
        manager = FlightPhaseManager(initial_phase=FlightPhase.HOLDING_SHORT)
        assert manager.can_request_takeoff() is True

        manager = FlightPhaseManager(initial_phase=FlightPhase.CRUISE)
        assert manager.can_request_takeoff() is False

    def test_phase_history(self, manager: FlightPhaseManager) -> None:
        """Test phase history tracking."""
        manager.transition_to(FlightPhase.PARKED_HOT)
        manager.transition_to(FlightPhase.TAXI_OUT)

        history = manager.get_phase_history()
        assert len(history) == 3
        assert history[0] == FlightPhase.PARKED_COLD
        assert history[1] == FlightPhase.PARKED_HOT
        assert history[2] == FlightPhase.TAXI_OUT

    def test_reset(self, manager: FlightPhaseManager) -> None:
        """Test reset to initial state."""
        manager.transition_to(FlightPhase.PARKED_HOT)
        manager.transition_to(FlightPhase.TAXI_OUT)

        manager.reset()
        assert manager.current_phase == FlightPhase.PARKED_COLD
        assert len(manager.get_phase_history()) == 1

    def test_reset_custom_phase(self, manager: FlightPhaseManager) -> None:
        """Test reset to custom phase."""
        manager.transition_to(FlightPhase.PARKED_HOT)
        manager.reset(initial_phase=FlightPhase.CRUISE)

        assert manager.current_phase == FlightPhase.CRUISE
