"""Flight phase state machine for ATC context awareness.

Tracks the current phase of flight to enable context-appropriate
ATC communications and requests.
"""

from collections.abc import Callable
from enum import Enum, auto


class FlightPhase(Enum):
    """Flight phases for ATC context.

    Each phase determines what ATC services and requests are available.
    """

    # Ground phases
    PARKED_COLD = auto()  # Engine off, parked at gate/ramp
    PARKED_HOT = auto()  # Engine running, parked
    PUSHBACK = auto()  # Being pushed back from gate
    TAXI_OUT = auto()  # Taxiing to runway
    HOLDING_SHORT = auto()  # Holding short of runway

    # Takeoff/departure phases
    LINEUP = auto()  # Lined up on runway, waiting
    TAKEOFF_ROLL = auto()  # Taking off
    INITIAL_CLIMB = auto()  # Climbing after takeoff (below pattern altitude)
    DEPARTURE = auto()  # Departing the airport area

    # Enroute phases
    CRUISE = auto()  # Level flight, enroute
    DESCENT = auto()  # Descending toward destination

    # Arrival/approach phases
    APPROACH = auto()  # On approach to airport
    PATTERN = auto()  # In traffic pattern
    BASE = auto()  # On base leg
    FINAL = auto()  # On final approach

    # Landing phases
    LANDING_ROLL = auto()  # On runway after touchdown
    TAXI_IN = auto()  # Taxiing to parking
    SHUTDOWN = auto()  # Engine shutdown


