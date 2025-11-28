# Realistic ATC System Implementation Plan

## Overview

This document outlines the implementation plan for a comprehensive, realistic ATC system for AirBorne flight simulator. The system will support all airports in the database (excluding heliports), provide Full VFR operations, use concatenated audio for dynamic phrases, and integrate real METAR weather with simulation fallback.

---

## 1. Architecture Overview

### 1.1 New Components

```
src/airborne/
├── services/
│   └── weather/
│       ├── __init__.py
│       ├── weather_service.py      # Main weather service
│       ├── metar_parser.py         # METAR string parser
│       ├── weather_simulator.py    # Simulated weather generator
│       └── models.py               # Weather data models
│
├── plugins/radio/
│   ├── atc/
│   │   ├── __init__.py
│   │   ├── atc_controller.py       # Simulated ATC controller
│   │   ├── flight_state.py         # Flight phase state machine
│   │   ├── clearance_generator.py  # Generates clearances based on context
│   │   └── frequency_manager.py    # Frequency-context awareness
│   ├── atis/
│   │   ├── __init__.py
│   │   ├── dynamic_atis.py         # Dynamic ATIS generator
│   │   └── atis_builder.py         # Builds ATIS audio sequences
│   └── speech/
│       ├── __init__.py
│       ├── phrase_builder.py       # Builds concatenated audio sequences
│       └── audio_sequence.py       # Audio sequence player
```

### 1.2 Data Flow

```
Weather Service                    Flight State Machine
     │                                    │
     ▼                                    ▼
┌─────────────────┐              ┌─────────────────┐
│  METAR Parser   │              │  State Tracker  │
│  + Simulator    │              │ (on_ground,     │
│  (5 min cycle)  │              │  taxiing, etc)  │
└────────┬────────┘              └────────┬────────┘
         │                                │
         ▼                                ▼
┌─────────────────────────────────────────────────┐
│              Dynamic ATIS Generator              │
│  - Airport info + weather + runway selection     │
│  - Updates every 5 minutes or on weather change  │
└────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│              ATC Controller                      │
│  - Receives pilot requests                       │
│  - Validates against flight state               │
│  - Generates appropriate clearances             │
│  - Uses phrase builder for audio sequences      │
└────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│              Audio Sequence Player               │
│  - Plays concatenated phonetic audio            │
│  - Applies radio effects                        │
│  - Queues pilot/ATC messages                    │
└────────────────────────────────────────────────┘
```

---

## 2. Weather System

### 2.1 Weather Service

```python
class WeatherService:
    """Provides weather data from METAR or simulation."""

    def __init__(self, cache_duration: float = 300.0):  # 5 minutes
        self.cache: dict[str, CachedWeather] = {}
        self.simulator = WeatherSimulator()
        self.parser = METARParser()

    async def get_weather(self, icao: str) -> Weather:
        """Get weather for airport, trying METAR first."""
        # 1. Check cache
        # 2. Try METAR API
        # 3. Fall back to simulation

    def get_active_runway(self, airport: Airport, weather: Weather) -> str:
        """Determine best runway based on wind."""
        # Calculate headwind component for each runway
        # Return runway with best headwind
```

### 2.2 METAR Sources (in order)

1. **AVWX API** (free, global): `https://avwx.rest/api/metar/{ICAO}`
2. **Aviation Weather API**: `https://aviationweather.gov/api/data/metar?ids={ICAO}`
3. **Fallback**: Simulated weather

### 2.3 Weather Simulation

```python
class WeatherSimulator:
    """Generates realistic weather patterns."""

    def generate(self, icao: str, seed: int | None = None) -> Weather:
        # Use time-based seed for consistency across 5-minute periods
        # Generate:
        # - Wind direction (0-360) with realistic variations
        # - Wind speed (0-30 kts typical, occasional gusts)
        # - Visibility (1-10+ SM)
        # - Sky condition (clear/few/scattered/broken/overcast)
        # - Temperature based on location and time
        # - Altimeter (29.80-30.20 typical)
```

---

## 3. Dynamic ATIS

### 3.1 ATIS Structure

Standard ATIS format:
```
[Airport] Information [Letter]
[Time] Zulu
Wind [direction] at [speed], [gusts if any]
Visibility [miles]
Sky [condition], ceiling [if applicable]
Temperature [temp], dewpoint [dew]
Altimeter [setting]
[Remarks]
Landing and departing runway [number]
Advise on initial contact you have information [Letter]
```

