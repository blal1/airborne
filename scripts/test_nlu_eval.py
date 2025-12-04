#!/usr/bin/env python3
"""Comprehensive NLU evaluation script.

Tests the NLU system with a wide variety of pilot prompts covering:
- All intent types (VFR, IFR, ground, tower, approach, etc.)
- English and French phraseology
- Hesitations, partial phrases, realistic speech patterns
- Edge cases and ambiguous inputs

Produces a detailed efficiency report.

Usage:
    uv run python scripts/test_nlu_eval.py [--model MODEL]
"""

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from airborne.services.atc.providers.local_nlu import LocalNLUProvider
from airborne.services.download_manager import DEFAULT_NLU_MODEL, get_nlu_model_path


@dataclass
class TestCase:
    """A single test case for NLU evaluation."""

    input_text: str
    expected_intent: str
    language: str
    category: str
    description: str
    # Optional expected slot values
    expected_callsign: str | None = None
    expected_runway: str | None = None
    expected_taxiway: str | None = None
    expected_altitude: int | None = None
    expected_heading: int | None = None
    expected_frequency: str | None = None
    expected_hold_short: str | None = None


@dataclass
class TestResult:
    """Result of a single test case."""

    test_case: TestCase
    actual_intent: str
    confidence: float
    intent_correct: bool
    slots_correct: bool
    elapsed_ms: float
    extracted_slots: dict


