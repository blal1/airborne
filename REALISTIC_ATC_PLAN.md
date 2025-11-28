# Realistic ATC Implementation Plan

## Overview
Transform the ATC system into a highly realistic radio communications experience with modular audio, realistic procedures, and immersive effects.

---

## Phase 1: Modular Speech System (Foundation)

### 1.1 Phonetic Alphabet Audio Files
**Goal**: Break down all speech into reusable phonetic components

**Audio Assets Needed**:
```
/data/speech/en/phonetic/
├── alpha.mp3
├── bravo.mp3
├── charlie.mp3
├── delta.mp3
├── echo.mp3
├── foxtrot.mp3
├── golf.mp3
├── hotel.mp3
├── india.mp3
├── juliett.mp3
├── kilo.mp3
├── lima.mp3
├── mike.mp3
├── november.mp3
├── oscar.mp3
├── papa.mp3
├── quebec.mp3
├── romeo.mp3
├── sierra.mp3
├── tango.mp3
├── uniform.mp3
├── victor.mp3
├── whiskey.mp3
├── xray.mp3
├── yankee.mp3
└── zulu.mp3
```

**Numbers** (aviation specific):
```
/data/speech/en/numbers/
├── zero.mp3
├── one.mp3
├── two.mp3
├── three.mp3
├── four.mp3
├── five.mp3
├── six.mp3
├── seven.mp3
├── eight.mp3
├── niner.mp3      # Special aviation pronunciation
├── hundred.mp3
├── thousand.mp3
├── decimal.mp3
└── point.mp3
```

### 1.2 Modular Phraseology Components
**Goal**: Build realistic ATC messages from reusable parts

**Common Phrases**:
```
/data/speech/en/atc/common/
├── roger.mp3
├── wilco.mp3
├── affirmative.mp3
├── negative.mp3
├── say_again.mp3
├── standby.mp3
├── contact.mp3
├── frequency.mp3
├── squawk.mp3
├── cleared.mp3
├── taxi.mp3
├── hold_short.mp3
├── runway.mp3
├── via.mp3
├── direct.mp3
├── climb.mp3
├── descend.mp3
├── maintain.mp3
├── altimeter.mp3
└── ...
```

**Position Reports**:
```
/data/speech/en/atc/positions/
├── tower.mp3
├── ground.mp3
├── approach.mp3
├── departure.mp3
├── center.mp3
├── clearance_delivery.mp3
├── left.mp3
├── right.mp3
├── base.mp3
├── final.mp3
├── downwind.mp3
├── crosswind.mp3
└── upwind.mp3
```

### 1.3 Speech Synthesis Engine
**File**: `src/airborne/audio/tts/modular_speech.py`

```python
class ModularSpeechEngine:
    """
    Builds speech from phonetic components.

    Features:
    - Combine phonetic alphabet for callsigns
    - Assemble numbers with proper aviation pronunciation
    - Join phrase chunks with natural timing
    - Add realistic pauses and inflection
    """

    def build_callsign(self, registration: str) -> list[str]:
        """
        Convert N123AB to ['november', 'one', 'two', 'three',
                            'alpha', 'bravo']
        """

    def build_number(self, number: int) -> list[str]:
        """Convert 2500 to ['two', 'five', 'hundred']"""

    def build_frequency(self, freq: float) -> list[str]:
        """Convert 121.5 to ['one', 'two', 'one', 'decimal', 'five']"""

    def build_altitude(self, altitude: int) -> list[str]:
        """Convert 2500 to ['two', 'thousand', 'five', 'hundred']"""
```

---

## Phase 2: Radio Panel UI

### 2.1 Radio Stack Display
**Goal**: Create realistic avionics-style radio panel

**Components**:
1. **COM1 Radio**
   - Active frequency display (large, green)
   - Standby frequency display (smaller, amber)
   - Tuning knobs (coarse/fine)
   - Swap button (⇄)
   - Volume knob
   - Squelch control

2. **COM2 Radio** (same layout)

3. **Audio Panel**
   - COM1/COM2 selector switches
   - Transmit selector (COM1/COM2)
   - Speaker/Headset toggle
   - Volume sliders for each radio
   - Marker beacon lights (O/M/I)

**UI File**: `src/airborne/ui/radio_panel.py`

```python
class RadioPanel(Menu):
    """
    Realistic radio stack interface.

    Features:
    - Click to select frequency digit
    - Mouse wheel to tune
    - Keyboard shortcuts (F12 for COM1, F11 for COM2)
    - Visual feedback (selected digit highlighted)
    - Realistic knob behavior
    """
```

### 2.2 Frequency Database
**Goal**: Accurate airport frequencies based on real-world data

**Database**: `data/frequencies/airports.json`