### 3.2 Audio Building

Use concatenated audio files:
```python
class ATISBuilder:
    def build_atis_sequence(self, atis: ATISInfo) -> list[str]:
        """Build list of audio file paths for ATIS."""
        sequence = []

        # Airport name
        sequence.append(f"airport_{atis.icao.lower()}")  # or generic "airport"
        sequence.append("information")
        sequence.append(f"phonetic_{atis.letter.lower()}")  # alpha, bravo, etc.

        # Time
        sequence.extend(self._build_time(atis.time_zulu))
        sequence.append("zulu")

        # Wind
        sequence.append("wind")
        sequence.extend(self._build_number(atis.wind_direction))
        sequence.append("at")
        sequence.extend(self._build_number(atis.wind_speed))
        if atis.wind_gust:
            sequence.append("gusting")
            sequence.extend(self._build_number(atis.wind_gust))

        # ... continue for all ATIS elements

        return sequence
```

---

## 4. Flight State Machine

### 4.1 States

```python
class FlightPhase(Enum):
    PARKED_COLD = "parked_cold"           # Engine off, at parking
    PARKED_HOT = "parked_hot"             # Engine running, at parking
    TAXIING_OUT = "taxiing_out"           # Taxiing to runway
    HOLDING_SHORT = "holding_short"        # At hold short line
    ON_RUNWAY = "on_runway"               # On runway, ready for takeoff
    TAKEOFF_ROLL = "takeoff_roll"         # Accelerating on runway
    INITIAL_CLIMB = "initial_climb"       # Just after rotation, <1000 AGL
    DEPARTURE = "departure"               # Climbing out, 1000-3000 AGL
    CRUISE = "cruise"                     # Level flight, >3000 AGL
    DESCENDING = "descending"             # Descending toward airport
    PATTERN_ENTRY = "pattern_entry"       # Entering traffic pattern
    DOWNWIND = "downwind"                 # On downwind leg
    BASE = "base"                         # On base leg
    FINAL = "final"                       # On final approach
    LANDING_ROLL = "landing_roll"         # On runway after touchdown
    TAXIING_IN = "taxiing_in"            # Taxiing to parking
```

### 4.2 State Transitions

```
PARKED_COLD ──[engine start]──► PARKED_HOT
                                    │
            ◄──[engine shutdown]────┘
                                    │
                    [taxi clearance + movement]
                                    │
                                    ▼
                              TAXIING_OUT
                                    │
                    [reach hold short line]
                                    │
                                    ▼
                             HOLDING_SHORT
                                    │
                    [takeoff clearance + enter runway]
                                    │
                                    ▼
                              ON_RUNWAY
                                    │
                    [throttle up + rolling]
                                    │
                                    ▼
                             TAKEOFF_ROLL
                                    │
                    [airborne + climbing]
                                    │
                                    ▼
                            INITIAL_CLIMB
                                    │
                    [>1000 AGL]
                                    │
                                    ▼
                              DEPARTURE ◄────────────────┐
                                    │                    │
                    [>3000 AGL + level]          [go-around]
                                    │                    │
                                    ▼                    │
                               CRUISE                    │
                                    │                    │
                    [descending toward airport]         │
                                    │                    │
                                    ▼                    │
                             DESCENDING                  │
                                    │                    │
                    [pattern altitude + position]       │
                                    │                    │
                                    ▼                    │
                           PATTERN_ENTRY                 │
                                    │                    │
                    [abeam numbers]                     │
                                    │                    │
                                    ▼                    │
                              DOWNWIND                   │
                                    │                    │
                    [45° past threshold]                │
                                    │                    │
                                    ▼                    │
                                BASE                     │
                                    │                    │
                    [aligned with runway]               │
                                    │                    │
                                    ▼                    │
                               FINAL ───[go-around]─────┘
                                    │
                    [touchdown]
                                    │
                                    ▼
                            LANDING_ROLL
                                    │
                    [clear runway + taxi]
                                    │
                                    ▼
                             TAXIING_IN
                                    │
                    [reach parking]
                                    │
                                    ▼
                             PARKED_HOT
```

---

## 5. ATC Communications

### 5.1 Request Types by Phase