# Comprehensive test cases covering all scenarios
TEST_CASES = [
    # ========== INITIAL CONTACT / GROUND - ENGLISH ==========
    TestCase(
        "November 123AB, ground, good morning",
        "initial_contact",
        "en",
        "ground",
        "Initial contact English",
    ),
    TestCase("Speedbird 442, ground", "initial_contact", "en", "ground", "Airline initial contact"),
    TestCase(
        "uh... November 456, ground, hello",
        "initial_contact",
        "en",
        "ground",
        "Hesitant initial contact",
    ),
    # ========== INITIAL CONTACT / GROUND - FRENCH ==========
    TestCase(
        "Air France 1418, sol, bonjour",
        "initial_contact",
        "fr",
        "ground",
        "Initial contact French",
        expected_callsign="AF1418",
    ),
    TestCase(
        "Fox Golf X-ray Yankee Zulu, sol bonjour",
        "initial_contact",
        "fr",
        "ground",
        "French callsign spelled",
    ),
    TestCase(
        "euh... AF256, controle sol, bonjour",
        "initial_contact",
        "fr",
        "ground",
        "Hesitant French contact",
    ),
    TestCase(
        "SK202, sol",
        "initial_contact",
        "fr",
        "ground",
        "Short French contact",
        expected_callsign="SK202",
    ),
    # ========== TAXI REQUESTS - ENGLISH ==========
    TestCase(
        "N123AB, request taxi",
        "request_taxi",
        "en",
        "ground",
        "Simple taxi request",
        expected_callsign="N123AB",
    ),
    TestCase(
        "November 456, ready to taxi", "request_taxi", "en", "ground", "Ready to taxi variation"
    ),
    TestCase(
        "Cessna 789, request taxi to runway 27",
        "request_taxi",
        "en",
        "ground",
        "Taxi with runway",
        expected_runway="27",
    ),
    TestCase(
        "uh N123, we're ready for taxi when... when you're ready",
        "request_taxi",
        "en",
        "ground",
        "Hesitant taxi request",
    ),
    # ========== TAXI REQUESTS - FRENCH ==========
    TestCase(
        "F-GXYZ, demande roulage",
        "request_taxi",
        "fr",
        "ground",
        "French taxi request",
        expected_callsign="F-GXYZ",
    ),
    TestCase("AF1418, on demande le roulage", "request_taxi", "fr", "ground", "French taxi formal"),
    TestCase(
        "euh... F-ABCD, demande roulage piste 27",
        "request_taxi",
        "fr",
        "ground",
        "Hesitant French taxi",
        expected_runway="27",
    ),
    # ========== PUSHBACK - ENGLISH ==========
    TestCase("Delta 456, request pushback", "request_pushback", "en", "ground", "Pushback request"),
    TestCase("United 789, ready for push", "request_pushback", "en", "ground", "Short pushback"),
    # ========== PUSHBACK - FRENCH ==========
    TestCase("AF256, demande refoulement", "request_pushback", "fr", "ground", "French pushback"),
    TestCase(
        "F-GXYZ, on demande le push-back",
        "request_pushback",
        "fr",
        "ground",
        "French pushback mixed",
    ),
    # ========== HOLDING SHORT - ENGLISH ==========
    TestCase(
        "N123AB holding short runway 27",
        "report_holding_short",
        "en",
        "ground",
        "Holding short",
        expected_runway="27",
    ),
    TestCase(
        "Cessna 456 holding short 09 left",
        "report_holding_short",
        "en",
        "ground",
        "Holding short left runway",
        expected_runway="09L",
    ),
    # ========== HOLDING SHORT - FRENCH ==========
    TestCase(
        "F-ABCD, maintien avant piste 27",
        "report_holding_short",
        "fr",
        "ground",
        "French holding short",
        expected_runway="27",
    ),
    TestCase(
        "AF1418, on maintient avant la piste",
        "report_holding_short",
        "fr",
        "ground",
        "French holding short informal",
    ),
    # ========== READY FOR DEPARTURE - ENGLISH ==========
    TestCase(
        "N123AB ready for departure runway 27",
        "ready_for_departure",
        "en",
        "tower",
        "Ready departure",
        expected_runway="27",
    ),
    TestCase(
        "Cessna 456 ready to go", "ready_for_departure", "en", "tower", "Ready to go informal"
    ),
    TestCase(
        "November 789, we're number one, ready",
        "ready_for_departure",
        "en",
        "tower",
        "Ready number one",
    ),
    TestCase(
        "uh... N123, ready when you are", "ready_for_departure", "en", "tower", "Hesitant ready"
    ),
    # ========== READY FOR DEPARTURE - FRENCH ==========
    TestCase(
        "F-GXYZ, prêt au départ piste 09",
        "ready_for_departure",
        "fr",
        "tower",
        "French ready departure",
        expected_runway="09",
    ),
    TestCase(
        "AF1418, prêt au décollage", "ready_for_departure", "fr", "tower", "French ready takeoff"
    ),
    TestCase(
        "euh... F-ABCD, on est prêt", "ready_for_departure", "fr", "tower", "Hesitant French ready"
    ),
    # ========== TAKEOFF REQUEST - ENGLISH ==========
    TestCase("N123AB request takeoff", "request_takeoff", "en", "tower", "Takeoff request"),
    TestCase(
        "Cessna 456 requesting immediate departure",
        "request_immediate_takeoff",
        "en",
        "tower",
        "Immediate takeoff",
    ),
    # ========== TRAFFIC PATTERN - ENGLISH ==========
    TestCase(
        "N123AB crosswind runway 27",
        "report_crosswind",
        "en",
        "pattern",
        "Crosswind report",
        expected_runway="27",
    ),
    TestCase(
        "Cessna 456 downwind 27",
        "report_downwind",
        "en",
        "pattern",
        "Downwind report",
        expected_runway="27",
    ),
    TestCase("N789 left downwind runway 09", "report_downwind", "en", "pattern", "Left downwind"),
    TestCase(
        "November 123 midfield downwind",
        "report_midfield_downwind",
        "en",
        "pattern",
        "Midfield downwind",
    ),
    TestCase(
        "N456 base runway 27", "report_base", "en", "pattern", "Base report", expected_runway="27"
    ),
    TestCase("Cessna 789 turning base", "report_base", "en", "pattern", "Turning base"),
    TestCase(
        "N123AB final runway 27",
        "report_final",
        "en",
        "pattern",
        "Final report",
        expected_runway="27",
    ),
    TestCase("November 456, uh, final", "report_final", "en", "pattern", "Hesitant final"),
    TestCase(
        "N789 short final 27",
        "report_short_final",
        "en",
        "pattern",
        "Short final",
        expected_runway="27",
    ),
    # ========== TRAFFIC PATTERN - FRENCH ==========
    TestCase(
        "F-GXYZ vent traversier piste 27",
        "report_crosswind",
        "fr",
        "pattern",
        "French crosswind",
        expected_runway="27",
    ),
    TestCase(
        "F-ABCD vent arrière piste 09",
        "report_downwind",
        "fr",
        "pattern",
        "French downwind",
        expected_runway="09",
    ),
    TestCase(
        "AF1418, euh, vent arrière main gauche",
        "report_downwind",
        "fr",
        "pattern",
        "French left downwind",
    ),
    TestCase("F-GXYZ en base", "report_base", "fr", "pattern", "French base"),
    TestCase(
        "F-ABCD étape de base piste 27",
        "report_base",
        "fr",
        "pattern",
        "French base formal",
        expected_runway="27",
    ),
    TestCase(
        "AF1418 finale piste 09 gauche",
        "report_final",
        "fr",
        "pattern",
        "French final",
        expected_runway="09L",
    ),
    TestCase("F-GXYZ en finale", "report_final", "fr", "pattern", "French in final"),
    TestCase("F-ABCD courte finale", "report_short_final", "fr", "pattern", "French short final"),
    # ========== GO AROUND - ENGLISH ==========
    TestCase("N123AB going around", "request_go_around", "en", "tower", "Going around"),
    TestCase("Cessna 456 go around", "request_go_around", "en", "tower", "Go around"),
    TestCase(
        "November 789, uh, going around, traffic on runway",
        "request_go_around",
        "en",
        "tower",
        "Go around with reason",
    ),
    # ========== GO AROUND - FRENCH ==========
    TestCase("F-GXYZ remise de gaz", "request_go_around", "fr", "tower", "French go around"),
    TestCase(
        "AF1418, on remet les gaz", "request_go_around", "fr", "tower", "French go around informal"
    ),
    # ========== TOUCH AND GO - ENGLISH ==========
    TestCase(
        "N123AB request touch and go", "request_touch_and_go", "en", "tower", "Touch and go request"
    ),
    TestCase("Cessna 456 requesting the option", "request_option", "en", "tower", "Option request"),
    TestCase(
        "November 789 request closed traffic",
        "request_closed_traffic",
        "en",
        "pattern",
        "Closed traffic",
    ),
    # ========== TOUCH AND GO - FRENCH ==========
    TestCase(
        "F-GXYZ demande touch and go", "request_touch_and_go", "fr", "tower", "French touch and go"
    ),
    TestCase(
        "F-ABCD demande posé décollé", "request_touch_and_go", "fr", "tower", "French stop and go"
    ),
    TestCase(
        "AF1418, on reste dans le circuit",
        "request_closed_traffic",
        "fr",
        "pattern",
        "French closed traffic",
    ),
    # ========== LANDING - ENGLISH ==========
    TestCase(
        "N123AB request landing runway 27",
        "request_landing",
        "en",
        "tower",
        "Landing request",
        expected_runway="27",
    ),
    TestCase("Cessna 456 inbound for landing", "request_landing", "en", "tower", "Inbound landing"),
    TestCase("November 789 full stop", "request_landing", "en", "tower", "Full stop request"),
    # ========== LANDING - FRENCH ==========
    TestCase(
        "F-GXYZ demande atterrissage piste 09",
        "request_landing",
        "fr",
        "tower",
        "French landing",
        expected_runway="09",
    ),
    # ========== CLEAR OF RUNWAY - ENGLISH ==========
    TestCase(
        "N123AB clear of runway 27",
        "report_clear_of_runway",
        "en",
        "ground",
        "Clear runway",
        expected_runway="27",
    ),
    TestCase("Cessna 456 clear", "report_clear_of_runway", "en", "ground", "Clear short"),
    TestCase(
        "November 789, uh, we're off the runway",
        "report_clear_of_runway",
        "en",
        "ground",
        "Off runway",
    ),
    # ========== CLEAR OF RUNWAY - FRENCH ==========
    TestCase(
        "F-GXYZ piste dégagée", "report_clear_of_runway", "fr", "ground", "French clear runway"
    ),
    TestCase("AF1418, piste libre", "report_clear_of_runway", "fr", "ground", "French runway free"),
    # ========== IFR APPROACH REQUESTS - ENGLISH ==========
    TestCase(
        "N123AB request ILS runway 27 left",
        "request_ils_approach",
        "en",
        "approach",
        "ILS request",
        expected_runway="27L",
    ),
    TestCase(
        "Cessna 456 request visual approach",
        "request_visual_approach",
        "en",
        "approach",
        "Visual approach",
    ),
    TestCase(
        "November 789 request RNAV runway 09",
        "request_rnav_approach",
        "en",
        "approach",
        "RNAV request",
        expected_runway="09",
    ),
    TestCase(
        "Delta 123 request VOR approach", "request_vor_approach", "en", "approach", "VOR approach"
    ),
    TestCase(
        "United 456 request approach", "request_approach", "en", "approach", "Generic approach"
    ),
    # ========== IFR APPROACH REQUESTS - FRENCH ==========
    TestCase(
        "AF1418 demande approche ILS piste 27",
        "request_ils_approach",
        "fr",
        "approach",
        "French ILS",
        expected_runway="27",
    ),
    TestCase(
        "F-GXYZ demande approche à vue",
        "request_visual_approach",
        "fr",
        "approach",
        "French visual",
    ),
    TestCase(
        "F-ABCD demande approche RNAV", "request_rnav_approach", "fr", "approach", "French RNAV"
    ),
    # ========== ESTABLISHED - ENGLISH ==========
    TestCase(
        "N123AB established ILS runway 27",
        "report_established",
        "en",
        "approach",
        "Established ILS",
        expected_runway="27",
    ),
    TestCase(
        "Cessna 456 established on the localizer",
        "report_established",
        "en",
        "approach",
        "Established localizer",
    ),
    # ========== ESTABLISHED - FRENCH ==========
    TestCase(
        "AF1418 établi ILS piste 09",
        "report_established",
        "fr",
        "approach",
        "French established",
        expected_runway="09",
    ),
    TestCase("F-GXYZ établi localizer", "report_established", "fr", "approach", "French localizer"),
    # ========== FIELD IN SIGHT - ENGLISH ==========
    TestCase("N123AB field in sight", "report_field_in_sight", "en", "approach", "Field in sight"),
    TestCase(
        "Cessna 456, airport in sight",
        "report_field_in_sight",
        "en",
        "approach",
        "Airport in sight",
    ),
    # ========== FIELD IN SIGHT - FRENCH ==========
    TestCase(
        "AF1418, terrain en vue", "report_field_in_sight", "fr", "approach", "French field in sight"
    ),
    TestCase(
        "F-GXYZ, on a le terrain", "report_field_in_sight", "fr", "approach", "French got field"
    ),
    # ========== ALTITUDE REQUESTS - ENGLISH ==========
    TestCase(
        "N123AB request flight level 350",
        "request_altitude_change",
        "en",
        "enroute",
        "FL request",
        expected_altitude=35000,
    ),
    TestCase(
        "Cessna 456 request 8000",
        "request_altitude_change",
        "en",
        "enroute",
        "Altitude request",
        expected_altitude=8000,
    ),
    TestCase(
        "November 789 requesting higher",
        "request_altitude_change",
        "en",
        "enroute",
        "Higher request",
    ),
    # ========== ALTITUDE REQUESTS - FRENCH ==========
    TestCase(
        "AF1418 demande niveau 350",
        "request_altitude_change",
        "fr",
        "enroute",
        "French FL",
        expected_altitude=35000,
    ),
    TestCase(
        "F-GXYZ demande altitude 5000",
        "request_altitude_change",
        "fr",
        "enroute",
        "French altitude",
        expected_altitude=5000,
    ),
    # ========== ALTITUDE REPORTS - ENGLISH ==========
    TestCase("N123AB level flight level 350", "report_level", "en", "enroute", "Level report"),
    TestCase(
        "Cessna 456 leaving 3000 for 5000", "report_leaving", "en", "enroute", "Leaving altitude"
    ),
    TestCase(
        "November 789 reaching flight level 280",
        "report_reaching",
        "en",
        "enroute",
        "Reaching altitude",
    ),
    # ========== ALTITUDE REPORTS - FRENCH ==========
    TestCase("AF1418 stabilisé niveau 350", "report_level", "fr", "enroute", "French level"),
    TestCase("F-GXYZ passant niveau 100", "report_leaving", "fr", "enroute", "French leaving"),
    TestCase("F-ABCD niveau atteint", "report_level", "fr", "enroute", "French level reached"),
    # ========== HEADING REQUESTS - ENGLISH ==========
    TestCase(
        "N123AB request heading 270",
        "request_heading",
        "en",
        "enroute",
        "Heading request",
        expected_heading=270,
    ),
    TestCase(
        "Cessna 456 request direct ALPHA", "request_direct", "en", "enroute", "Direct request"
    ),
    # ========== TRAFFIC - ENGLISH ==========
    TestCase(
        "N123AB traffic in sight", "report_traffic_in_sight", "en", "traffic", "Traffic in sight"
    ),
    TestCase(
        "Cessna 456, looking for traffic",
        "negative_traffic",
        "en",
        "traffic",
        "Looking for traffic",
    ),
    TestCase(
        "November 789 negative contact", "negative_traffic", "en", "traffic", "Negative contact"
    ),
    TestCase(
        "N456, uh, no joy on that traffic", "negative_traffic", "en", "traffic", "No joy traffic"
    ),
    # ========== TRAFFIC - FRENCH ==========
    TestCase(
        "AF1418 trafic en vue",
        "report_traffic_in_sight",
        "fr",
        "traffic",
        "French traffic in sight",
    ),
    TestCase(
        "F-GXYZ, on cherche le trafic",
        "negative_traffic",
        "fr",
        "traffic",
        "French looking traffic",
    ),
    TestCase(
        "F-ABCD négatif trafic", "negative_traffic", "fr", "traffic", "French negative traffic"
    ),
    # ========== READBACK TAXI - ENGLISH ==========
    TestCase(
        "taxi runway 27 via alpha, N123AB",
        "readback_taxi",
        "en",
        "readback",
        "Taxi readback",
        expected_callsign="N123AB",
        expected_runway="27",
        expected_taxiway="A",
    ),
    TestCase(
        "taxi 09 via bravo charlie, hold short runway 27, Cessna 456",
        "readback_taxi",
        "en",
        "readback",
        "Taxi with hold short",
        expected_runway="09",
        expected_hold_short="runway 27",
    ),
    TestCase(
        "runway 16 via alpha, hold short runway 09, AF1213",
        "readback_taxi",
        "en",
        "readback",
        "Complex taxi readback",
        expected_runway="16",
        expected_taxiway="A",
        expected_hold_short="runway 09",
    ),
    # ========== READBACK TAXI - FRENCH ==========
    TestCase(
        "roulage piste 27 via alpha, F-GXYZ",
        "readback_taxi",
        "fr",
        "readback",
        "French taxi readback",
        expected_runway="27",
        expected_taxiway="A",
    ),
    TestCase(
        "roulage piste 09 via bravo, maintien avant piste 27, AF1418",
        "readback_taxi",
        "fr",
        "readback",
        "French taxi hold short",
        expected_runway="09",
        expected_hold_short="27",
    ),
    # ========== READBACK DEPARTURE - ENGLISH ==========
    TestCase(
        "cleared for takeoff runway 27, N123AB",
        "readback_departure",
        "en",
        "readback",
        "Takeoff readback",
        expected_runway="27",
    ),
    TestCase(
        "cleared takeoff 09 left, Cessna 456",
        "readback_departure",
        "en",
        "readback",
        "Takeoff L readback",
        expected_runway="09L",
    ),
    # ========== READBACK DEPARTURE - FRENCH ==========
    TestCase(
        "autorisé décollage piste 27, AF1418",
        "readback_departure",
        "fr",
        "readback",
        "French takeoff readback",
        expected_runway="27",
    ),
    # ========== READBACK LANDING - ENGLISH ==========
    TestCase(
        "cleared to land runway 27, N123AB",
        "readback_landing",
        "en",
        "readback",
        "Landing readback",
        expected_runway="27",
    ),
    TestCase(
        "cleared land 09, N456",
        "readback_landing",
        "en",
        "readback",
        "Short landing readback",
        expected_runway="09",
    ),
    # ========== READBACK ALTITUDE - ENGLISH ==========
    TestCase(
        "climb flight level 350, Speedbird 123",
        "readback_altitude",
        "en",
        "readback",
        "Climb readback",
        expected_altitude=35000,
    ),
    TestCase(
        "descend 5000, N123AB",
        "readback_altitude",
        "en",
        "readback",
        "Descend readback",
        expected_altitude=5000,
    ),
    # ========== READBACK HEADING - ENGLISH ==========
    TestCase(
        "turn right heading 270, N123AB",
        "readback_heading",
        "en",
        "readback",
        "Heading readback",
        expected_heading=270,
    ),
    TestCase(
        "left turn 180, Cessna 456",
        "readback_heading",
        "en",
        "readback",
        "Left turn readback",
        expected_heading=180,
    ),
    # ========== READBACK FREQUENCY - ENGLISH ==========
    TestCase(
        "contact departure 124.85, N123AB",
        "readback_frequency",
        "en",
        "readback",
        "Frequency readback",
        expected_frequency="124.85",
    ),
    TestCase(
        "tower 118.7, Cessna 456",
        "readback_frequency",
        "en",
        "readback",
        "Tower freq readback",
        expected_frequency="118.7",
    ),
    # ========== READBACK HOLD SHORT - ENGLISH ==========
    TestCase(
        "hold short runway 27, N123AB",
        "readback_hold_short",
        "en",
        "readback",
        "Hold short readback",
        expected_hold_short="runway 27",
    ),
    # ========== ACKNOWLEDGEMENTS - ENGLISH ==========
    TestCase("roger", "roger", "en", "ack", "Roger"),
    TestCase("roger that", "roger", "en", "ack", "Roger that"),
    TestCase("wilco", "wilco", "en", "ack", "Wilco"),
    TestCase("will comply", "wilco", "en", "ack", "Will comply"),
    TestCase("affirmative", "affirm", "en", "ack", "Affirmative"),
    TestCase("negative", "negative", "en", "ack", "Negative"),
    TestCase("unable", "unable", "en", "ack", "Unable"),
    TestCase("say again", "say_again", "en", "ack", "Say again"),
    TestCase("standby", "standby", "en", "ack", "Standby"),
    # ========== ACKNOWLEDGEMENTS - FRENCH ==========
    TestCase("reçu", "roger", "fr", "ack", "French roger"),
    TestCase("bien reçu", "roger", "fr", "ack", "French well received"),
    TestCase("compris", "wilco", "fr", "ack", "French understood"),
    TestCase("bien compris", "wilco", "fr", "ack", "French well understood"),
    TestCase("affirmatif", "affirm", "fr", "ack", "French affirmative"),
    TestCase("négatif", "negative", "fr", "ack", "French negative"),
    TestCase("impossible", "unable", "fr", "ack", "French unable"),
    TestCase("répétez", "say_again", "fr", "ack", "French say again"),
    TestCase("attendez", "standby", "fr", "ack", "French standby"),
    # ========== EMERGENCY - ENGLISH ==========
    TestCase(
        "mayday mayday mayday, N123AB engine failure",
        "declare_emergency",
        "en",
        "emergency",
        "Mayday",
    ),
    TestCase(
        "pan pan pan pan, Cessna 456 low fuel", "declare_emergency", "en", "emergency", "Pan pan"
    ),
    TestCase("cancel emergency, N123AB", "cancel_emergency", "en", "emergency", "Cancel emergency"),
    # ========== EMERGENCY - FRENCH ==========
    TestCase(
        "mayday mayday, AF1418 feu moteur", "declare_emergency", "fr", "emergency", "French mayday"
    ),
    TestCase(
        "pan pan, F-GXYZ problème hydraulique",
        "declare_emergency",
        "fr",
        "emergency",
        "French pan pan",
    ),
    # ========== RADIO CHECK - ENGLISH ==========
    TestCase("N123AB radio check", "request_radio_check", "en", "misc", "Radio check"),
    TestCase("Cessna 456 how do you read", "request_radio_check", "en", "misc", "How do you read"),
    # ========== FREQUENCY CHANGE - ENGLISH ==========
    TestCase(
        "N123AB request frequency change",
        "request_frequency_change",
        "en",
        "misc",
        "Freq change request",
    ),
    # ========== POSITION REPORTS - ENGLISH ==========
    TestCase("N123AB 10 miles south", "report_position", "en", "enroute", "Position report"),
    TestCase(
        "Cessna 456 over ALPHA intersection",
        "report_position",
        "en",
        "enroute",
        "Over intersection",
    ),
    # ========== ATIS REQUEST - ENGLISH ==========
    TestCase("N123AB request ATIS", "request_atis", "en", "ground", "ATIS request"),
    TestCase(
        "Cessna 456 request information", "request_atis", "en", "ground", "Information request"
    ),
    # ========== ATIS REQUEST - FRENCH ==========
    TestCase("AF1418 demande information", "request_atis", "fr", "ground", "French ATIS"),
    # ========== IFR CLEARANCE - ENGLISH ==========
    TestCase("N123AB request IFR clearance", "request_clearance", "en", "ground", "IFR clearance"),
    TestCase(
        "Cessna 456 clearance delivery", "request_clearance", "en", "ground", "Clearance delivery"
    ),
    # ========== IFR CLEARANCE - FRENCH ==========
    TestCase("AF1418 demande clairance", "request_clearance", "fr", "ground", "French clearance"),
    # ========== CANCEL IFR - ENGLISH ==========
    TestCase("N123AB cancel IFR", "cancel_ifr", "en", "approach", "Cancel IFR"),
    # ========== CANCEL IFR - FRENCH ==========
    TestCase("AF1418 annule IFR", "cancel_ifr", "fr", "approach", "French cancel IFR"),
    # ========== FLIGHT FOLLOWING - ENGLISH ==========
    TestCase(
        "N123AB request flight following",
        "request_flight_following",
        "en",
        "enroute",
        "Flight following",
    ),
    TestCase(
        "Cessna 456 request VFR advisories",
        "request_flight_following",
        "en",
        "enroute",
        "VFR advisories",
    ),
    # ========== HESITATIONS AND PARTIAL SPEECH ==========
    TestCase(
        "uh... N123... uh... request taxi", "request_taxi", "en", "hesitation", "Heavy hesitation"
    ),
    TestCase(
        "euh... AF1418... euh... demande roulage",
        "request_taxi",
        "fr",
        "hesitation",
        "French heavy hesitation",
    ),
    TestCase(
        "november one two... uh... three alpha bravo, ready",
        "ready_for_departure",
        "en",
        "hesitation",
        "Broken callsign",
    ),
    TestCase(
        "we're... uh... ready to go when... whenever",
        "ready_for_departure",
        "en",
        "hesitation",
        "Hesitant ready",
    ),
    # ========== GARBLED / UNKNOWN ==========
    TestCase("xkfjsd asdf", "unknown", "en", "garbled", "Garbled input"),
    TestCase("blah blah something", "unknown", "en", "garbled", "Nonsense"),
    TestCase("", "unknown", "en", "garbled", "Empty input"),
    TestCase("123", "unknown", "en", "garbled", "Just numbers"),
]