```json
{
  "KSFO": {
    "name": "San Francisco Intl",
    "size": "large",
    "frequencies": {
      "atis": [135.4, 118.85],
      "clearance": 118.2,
      "ground": [121.8, 121.9],
      "tower": [120.5, 128.65],
      "departure": [135.1, 135.65],
      "approach": [115.8, 135.1]
    },
    "coverage": {
      "ground": 5.0,      // nm
      "tower": 25.0,
      "approach": 50.0,
      "departure": 50.0
    }
  },
  "KPAO": {
    "name": "Palo Alto",
    "size": "small",
    "frequencies": {
      "ctaf": 122.05,
      "unicom": 122.95
    },
    "coverage": {
      "ctaf": 10.0
    }
  }
}
```

**Manager**: `src/airborne/plugins/radio/frequency_database.py`

```python
class FrequencyDatabase:
    """
    Loads and provides airport frequency information.

    Features:
    - Query frequencies by airport code
    - Get appropriate frequency for phase of flight
    - Coverage area calculations
    - Frequency type validation
    """
```

---

## Phase 3: Distance-Based Audio Degradation

### 3.1 Signal Strength Calculator
**File**: `src/airborne/audio/effects/signal_strength.py`

```python
class SignalStrengthCalculator:
    """
    Calculate radio signal quality based on distance.

    Factors:
    - Distance from transmitter
    - Altitude (line-of-sight)
    - Terrain blocking
    - Frequency propagation characteristics

    Returns:
    - Signal strength (0.0 to 1.0)
    - Suggested noise/static level
    """

    def calculate_vhf_range(self,
                            aircraft_alt_ft: float,
                            station_alt_ft: float) -> float:
        """
        VHF is line-of-sight.
        Range (nm) ≈ 1.23 × (√aircraft_alt + √station_alt)
        """

    def get_signal_quality(self,
                          distance_nm: float,
                          max_range_nm: float,
                          terrain_factor: float = 1.0) -> float:
        """
        Returns 0.0 (no signal) to 1.0 (perfect)
        """
```

### 3.2 Dynamic Audio Effects
**Enhancement to**: `src/airborne/audio/effects/radio_filter.py`

**New Features**:
```python
class AdaptiveRadioFilter(RadioEffectFilter):
    """
    Adjusts radio effects based on signal quality.

    Effects:
    - Static noise level (increases with distance)
    - Frequency cutoff (degrades with poor signal)
    - Compression ratio (more compression when weak)
    - Dropouts/interference (random at signal edges)
    """

    def update_signal_strength(self, strength: float):
        """Adjust DSP parameters based on signal (0-1)"""

    def add_interference(self, probability: float):
        """Randomly inject brief static bursts"""

    def simulate_dropout(self, duration_ms: float):
        """Briefly cut signal to simulate loss"""
```

---

## Phase 4: Realistic Radio Procedures

### 4.1 Frequency Assignment System
**File**: `src/airborne/plugins/radio/frequency_controller.py`

```python
class FrequencyController:
    """
    Manages frequency changes during flight.

    Workflow:
    1. Ground → Clearance Delivery (if towered)
    2. Clearance → Ground
    3. Ground → Tower (before takeoff)
    4. Tower → Departure (after takeoff)
    5. Departure → Center (en route)
    6. Center → Approach (near destination)
    7. Approach → Tower
    8. Tower → Ground (after landing)

    Features:
    - Automatic suggestions for next frequency
    - Frequency handoff messages
    - Read-back requirements
    """
```

### 4.2 Context-Aware Communications
**Enhancement to**: `src/airborne/plugins/radio/atc_manager.py`

**New Message Types**:
```python
class ATCMessageBuilder:
    """
    Builds realistic ATC messages based on context.

    Message Categories:

    1. Ground Operations:
       - Taxi clearance: "N123AB, taxi runway 28R via Alpha, Bravo"
       - Hold short: "N123AB, hold short runway 28R"
       - Cross runway: "N123AB, cross runway 28R"

    2. Departure:
       - Takeoff clearance: "N123AB, runway 28R, cleared for takeoff"
       - Frequency change: "N123AB, contact departure 135.1"
       - Altitude assignment: "N123AB, climb and maintain 3000"

    3. En Route:
       - Course corrections: "N123AB, turn left heading 270"
       - Altitude changes: "N123AB, descend and maintain 2500"
       - Traffic advisories: "N123AB, traffic 2 o'clock, 5 miles"

    4. Approach:
       - Vectors: "N123AB, turn right heading 310, vectors for ILS 28R"
       - Clearance: "N123AB, cleared ILS runway 28R approach"
       - Descent: "N123AB, descend and maintain 2000"

    5. Landing:
       - Landing clearance: "N123AB, runway 28R, cleared to land"
       - Go-around: "N123AB, go around, traffic on runway"
       - Exit instructions: "N123AB, turn left next taxiway, contact ground"
    """
```