| Phase | Available Requests |
|-------|-------------------|
| PARKED_COLD | Request ATIS, Radio Check |
| PARKED_HOT | Request Taxi, Request ATIS |
| TAXIING_OUT | Report Position |
| HOLDING_SHORT | Ready for Departure, Request Intersection Departure |
| ON_RUNWAY | Report Ready |
| DEPARTURE | Contact Departure, Report Altitude |
| CRUISE | Request Flight Following, Position Report |
| DESCENDING | Inbound Report |
| PATTERN_ENTRY | Request Pattern Entry, Report Position |
| DOWNWIND | Report Downwind |
| BASE | Report Base |
| FINAL | Report Final |
| LANDING_ROLL | Clear of Runway |
| TAXIING_IN | Request Parking |

### 5.2 ATC Response Generation

```python
class ClearanceGenerator:
    """Generates context-aware ATC clearances."""

    def generate_taxi_clearance(
        self,
        callsign: str,
        airport: Airport,
        runway: str,
        position: str
    ) -> ATCClearance:
        """Generate taxi clearance with route."""
        # Determine taxiway route from position to runway
        taxiway = self._get_taxiway_route(airport, position, runway)

        return ATCClearance(
            type="taxi",
            audio_sequence=[
                *self._build_callsign(callsign),
                "ground",
                "taxi_to_runway",
                *self._build_runway(runway),
                "via",
                *self._build_taxiway(taxiway),
            ],
            data={"runway": runway, "taxiway": taxiway}
        )

    def generate_takeoff_clearance(
        self,
        callsign: str,
        runway: str,
        wind: Wind
    ) -> ATCClearance:
        """Generate takeoff clearance with wind."""
        return ATCClearance(
            type="takeoff",
            audio_sequence=[
                *self._build_callsign(callsign),
                "runway",
                *self._build_runway(runway),
                "cleared_for_takeoff",
                "wind",
                *self._build_wind(wind),
            ],
            data={"runway": runway}
        )
```

### 5.3 Frequency Management

```python
class FrequencyContext:
    """Tracks which frequency should be used for each operation."""

    FREQUENCY_MAP = {
        "PARKED_COLD": None,          # No ATC contact needed
        "PARKED_HOT": "GROUND",       # Contact ground for taxi
        "TAXIING_OUT": "GROUND",      # Stay with ground
        "HOLDING_SHORT": "TOWER",     # Contact tower for takeoff
        "ON_RUNWAY": "TOWER",
        "TAKEOFF_ROLL": "TOWER",
        "INITIAL_CLIMB": "TOWER",
        "DEPARTURE": "DEPARTURE",     # Contact departure
        "CRUISE": "CENTER",           # Contact center (or remain with departure)
        "DESCENDING": "APPROACH",     # Contact approach
        "PATTERN_ENTRY": "TOWER",     # Contact tower
        "DOWNWIND": "TOWER",
        "BASE": "TOWER",
        "FINAL": "TOWER",
        "LANDING_ROLL": "TOWER",
        "TAXIING_IN": "GROUND",       # Contact ground
    }

    def get_expected_frequency(self, phase: FlightPhase) -> str | None:
        return self.FREQUENCY_MAP.get(phase.value)

    def validate_frequency(self, current_freq: float, expected_type: str) -> bool:
        """Check if tuned to correct frequency for operation."""
        # Look up expected frequency from airport database
        # Compare with current frequency
```

---

## 6. Audio System

### 6.1 Required Audio Files