def run_test(nlu: LocalNLUProvider, test: TestCase) -> TestResult:
    """Run a single test case and return the result."""
    start = time.perf_counter()
    intent = nlu.extract_intent(test.input_text)
    elapsed_ms = (time.perf_counter() - start) * 1000

    # Check intent correctness
    intent_correct = intent.intent_type.value == test.expected_intent

    # Check slot correctness
    slots_correct = True
    if test.expected_callsign and intent.callsign:
        # Normalize callsign comparison (remove dashes, case insensitive)
        expected_cs = test.expected_callsign.replace("-", "").upper()
        actual_cs = intent.callsign.replace("-", "").upper()
        if expected_cs != actual_cs:
            slots_correct = False
    if test.expected_runway and intent.runway != test.expected_runway:
        # Allow some flexibility (09L vs 9L)
        if not (
            test.expected_runway.lstrip("0") == str(intent.runway).lstrip("0")
            if intent.runway
            else False
        ):
            slots_correct = False
    if test.expected_taxiway and intent.taxiway:
        if intent.taxiway.upper() != test.expected_taxiway.upper():
            slots_correct = False
    if test.expected_altitude and intent.altitude != test.expected_altitude:
        slots_correct = False
    if test.expected_heading and intent.heading != test.expected_heading:
        slots_correct = False
    if test.expected_frequency and intent.frequency != test.expected_frequency:
        slots_correct = False
    if test.expected_hold_short and intent.hold_short:
        # Normalize hold short comparison
        expected_hs = test.expected_hold_short.lower().replace("runway ", "")
        actual_hs = intent.hold_short.lower().replace("runway ", "").replace("piste ", "")
        if expected_hs not in actual_hs and actual_hs not in expected_hs:
            slots_correct = False

    extracted_slots = {
        "callsign": intent.callsign,
        "runway": intent.runway,
        "taxiway": intent.taxiway,
        "altitude": intent.altitude,
        "heading": intent.heading,
        "frequency": intent.frequency,
        "hold_short": intent.hold_short,
        "position": intent.position,
    }

    return TestResult(
        test_case=test,
        actual_intent=intent.intent_type.value,
        confidence=intent.confidence,
        intent_correct=intent_correct,
        slots_correct=slots_correct,
        elapsed_ms=elapsed_ms,
        extracted_slots=extracted_slots,
    )