### 4.3 Pilot Response System
**File**: `src/airborne/plugins/radio/pilot_responses.py`

```python
class PilotResponseGenerator:
    """
    Generates proper pilot read-backs.

    Rules:
    - Always read back:
      * Runway assignments
      * Altitude assignments
      * Heading assignments
      * Clearances
      * Frequency changes

    - Use callsign in every transmission
    - Acknowledge with "Roger" or specific read-back

    Example:
    ATC: "N123AB, climb and maintain 3000"
    Pilot: "Climb and maintain 3000, N123AB"
    """
```

---

## Phase 5: Advanced Features

### 5.1 ATIS (Automatic Terminal Information Service)
**Enhancement to**: `src/airborne/plugins/radio/atis.py`

**Features**:
- Continuous loop on designated frequency
- Information code (Alpha, Bravo, Charlie...)
- Weather, wind, active runway
- Altimeter setting
- NOTAMs (Notices to Airmen)
- "Advise on initial contact you have information [code]"

### 5.2 Multiple Concurrent Transmissions
**Feature**: Handle realistic radio traffic

```python
class RadioChannel:
    """
    Simulates a real radio channel.

    Features:
    - Only one transmission at a time
    - Queue incoming messages
    - "Stepped on" effect when multiple transmit
    - Realistic timing between messages
    """
```

### 5.3 Emergency Frequencies
**Special handling**:
- 121.5 MHz (emergency)
- 7500 (hijack), 7600 (comm failure), 7700 (emergency) squawk codes
- Mayday/Pan-pan calls

### 5.4 Traffic Pattern Communications
**For uncontrolled airports**:
```
- "Palo Alto traffic, Cessna 123AB, 10 miles north, inbound landing"
- "Palo Alto traffic, Cessna 123AB, entering left downwind, runway 31"
- "Palo Alto traffic, Cessna 123AB, left base, runway 31"
- "Palo Alto traffic, Cessna 123AB, final, runway 31"
- "Palo Alto traffic, Cessna 123AB, clear of runway 31"
```

---

## Phase 6: UI/UX Enhancements

### 6.1 Radio Tuning Interface
**Methods**:
1. **Mouse Wheel**: Scroll on frequency to tune
2. **Click Digits**: Click digit, use keyboard
3. **Knob Simulation**: Click-drag virtual knobs
4. **Presets**: Quick-select common frequencies
5. **Nearest**: Auto-tune to nearest airport frequencies

### 6.2 Visual Feedback
```
COM1 Display:
┌─────────────────────┐
│ COM1     VOL ▮▮▮▯▯  │
│ ╔═══════╗           │
│ ║ 121.5 ║  [⇄]      │  ← Active (large, green)
│ ╚═══════╝           │
│  118.3              │  ← Standby (amber)
│ [▲] [▼] [◄] [►]     │  ← Tuning controls
└─────────────────────┘

Indicators:
- TX: Transmitting (red)
- RX: Receiving (green)
- SQ: Squelch active (amber)
- SIG: Signal strength bars
```

### 6.3 Audio Panel
```
┌─────────────────────────┐
│   AUDIO PANEL           │
├─────────────────────────┤
│ COM1 [⦿] [♪] ▮▮▮▯▯     │  ← Selected, Speaker on, Volume
│ COM2 [ ] [♪] ▮▮▯▯▯     │
│ NAV1 [ ] [♪] ▮▮▮▮▯     │
│ NAV2 [ ] [♪] ▮▮▮▯▯     │
│                         │
│ TX: ⦿ COM1  ○ COM2      │  ← Transmit selector
│                         │
│ MARKER: O  M  I         │  ← Beacon lights
└─────────────────────────┘
```

---

## Implementation Timeline

### Sprint 1 (Week 1-2): Foundation
- [ ] Create phonetic alphabet audio files
- [ ] Create numbers audio files
- [ ] Implement `ModularSpeechEngine`
- [ ] Create basic frequency database
- [ ] Test speech assembly

### Sprint 2 (Week 3-4): Radio Panel
- [ ] Design radio panel UI
- [ ] Implement frequency tuning
- [ ] Add visual feedback
- [ ] Integrate with existing radio plugin
- [ ] Test frequency management

### Sprint 3 (Week 5-6): Audio Quality
- [ ] Implement `SignalStrengthCalculator`
- [ ] Create adaptive radio filter
- [ ] Add distance-based degradation
- [ ] Implement interference effects
- [ ] Test signal quality at various ranges

### Sprint 4 (Week 7-8): Procedures
- [ ] Build `ATCMessageBuilder`
- [ ] Implement phase-of-flight logic
- [ ] Create pilot response system
- [ ] Add frequency handoffs
- [ ] Test complete ATC workflow