**New phonetic/number files needed:**
```
data/speech/en/atc/
├── common/                      # Shared across all ATC positions
│   ├── phonetic_alpha.wav       # Already exists
│   ├── phonetic_bravo.wav
│   ├── ... (A-Z)
│   ├── number_0.wav through number_9.wav
│   ├── niner.wav
│   ├── hundred.wav
│   ├── thousand.wav
│   ├── decimal.wav (or "point")
│   ├── zulu.wav
│   ├── roger.wav
│   ├── affirmative.wav
│   ├── negative.wav
│   ├── standby.wav
│   ├── say_again.wav
│   ├── cleared.wav
│   ├── contact.wav
│   ├── runway.wav
│   ├── taxi_to.wav
│   ├── hold_short.wav
│   ├── cross.wav
│   ├── via.wav
│   ├── wind.wav
│   ├── at.wav
│   ├── gusting.wav
│   ├── knots.wav
│   ├── visibility.wav
│   ├── miles.wav
│   ├── ceiling.wav
│   ├── feet.wav
│   ├── temperature.wav
│   ├── dewpoint.wav
│   ├── altimeter.wav
│   ├── information.wav
│   ├── landing_and_departing.wav
│   ├── advise_on_initial_contact.wav
│   ├── you_have.wav
│   ├── cleared_for_takeoff.wav
│   ├── cleared_to_land.wav
│   ├── line_up_and_wait.wav
│   ├── traffic_pattern.wav
│   ├── left_downwind.wav
│   ├── right_downwind.wav
│   ├── enter.wav
│   ├── report.wav
│   ├── midfield.wav
│   ├── downwind.wav
│   ├── base.wav
│   ├── final.wav
│   ├── go_around.wav
│   ├── make.wav
│   ├── left_traffic.wav
│   ├── right_traffic.wav
│   ├── extend.wav
│   ├── number.wav (sequence number)
│   ├── following.wav
│   ├── traffic.wav
│   └── o_clock.wav (for traffic positions)
│
├── ground/                      # Ground control specific
│   ├── good_morning.wav
│   ├── good_afternoon.wav
│   ├── good_evening.wav
│   └── ground.wav
│
├── tower/                       # Tower control specific
│   └── tower.wav
│
├── atis/                        # ATIS specific
│   ├── airport_information.wav
│   ├── sky_clear.wav
│   ├── few_clouds.wav
│   ├── scattered.wav
│   ├── broken.wav
│   ├── overcast.wav
│   └── variable.wav

data/speech/en/pilot/
├── common/
│   ├── phonetic_alpha.wav through phonetic_zulu.wav
│   ├── number_0.wav through number_9.wav
│   ├── roger.wav
│   ├── wilco.wav
│   ├── ready.wav
│   ├── request.wav
│   ├── taxi.wav
│   ├── departure.wav
│   ├── with_you.wav
│   ├── level.wav
│   ├── climbing.wav
│   ├── descending.wav
│   ├── inbound.wav
│   ├── for_landing.wav
│   ├── full_stop.wav
│   ├── touch_and_go.wav
│   ├── clear_of_runway.wav
│   └── information.wav
```

### 6.2 Audio Generation Script

Extend `scripts/generate_speech.py` to generate all needed files:

```python
# New voice configurations
VOICES = {
    "atc_ground": {"voice": "Evan", "rate": 180},
    "atc_tower": {"voice": "Evan", "rate": 180},
    "atc_approach": {"voice": "Evan", "rate": 175},
    "atc_atis": {"voice": "Samantha", "rate": 160},  # Slower for ATIS
    "pilot": {"voice": "Oliver", "rate": 190},
}

# Phrases to generate
PHRASES = {
    "phonetics": ["alpha", "bravo", "charlie", ...],
    "numbers": ["zero", "one", "two", ..., "niner"],
    "atc_common": ["roger", "affirmative", "cleared", ...],
    "atc_taxi": ["taxi to runway", "hold short", ...],
    "atc_pattern": ["enter left downwind", "cleared to land", ...],
}
```

---

## 7. Implementation Phases

### Phase 1: Weather System (2-3 hours)
1. Create weather service with METAR fetching
2. Implement METAR parser
3. Create weather simulator for fallback
4. Add active runway calculation

### Phase 2: Dynamic ATIS (3-4 hours)
1. Create ATIS builder for audio sequences
2. Implement ATIS update cycle (5 minutes)
3. Generate required ATIS audio files
4. Integrate with radio plugin

### Phase 3: Flight State Machine (2-3 hours)
1. Implement flight phase state machine
2. Add automatic state detection based on:
   - Ground speed
   - Altitude AGL
   - Position relative to airport/runway
   - Engine state
3. Integrate with radio plugin

### Phase 4: ATC Communications (4-5 hours)
1. Create clearance generator
2. Implement request handlers for each phase
3. Add frequency validation
4. Generate required ATC audio files

### Phase 5: VFR Pattern Work (2-3 hours)
1. Add pattern entry detection
2. Implement traffic pattern state tracking
3. Add pattern-specific ATC communications
4. Handle touch-and-go vs full-stop

### Phase 6: Integration & Testing (2-3 hours)
1. Integrate all components
2. Test full flight cycle
3. Fix edge cases
4. Performance optimization

---

## 8. Example Interaction Flow

### Full VFR Flight Example