def main() -> int:
    """Run the NLU evaluation."""
    parser = argparse.ArgumentParser(description="NLU Evaluation Script")
    parser.add_argument(
        "--model",
        default=DEFAULT_NLU_MODEL,
        help=f"NLU model ID (default: {DEFAULT_NLU_MODEL})",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed results for each test",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("NLU EVALUATION")
    print("=" * 70)

    # Check model availability
    model_path = get_nlu_model_path(args.model)
    if not model_path:
        print(f"ERROR: Model '{args.model}' not found.")
        return 1

    print(f"Model: {model_path.name}")
    print(f"Test cases: {len(TEST_CASES)}")
    print()

    # Initialize NLU
    print("Loading NLU model...")
    nlu = LocalNLUProvider()
    try:
        nlu.initialize(
            {
                "model_path": str(model_path),
                "n_ctx": 2048,
                "n_threads": 4,
                "n_gpu_layers": 0,
            }
        )
    except Exception as e:
        print(f"ERROR: Failed to load model: {e}")
        return 1

    print(f"Model loaded: {nlu.name}")
    print()
    print("Running tests...")
    print("-" * 70)

    # Run all tests
    results: list[TestResult] = []
    for i, test in enumerate(TEST_CASES):
        result = run_test(nlu, test)
        results.append(result)

        # Progress indicator
        status = "✓" if result.intent_correct else "✗"
        if args.verbose or not result.intent_correct:
            print(f"{status} [{test.language}] {test.category}: {test.description}")
            print(f'  Input: "{test.input_text}"')
            print(
                f"  Expected: {test.expected_intent}, Got: {result.actual_intent} (conf: {result.confidence:.2f})"
            )
            if not result.slots_correct:
                print(f"  Slots: {result.extracted_slots}")
            print()
        else:
            # Show progress dots
            if (i + 1) % 20 == 0:
                print(f"  Completed {i + 1}/{len(TEST_CASES)} tests...")

    # Cleanup
    nlu.shutdown()

    # Calculate statistics
    print()
    print("=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    total = len(results)
    correct_intent = sum(1 for r in results if r.intent_correct)
    correct_slots = sum(1 for r in results if r.intent_correct and r.slots_correct)
    avg_confidence = sum(r.confidence for r in results) / total if total > 0 else 0
    avg_time = sum(r.elapsed_ms for r in results) / total if total > 0 else 0

    print("\nOverall Accuracy:")
    print(f"  Intent accuracy:     {correct_intent}/{total} ({100 * correct_intent / total:.1f}%)")
    print(f"  Full accuracy:       {correct_slots}/{total} ({100 * correct_slots / total:.1f}%)")
    print(f"  Average confidence:  {avg_confidence:.2f}")
    print(f"  Average latency:     {avg_time:.0f}ms")

    # By language
    print("\nBy Language:")
    for lang in ["en", "fr"]:
        lang_results = [r for r in results if r.test_case.language == lang]
        if lang_results:
            lang_correct = sum(1 for r in lang_results if r.intent_correct)
            lang_total = len(lang_results)
            print(
                f"  {lang.upper()}: {lang_correct}/{lang_total} ({100 * lang_correct / lang_total:.1f}%)"
            )

    # By category
    print("\nBy Category:")
    categories = sorted(set(r.test_case.category for r in results))
    for cat in categories:
        cat_results = [r for r in results if r.test_case.category == cat]
        if cat_results:
            cat_correct = sum(1 for r in cat_results if r.intent_correct)
            cat_total = len(cat_results)
            pct = 100 * cat_correct / cat_total
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            print(f"  {cat:12} {bar} {cat_correct:2}/{cat_total:2} ({pct:5.1f}%)")

    # Failed tests summary
    failed = [r for r in results if not r.intent_correct]
    if failed:
        print(f"\nFailed Tests ({len(failed)}):")
        for r in failed[:15]:  # Show first 15
            print(f'  [{r.test_case.language}] "{r.test_case.input_text[:40]}..."')
            print(f"      Expected: {r.test_case.expected_intent}, Got: {r.actual_intent}")
        if len(failed) > 15:
            print(f"  ... and {len(failed) - 15} more")

    # Confidence distribution
    print("\nConfidence Distribution:")
    conf_bins = [(0, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.01)]
    for low, high in conf_bins:
        count = sum(1 for r in results if low <= r.confidence < high)
        bar = "█" * (count * 2 // max(1, total // 20))
        print(f"  {low:.1f}-{high:.1f}: {bar} {count}")

    print()
    print("=" * 70)

    # Return success if accuracy > 70%
    return 0 if (correct_intent / total) >= 0.7 else 1


if __name__ == "__main__":
    sys.exit(main())