### Sprint 5 (Week 9-10): Polish
- [ ] Add ATIS improvements
- [ ] Implement traffic pattern comms
- [ ] Add emergency procedures
- [ ] Create presets and quick-tune
- [ ] Full integration testing

---

## Audio File Generation Strategy

### Option 1: Record Real Voice Actor
**Pros**: Most realistic
**Cons**: Expensive, time-consuming
**Cost**: ~$500-1000

### Option 2: High-Quality TTS (Eleven Labs, Google Cloud TTS)
**Pros**: Quick, consistent, affordable
**Cons**: Slight robotic quality
**Cost**: ~$50-200

### Option 3: Hybrid Approach (Recommended)
- Use TTS for most components
- Record critical phrases with voice actor
- Apply radio effects to mask TTS quality
**Cost**: ~$200-300

---

## Testing Checklist

### Functionality Tests
- [ ] Callsign pronunciation is accurate
- [ ] Numbers use aviation terminology (niner)
- [ ] Frequencies tune correctly
- [ ] Signal strength calculations work
- [ ] Audio degrades realistically with distance
- [ ] Frequency handoffs occur at right times
- [ ] Read-backs are proper

### Realism Tests
- [ ] Audio sounds like real aviation radio
- [ ] Phraseology matches ICAO standards
- [ ] Timing feels natural (not too fast/slow)
- [ ] Static/interference is subtle, not annoying
- [ ] UI is intuitive for pilots

### Performance Tests
- [ ] Audio playback is smooth
- [ ] No lag when tuning frequencies
- [ ] Multiple audio sources don't stutter
- [ ] Memory usage is reasonable

---

## Configuration Files

### `config/radio_effects.yaml`
```yaml
radio_filter:
  base:
    highpass_cutoff: 300    # Hz
    lowpass_cutoff: 3000    # Hz
    compression_ratio: 4.0

  distance_degradation:
    enabled: true
    min_distance: 0.0       # nm
    max_distance: 50.0      # nm
    static_increase: 0.8    # 0-1 scale

  interference:
    enabled: true
    probability: 0.02       # 2% chance per second
    duration_ms: 100        # Brief burst
```

### `config/frequencies.yaml`
```yaml
frequency_types:
  clearance:
    range: [118.0, 119.95]
    typical: [118.0, 118.95]

  ground:
    range: [121.0, 122.0]
    typical: [121.6, 121.9]

  tower:
    range: [118.0, 136.0]
    typical: [118.0, 128.0]

  approach:
    range: [118.0, 136.0]
    typical: [119.0, 135.0]

  center:
    range: [118.0, 136.0]
    typical: [120.0, 135.0]

  atis:
    range: [118.0, 136.0]
    typical: [135.0, 135.95]

  unicom:
    fixed: 122.95

  ctaf:
    typical: [122.7, 122.8, 122.9, 123.0, 123.05]
```

---

## Success Metrics

### Realism Score
- [ ] Phraseology matches real ATC (95%+)
- [ ] Audio quality sounds authentic
- [ ] Frequency coverage is realistic
- [ ] Signal degradation is believable

### User Experience
- [ ] Radio panel is intuitive
- [ ] Frequency tuning is easy
- [ ] Communications feel immersive
- [ ] Not frustrating or tedious

### Technical Quality
- [ ] No audio glitches
- [ ] Smooth performance
- [ ] Proper error handling
- [ ] Well-documented code

---

## Future Enhancements (Post-MVP)

1. **Multi-crew Communications**
   - Intercom system
   - Pilot/co-pilot split audio

2. **Recorded Real ATC**
   - Sample real ATC recordings
   - Trigger context-appropriate clips

3. **AI-Driven ATC**
   - GPT-based responses
   - Natural language understanding
   - Adaptive to player actions

4. **Multiplayer ATC**
   - Human ATC controllers
   - Shared radio frequencies
   - Realistic traffic

5. **Advanced Weather Integration**
   - ATIS updates with changing weather
   - SIGMET/AIRMET broadcasts
   - Severe weather advisories

---

## Resources & References

### Aviation Radio Phraseology
- ICAO Annex 10 (Aeronautical Telecommunications)
- FAA ATC Manual (7110.65)
- Pilot/Controller Glossary
- Say Again, Please (book)

### Technical References
- VHF propagation characteristics
- Radio frequency allocation charts
- Airport/Facility Directory

### Audio Resources
- LiveATC.net (real ATC recordings)
- Aviation voice actor samples
- TTS voice selection guides

---

## Notes

- Keep audio files under 500ms each for quick assembly
- Use 44.1kHz sample rate for quality
- Normalize all audio to -3dB to prevent clipping
- Add 50ms silence at start/end of each file for smooth transitions
- Use MP3 or OGG format for space efficiency
- Cache assembled messages for performance