class FlightPhaseManager:
    """Manages flight phase transitions and provides context.

    Tracks the current flight phase and determines valid ATC requests
    based on that phase.
    """

    # Valid phase transitions
    VALID_TRANSITIONS: dict[FlightPhase, set[FlightPhase]] = {
        FlightPhase.PARKED_COLD: {FlightPhase.PARKED_HOT},
        FlightPhase.PARKED_HOT: {
            FlightPhase.PUSHBACK,
            FlightPhase.TAXI_OUT,
            FlightPhase.PARKED_COLD,
        },
        FlightPhase.PUSHBACK: {FlightPhase.PARKED_HOT, FlightPhase.TAXI_OUT},
        FlightPhase.TAXI_OUT: {FlightPhase.HOLDING_SHORT, FlightPhase.PARKED_HOT},
        FlightPhase.HOLDING_SHORT: {FlightPhase.LINEUP, FlightPhase.TAXI_OUT},
        FlightPhase.LINEUP: {FlightPhase.TAKEOFF_ROLL, FlightPhase.HOLDING_SHORT},
        FlightPhase.TAKEOFF_ROLL: {FlightPhase.INITIAL_CLIMB},
        FlightPhase.INITIAL_CLIMB: {FlightPhase.DEPARTURE, FlightPhase.PATTERN},
        FlightPhase.DEPARTURE: {FlightPhase.CRUISE, FlightPhase.PATTERN},
        FlightPhase.CRUISE: {FlightPhase.DESCENT, FlightPhase.CRUISE},
        FlightPhase.DESCENT: {FlightPhase.APPROACH, FlightPhase.CRUISE},
        FlightPhase.APPROACH: {FlightPhase.PATTERN, FlightPhase.FINAL},
        FlightPhase.PATTERN: {FlightPhase.BASE, FlightPhase.DEPARTURE},
        FlightPhase.BASE: {FlightPhase.FINAL, FlightPhase.PATTERN},
        FlightPhase.FINAL: {FlightPhase.LANDING_ROLL, FlightPhase.PATTERN},
        FlightPhase.LANDING_ROLL: {FlightPhase.TAXI_IN},
        FlightPhase.TAXI_IN: {FlightPhase.PARKED_HOT, FlightPhase.SHUTDOWN},
        FlightPhase.SHUTDOWN: {FlightPhase.PARKED_COLD},
    }

    # ATC requests available in each phase
    AVAILABLE_REQUESTS: dict[FlightPhase, list[str]] = {
        FlightPhase.PARKED_COLD: ["request_atis"],
        FlightPhase.PARKED_HOT: ["request_atis", "request_taxi", "request_pushback"],
        FlightPhase.PUSHBACK: ["report_ready"],
        FlightPhase.TAXI_OUT: ["request_atis", "report_position"],
        FlightPhase.HOLDING_SHORT: ["ready_departure", "request_atis"],
        FlightPhase.LINEUP: ["abort_takeoff"],
        FlightPhase.TAKEOFF_ROLL: ["abort_takeoff"],
        FlightPhase.INITIAL_CLIMB: ["checkin_departure"],
        FlightPhase.DEPARTURE: [
            "checkin_departure",
            "request_flight_following",
            "report_altitude",
        ],
        FlightPhase.CRUISE: [
            "request_flight_following",
            "report_position",
            "report_altitude",
            "request_descent",
        ],
        FlightPhase.DESCENT: [
            "request_approach",
            "report_altitude",
            "report_position",
        ],
        FlightPhase.APPROACH: [
            "request_landing",
            "report_position",
            "request_pattern_entry",
        ],
        FlightPhase.PATTERN: [
            "report_position",
            "request_landing",
            "report_downwind",
            "report_base",
        ],
        FlightPhase.BASE: ["report_base", "request_landing"],
        FlightPhase.FINAL: ["report_final", "go_around"],
        FlightPhase.LANDING_ROLL: ["report_clear", "request_taxi"],
        FlightPhase.TAXI_IN: ["request_parking"],
        FlightPhase.SHUTDOWN: [],
    }

    # Current ATC frequency based on phase
    PHASE_FREQUENCIES: dict[FlightPhase, str] = {
        FlightPhase.PARKED_COLD: "ground",
        FlightPhase.PARKED_HOT: "ground",
        FlightPhase.PUSHBACK: "ground",
        FlightPhase.TAXI_OUT: "ground",
        FlightPhase.HOLDING_SHORT: "tower",
        FlightPhase.LINEUP: "tower",
        FlightPhase.TAKEOFF_ROLL: "tower",
        FlightPhase.INITIAL_CLIMB: "tower",
        FlightPhase.DEPARTURE: "departure",
        FlightPhase.CRUISE: "center",
        FlightPhase.DESCENT: "approach",
        FlightPhase.APPROACH: "approach",
        FlightPhase.PATTERN: "tower",
        FlightPhase.BASE: "tower",
        FlightPhase.FINAL: "tower",
        FlightPhase.LANDING_ROLL: "tower",
        FlightPhase.TAXI_IN: "ground",
        FlightPhase.SHUTDOWN: "ground",
    }

    def __init__(self, initial_phase: FlightPhase = FlightPhase.PARKED_COLD) -> None:
        """Initialize flight phase manager.

        Args:
            initial_phase: Starting flight phase.
        """
        self._current_phase = initial_phase
        self._phase_history: list[FlightPhase] = [initial_phase]
        self._listeners: list[Callable[[FlightPhase, FlightPhase], None]] = []

    @property
    def current_phase(self) -> FlightPhase:
        """Get the current flight phase."""
        return self._current_phase

    @property
    def current_frequency(self) -> str:
        """Get the expected ATC frequency for current phase."""
        return self.PHASE_FREQUENCIES.get(self._current_phase, "ground")

    @property
    def available_requests(self) -> list[str]:
        """Get list of available ATC requests for current phase."""
        return self.AVAILABLE_REQUESTS.get(self._current_phase, [])

    def can_transition_to(self, new_phase: FlightPhase) -> bool:
        """Check if transition to new phase is valid.

        Args:
            new_phase: Phase to transition to.

        Returns:
            True if transition is valid.
        """
        valid_next = self.VALID_TRANSITIONS.get(self._current_phase, set())
        return new_phase in valid_next

    def transition_to(self, new_phase: FlightPhase, force: bool = False) -> bool:
        """Transition to a new flight phase.

        Args:
            new_phase: Phase to transition to.
            force: If True, allow invalid transitions.

        Returns:
            True if transition was successful.
        """
        if not force and not self.can_transition_to(new_phase):
            return False

        old_phase = self._current_phase
        self._current_phase = new_phase
        self._phase_history.append(new_phase)

        # Notify listeners
        for listener in self._listeners:
            listener(old_phase, new_phase)

        return True

    def add_transition_listener(self, listener: Callable[[FlightPhase, FlightPhase], None]) -> None:
        """Add a listener for phase transitions.

        Args:
            listener: Callback function(old_phase, new_phase).
        """
        self._listeners.append(listener)

    def remove_transition_listener(
        self, listener: Callable[[FlightPhase, FlightPhase], None]
    ) -> None:
        """Remove a transition listener.

        Args:
            listener: Callback to remove.
        """
        if listener in self._listeners:
            self._listeners.remove(listener)

    def is_on_ground(self) -> bool:
        """Check if aircraft is on the ground."""
        ground_phases = {
            FlightPhase.PARKED_COLD,
            FlightPhase.PARKED_HOT,
            FlightPhase.PUSHBACK,
            FlightPhase.TAXI_OUT,
            FlightPhase.HOLDING_SHORT,
            FlightPhase.LINEUP,
            FlightPhase.TAKEOFF_ROLL,
            FlightPhase.LANDING_ROLL,
            FlightPhase.TAXI_IN,
            FlightPhase.SHUTDOWN,
        }
        return self._current_phase in ground_phases

    def is_airborne(self) -> bool:
        """Check if aircraft is in the air."""
        return not self.is_on_ground()

    def is_departing(self) -> bool:
        """Check if aircraft is in departure phase."""
        departure_phases = {
            FlightPhase.TAKEOFF_ROLL,
            FlightPhase.INITIAL_CLIMB,
            FlightPhase.DEPARTURE,
        }
        return self._current_phase in departure_phases

    def is_arriving(self) -> bool:
        """Check if aircraft is in arrival phase."""
        arrival_phases = {
            FlightPhase.DESCENT,
            FlightPhase.APPROACH,
            FlightPhase.PATTERN,
            FlightPhase.BASE,
            FlightPhase.FINAL,
            FlightPhase.LANDING_ROLL,
        }
        return self._current_phase in arrival_phases

    def can_request_landing(self) -> bool:
        """Check if landing clearance can be requested."""
        return "request_landing" in self.available_requests

    def can_request_takeoff(self) -> bool:
        """Check if takeoff clearance can be requested."""
        return "ready_departure" in self.available_requests

    def get_phase_history(self) -> list[FlightPhase]:
        """Get the history of flight phases."""
        return self._phase_history.copy()

    def reset(self, initial_phase: FlightPhase = FlightPhase.PARKED_COLD) -> None:
        """Reset to initial state.

        Args:
            initial_phase: Phase to reset to.
        """
        self._current_phase = initial_phase
        self._phase_history = [initial_phase]