```
1. Start at parking (PARKED_COLD)
   Player: [Tunes ATIS frequency]
   System: [Plays dynamic ATIS]

2. Start engine (PARKED_HOT)
   Player: [Opens ATC menu] → "Request Taxi"
   Player: "Palo Alto Ground, November 5 8 3 Quebec Papa,
            at transient parking with information Alpha,
            request taxi"
   ATC: "November 5 8 3 Quebec Papa, Palo Alto Ground,
         taxi to runway 3 1 via Alpha"
   Player: "Taxi runway 3 1 via Alpha, 5 8 3 Quebec Papa"

3. Taxi to runway (TAXIING_OUT → HOLDING_SHORT)
   Player: [Opens ATC menu] → "Ready for Departure"
   Player: "Palo Alto Tower, 5 8 3 Quebec Papa,
            holding short runway 3 1, ready for departure"
   ATC: "5 8 3 Quebec Papa, runway 3 1, cleared for takeoff,
         wind 3 2 0 at 8"
   Player: "Cleared for takeoff runway 3 1, 5 8 3 Quebec Papa"

4. Takeoff (ON_RUNWAY → TAKEOFF_ROLL → INITIAL_CLIMB)
   [Automatic state progression based on airspeed/altitude]

5. Departure (DEPARTURE)
   Player: [Opens ATC menu] → "Report Position"
   Player: "Palo Alto Tower, 5 8 3 Quebec Papa,
            departing to the northwest, 1 thousand 5 hundred"
   ATC: "5 8 3 Quebec Papa, roger, frequency change approved"

6. Pattern return (CRUISE → DESCENDING → PATTERN_ENTRY)
   Player: [Opens ATC menu] → "Inbound for Landing"
   Player: "Palo Alto Tower, 5 8 3 Quebec Papa,
            5 miles northwest, inbound for landing with Alpha"
   ATC: "5 8 3 Quebec Papa, Palo Alto Tower,
         enter left downwind runway 3 1, report midfield"
   Player: "Left downwind 3 1, report midfield, 5 8 3 Quebec Papa"

7. Pattern (DOWNWIND → BASE → FINAL)
   Player: [Opens ATC menu] → "Report Midfield Downwind"
   Player: "5 8 3 Quebec Papa, midfield downwind runway 3 1"
   ATC: "5 8 3 Quebec Papa, number 1, cleared to land runway 3 1"
   Player: "Cleared to land runway 3 1, 5 8 3 Quebec Papa"

8. Landing (LANDING_ROLL → TAXIING_IN)
   Player: [Opens ATC menu] → "Clear of Runway"
   Player: "5 8 3 Quebec Papa, clear of runway 3 1"
   ATC: "5 8 3 Quebec Papa, contact ground point 6"
   Player: "Ground point 6, 5 8 3 Quebec Papa"

9. Return to parking
   [Tune ground frequency]
   Player: "Palo Alto Ground, 5 8 3 Quebec Papa,
            clear of runway 3 1, request taxi to transient"
   ATC: "5 8 3 Quebec Papa, taxi to transient parking via Alpha"
```

---

## 9. Configuration

### 9.1 New Configuration Files

```yaml
# config/atc_config.yaml
atc:
  weather:
    update_interval: 300  # 5 minutes
    metar_sources:
      - name: "avwx"
        url: "https://avwx.rest/api/metar/{icao}"
        timeout: 5
      - name: "aviationweather"
        url: "https://aviationweather.gov/api/data/metar"
        timeout: 5
    simulation_fallback: true

  atis:
    auto_update: true
    update_on_weather_change: true
    letter_cycle: "alpha_zulu"  # or "alpha_november"

  communications:
    response_delay_min: 1.5
    response_delay_max: 4.0
    readback_required: true
    abbreviate_callsign_after_contact: true

  frequencies:
    default_ground: 121.6
    default_tower: 118.6
    default_atis: 128.25
```

---

## 10. Success Criteria

1. **Dynamic ATIS**: ATIS updates every 5 minutes with current weather
2. **Correct Runway Selection**: Active runway based on wind direction
3. **Context-Aware Menu**: Only shows relevant options for current flight phase
4. **Proper Phraseology**: Uses correct ICAO phraseology
5. **Callsign Handling**: Proper callsign format and abbreviation after contact
6. **Frequency Awareness**: Warns if on wrong frequency
7. **Pattern Work**: Full VFR pattern operations supported
8. **Audio Quality**: Clear, realistic concatenated audio playback
