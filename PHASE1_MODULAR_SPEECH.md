# Phase 1: Modular Speech System (Audio-Only)

## Goal
Implement phonetic alphabet speech components to build realistic ATC callsigns and messages, leveraging the existing AudioSpeechProvider system.

---

## Overview: Existing System

### ✅ What We Have:
- `AudioSpeechProvider`: Plays pre-recorded WAV/OGG files
- Multiple voices configured: `pilot`, `cockpit`, `ground`, `tower`, `approach`, `atis`
- TTS generation using macOS `say` command
- Message mapping in `config/speech.yaml`
- Individual digits (0-9) already available
- Sequential playback queue for chaining messages

### 🔧 What We Need:
- Phonetic alphabet files (ALPHA → ZULU)
- Aviation-specific numbers (NINER, HUNDRED, THOUSAND, DECIMAL)
- CallsignBuilder to assemble N123AB → "November One Two Three Alpha Bravo"
- Keyboard controls for radio tuning (audio-only, no visual UI)
- Audio feedback for frequency changes

---

## Task 1: Generate Phonetic Alphabet Audio Files

### File List (26 files)
```
data/speech/en/atc/phonetic/
├── ALPHA.wav
├── BRAVO.wav
├── CHARLIE.wav
├── DELTA.wav
├── ECHO.wav
├── FOXTROT.wav
├── GOLF.wav
├── HOTEL.wav
├── INDIA.wav
├── JULIETT.wav      # Note: Two T's in ICAO spelling
├── KILO.wav
├── LIMA.wav
├── MIKE.wav
├── NOVEMBER.wav
├── OSCAR.wav
├── PAPA.wav
├── QUEBEC.wav
├── ROMEO.wav
├── SIERRA.wav
├── TANGO.wav
├── UNIFORM.wav
├── VICTOR.wav
├── WHISKEY.wav
├── XRAY.wav
├── YANKEE.wav
└── ZULU.wav
```

### Generation Script
```bash
#!/bin/bash
# generate_phonetic.sh

VOICE="Evan"  # Same as ATC voices
RATE=180
OUTPUT_DIR="data/speech/en/atc/phonetic"

mkdir -p "$OUTPUT_DIR"

declare -a PHONETIC=(
  "ALPHA" "BRAVO" "CHARLIE" "DELTA" "ECHO" "FOXTROT"
  "GOLF" "HOTEL" "INDIA" "JULIETT" "KILO" "LIMA"
  "MIKE" "NOVEMBER" "OSCAR" "PAPA" "QUEBEC" "ROMEO"
  "SIERRA" "TANGO" "UNIFORM" "VICTOR" "WHISKEY"
  "XRAY" "YANKEE" "ZULU"
)

for word in "${PHONETIC[@]}"; do
  echo "Generating $word..."
  say -v "$VOICE" -r "$RATE" -o "$OUTPUT_DIR/$word.wav" "$word"
done

echo "✓ Generated 26 phonetic alphabet files"
```

---

## Task 2: Generate Aviation Number Files

### File List
```
data/speech/en/atc/numbers/
├── NINER.wav          # Special aviation pronunciation for "9"
├── HUNDRED.wav
├── THOUSAND.wav
├── DECIMAL.wav
└── POINT.wav
```

Note: Digits 0-8 already exist as MSG_DIGIT_0 through MSG_DIGIT_8

### Generation Script
```bash
#!/bin/bash
# generate_aviation_numbers.sh

VOICE="Evan"
RATE=180
OUTPUT_DIR="data/speech/en/atc/numbers"

mkdir -p "$OUTPUT_DIR"

# Aviation-specific pronunciations
say -v "$VOICE" -r "$RATE" -o "$OUTPUT_DIR/NINER.wav" "niner"
say -v "$VOICE" -r "$RATE" -o "$OUTPUT_DIR/HUNDRED.wav" "hundred"
say -v "$VOICE" -r "$RATE" -o "$OUTPUT_DIR/THOUSAND.wav" "thousand"
say -v "$VOICE" -r "$RATE" -o "$OUTPUT_DIR/DECIMAL.wav" "decimal"
say -v "$VOICE" -r "$RATE" -o "$OUTPUT_DIR/POINT.wav" "point"

echo "✓ Generated 5 aviation number files"
```

---

## Task 3: Update speech.yaml Configuration

### Add to `config/speech.yaml`:

```yaml
messages:
  # ... existing messages ...

  # Phonetic Alphabet
  MSG_PHONETIC_ALPHA:
    text: "ALPHA"
    voice: tower
  MSG_PHONETIC_BRAVO:
    text: "BRAVO"
    voice: tower
  MSG_PHONETIC_CHARLIE:
    text: "CHARLIE"
    voice: tower
  MSG_PHONETIC_DELTA:
    text: "DELTA"
    voice: tower
  MSG_PHONETIC_ECHO:
    text: "ECHO"
    voice: tower
  MSG_PHONETIC_FOXTROT:
    text: "FOXTROT"
    voice: tower
  MSG_PHONETIC_GOLF:
    text: "GOLF"
    voice: tower
  MSG_PHONETIC_HOTEL:
    text: "HOTEL"
    voice: tower
  MSG_PHONETIC_INDIA:
    text: "INDIA"
    voice: tower
  MSG_PHONETIC_JULIETT:
    text: "JULIETT"
    voice: tower
  MSG_PHONETIC_KILO:
    text: "KILO"
    voice: tower
  MSG_PHONETIC_LIMA:
    text: "LIMA"
    voice: tower
  MSG_PHONETIC_MIKE:
    text: "MIKE"
    voice: tower
  MSG_PHONETIC_NOVEMBER:
    text: "NOVEMBER"
    voice: tower
  MSG_PHONETIC_OSCAR:
    text: "OSCAR"
    voice: tower
  MSG_PHONETIC_PAPA:
    text: "PAPA"
    voice: tower
  MSG_PHONETIC_QUEBEC:
    text: "QUEBEC"
    voice: tower
  MSG_PHONETIC_ROMEO:
    text: "ROMEO"
    voice: tower
  MSG_PHONETIC_SIERRA:
    text: "SIERRA"
    voice: tower
  MSG_PHONETIC_TANGO:
    text: "TANGO"
    voice: tower
  MSG_PHONETIC_UNIFORM:
    text: "UNIFORM"
    voice: tower
  MSG_PHONETIC_VICTOR:
    text: "VICTOR"
    voice: tower
  MSG_PHONETIC_WHISKEY:
    text: "WHISKEY"
    voice: tower
  MSG_PHONETIC_XRAY:
    text: "XRAY"
    voice: tower
  MSG_PHONETIC_YANKEE:
    text: "YANKEE"
    voice: tower
  MSG_PHONETIC_ZULU:
    text: "ZULU"
    voice: tower

  # Aviation Numbers
  MSG_NUMBER_NINER:
    text: "NINER"
    voice: tower
  MSG_NUMBER_HUNDRED:
    text: "HUNDRED"
    voice: tower
  MSG_NUMBER_THOUSAND:
    text: "THOUSAND"
    voice: tower
  MSG_WORD_DECIMAL:
    text: "DECIMAL"
    voice: tower
  MSG_WORD_POINT:
    text: "POINT"
    voice: tower
```

---

## Task 4: Add Message Keys to speech_messages.py

### Add to `src/airborne/audio/tts/speech_messages.py`:

```python
class SpeechMessages:
    # ... existing messages ...

    # Phonetic Alphabet
    MSG_PHONETIC_ALPHA = "MSG_PHONETIC_ALPHA"
    MSG_PHONETIC_BRAVO = "MSG_PHONETIC_BRAVO"
    MSG_PHONETIC_CHARLIE = "MSG_PHONETIC_CHARLIE"
    MSG_PHONETIC_DELTA = "MSG_PHONETIC_DELTA"
    MSG_PHONETIC_ECHO = "MSG_PHONETIC_ECHO"
    MSG_PHONETIC_FOXTROT = "MSG_PHONETIC_FOXTROT"
    MSG_PHONETIC_GOLF = "MSG_PHONETIC_GOLF"
    MSG_PHONETIC_HOTEL = "MSG_PHONETIC_HOTEL"
    MSG_PHONETIC_INDIA = "MSG_PHONETIC_INDIA"
    MSG_PHONETIC_JULIETT = "MSG_PHONETIC_JULIETT"
    MSG_PHONETIC_KILO = "MSG_PHONETIC_KILO"
    MSG_PHONETIC_LIMA = "MSG_PHONETIC_LIMA"
    MSG_PHONETIC_MIKE = "MSG_PHONETIC_MIKE"
    MSG_PHONETIC_NOVEMBER = "MSG_PHONETIC_NOVEMBER"
    MSG_PHONETIC_OSCAR = "MSG_PHONETIC_OSCAR"
    MSG_PHONETIC_PAPA = "MSG_PHONETIC_PAPA"
    MSG_PHONETIC_QUEBEC = "MSG_PHONETIC_QUEBEC"
    MSG_PHONETIC_ROMEO = "MSG_PHONETIC_ROMEO"
    MSG_PHONETIC_SIERRA = "MSG_PHONETIC_SIERRA"
    MSG_PHONETIC_TANGO = "MSG_PHONETIC_TANGO"
    MSG_PHONETIC_UNIFORM = "MSG_PHONETIC_UNIFORM"
    MSG_PHONETIC_VICTOR = "MSG_PHONETIC_VICTOR"
    MSG_PHONETIC_WHISKEY = "MSG_PHONETIC_WHISKEY"
    MSG_PHONETIC_XRAY = "MSG_PHONETIC_XRAY"
    MSG_PHONETIC_YANKEE = "MSG_PHONETIC_YANKEE"
    MSG_PHONETIC_ZULU = "MSG_PHONETIC_ZULU"

    # Aviation Numbers
    MSG_NUMBER_NINER = "MSG_NUMBER_NINER"
    MSG_NUMBER_HUNDRED = "MSG_NUMBER_HUNDRED"
    MSG_NUMBER_THOUSAND = "MSG_NUMBER_THOUSAND"
    MSG_WORD_DECIMAL = "MSG_WORD_DECIMAL"
    MSG_WORD_POINT = "MSG_WORD_POINT"
```

---

## Task 5: Create CallsignBuilder

### New File: `src/airborne/plugins/radio/callsign_builder.py`

```python
"""Callsign builder for aviation phonetic alphabet.

Converts callsigns to phonetic pronunciation using the existing speech system.
"""

from airborne.audio.tts.speech_messages import SpeechMessages


class CallsignBuilder:
    """Build phonetic callsigns from registration numbers.

    Examples:
        >>> builder = CallsignBuilder()
        >>> builder.build_callsign("N123AB")
        ['MSG_PHONETIC_NOVEMBER', 'MSG_DIGIT_1', 'MSG_DIGIT_2',
         'MSG_DIGIT_3', 'MSG_PHONETIC_ALPHA', 'MSG_PHONETIC_BRAVO']
    """

    # Phonetic alphabet mapping
    PHONETIC_MAP = {
        'A': SpeechMessages.MSG_PHONETIC_ALPHA,
        'B': SpeechMessages.MSG_PHONETIC_BRAVO,
        'C': SpeechMessages.MSG_PHONETIC_CHARLIE,
        'D': SpeechMessages.MSG_PHONETIC_DELTA,
        'E': SpeechMessages.MSG_PHONETIC_ECHO,
        'F': SpeechMessages.MSG_PHONETIC_FOXTROT,
        'G': SpeechMessages.MSG_PHONETIC_GOLF,
        'H': SpeechMessages.MSG_PHONETIC_HOTEL,
        'I': SpeechMessages.MSG_PHONETIC_INDIA,
        'J': SpeechMessages.MSG_PHONETIC_JULIETT,
        'K': SpeechMessages.MSG_PHONETIC_KILO,
        'L': SpeechMessages.MSG_PHONETIC_LIMA,
        'M': SpeechMessages.MSG_PHONETIC_MIKE,
        'N': SpeechMessages.MSG_PHONETIC_NOVEMBER,
        'O': SpeechMessages.MSG_PHONETIC_OSCAR,
        'P': SpeechMessages.MSG_PHONETIC_PAPA,
        'Q': SpeechMessages.MSG_PHONETIC_QUEBEC,
        'R': SpeechMessages.MSG_PHONETIC_ROMEO,
        'S': SpeechMessages.MSG_PHONETIC_SIERRA,
        'T': SpeechMessages.MSG_PHONETIC_TANGO,
        'U': SpeechMessages.MSG_PHONETIC_UNIFORM,
        'V': SpeechMessages.MSG_PHONETIC_VICTOR,
        'W': SpeechMessages.MSG_PHONETIC_WHISKEY,
        'X': SpeechMessages.MSG_PHONETIC_XRAY,
        'Y': SpeechMessages.MSG_PHONETIC_YANKEE,
        'Z': SpeechMessages.MSG_PHONETIC_ZULU,
    }

    # Digit mapping (using existing digit messages)
    DIGIT_MAP = {
        '0': SpeechMessages.MSG_DIGIT_0,
        '1': SpeechMessages.MSG_DIGIT_1,
        '2': SpeechMessages.MSG_DIGIT_2,
        '3': SpeechMessages.MSG_DIGIT_3,
        '4': SpeechMessages.MSG_DIGIT_4,
        '5': SpeechMessages.MSG_DIGIT_5,
        '6': SpeechMessages.MSG_DIGIT_6,
        '7': SpeechMessages.MSG_DIGIT_7,
        '8': SpeechMessages.MSG_DIGIT_8,
        '9': SpeechMessages.MSG_NUMBER_NINER,  # Aviation pronunciation
    }

    def build_callsign(self, callsign: str) -> list[str]:
        """Convert callsign to list of speech message keys.

        Args:
            callsign: Aircraft callsign (e.g., "N123AB")

        Returns:
            List of message keys for sequential playback.

        Examples:
            >>> builder.build_callsign("N123AB")
            ['MSG_PHONETIC_NOVEMBER', 'MSG_DIGIT_1', ...]
        """
        messages = []
        callsign = callsign.upper().strip()

        for char in callsign:
            if char in self.PHONETIC_MAP:
                messages.append(self.PHONETIC_MAP[char])
            elif char in self.DIGIT_MAP:
                messages.append(self.DIGIT_MAP[char])
            # Skip spaces and hyphens

        return messages

    def build_frequency(self, frequency: float) -> list[str]:
        """Convert frequency to speech message keys.

        Args:
            frequency: Radio frequency in MHz (e.g., 121.5)

        Returns:
            List of message keys.

        Examples:
            >>> builder.build_frequency(121.5)
            ['MSG_DIGIT_1', 'MSG_DIGIT_2', 'MSG_DIGIT_1',
             'MSG_WORD_DECIMAL', 'MSG_DIGIT_5']
        """
        messages = []
        freq_str = f"{frequency:.3f}"  # Format to 3 decimal places

        for char in freq_str:
            if char == '.':
                messages.append(SpeechMessages.MSG_WORD_DECIMAL)
            elif char in self.DIGIT_MAP:
                messages.append(self.DIGIT_MAP[char])

        return messages

    def build_altitude(self, altitude: int) -> list[str]:
        """Convert altitude to speech message keys.

        Aviation altitude is read in hundreds/thousands.

        Args:
            altitude: Altitude in feet (e.g., 2500)

        Returns:
            List of message keys.

        Examples:
            >>> builder.build_altitude(2500)
            ['MSG_DIGIT_2', 'MSG_NUMBER_THOUSAND',
             'MSG_DIGIT_5', 'MSG_NUMBER_HUNDRED']
        """
        messages = []

        if altitude >= 1000:
            thousands = altitude // 1000
            messages.append(self.DIGIT_MAP[str(thousands)])
            messages.append(SpeechMessages.MSG_NUMBER_THOUSAND)
            altitude = altitude % 1000

        if altitude >= 100:
            hundreds = altitude // 100
            messages.append(self.DIGIT_MAP[str(hundreds)])
            messages.append(SpeechMessages.MSG_NUMBER_HUNDRED)

        return messages
```

---

## Task 6: Keyboard Controls for Radio Tuning (Audio-Only)

### Enhancement to `src/airborne/core/input.py`

Add keyboard shortcuts for radio control:

```python
# Radio tuning controls
'f12': 'radio_com1_tune_up',       # Increase COM1 frequency
'shift+f12': 'radio_com1_tune_down',  # Decrease COM1 frequency
'ctrl+f12': 'radio_com1_swap',     # Swap active/standby
'alt+f12': 'radio_com1_read',      # Read current frequency

'f11': 'radio_com2_tune_up',
'shift+f11': 'radio_com2_tune_down',
'ctrl+f11': 'radio_com2_swap',
'alt+f11': 'radio_com2_read',
```

### Audio Feedback

When tuning:
1. **Beep**: Short beep on each frequency step
2. **Voice**: Speak frequency every 5 steps or on key release
3. **Confirmation**: "COM1 active one two one decimal five"

---

## Task 7: Frequency Announcer

### New File: `src/airborne/plugins/radio/frequency_announcer.py`

```python
"""Frequency announcement for audio-only radio interface."""

from airborne.plugins.radio.callsign_builder import CallsignBuilder


class FrequencyAnnouncer:
    """Announces radio frequencies via cockpit voice.

    Provides audio feedback for frequency changes in audio-only interface.
    """

    def __init__(self, tts_provider, callsign_builder: CallsignBuilder):
        """Initialize frequency announcer.

        Args:
            tts_provider: AudioSpeechProvider instance.
            callsign_builder: CallsignBuilder for number pronunciation.
        """
        self.tts = tts_provider
        self.builder = callsign_builder

    def announce_com1_active(self, frequency: float):
        """Announce COM1 active frequency.

        Args:
            frequency: Frequency in MHz.

        Audio output:
            "COM one active one two one decimal five"
        """
        messages = [
            "MSG_WORD_COM",           # Need to add
            "MSG_DIGIT_1",
            "MSG_WORD_ACTIVE",        # Need to add
        ]
        messages.extend(self.builder.build_frequency(frequency))

        for msg in messages:
            self.tts.speak(msg)

    def announce_com1_standby(self, frequency: float):
        """Announce COM1 standby frequency."""
        messages = [
            "MSG_WORD_COM",
            "MSG_DIGIT_1",
            "MSG_WORD_STANDBY",       # Need to add
        ]
        messages.extend(self.builder.build_frequency(frequency))

        for msg in messages:
            self.tts.speak(msg)

    def announce_swap(self, radio: str):
        """Announce frequency swap.

        Args:
            radio: "COM1" or "COM2"

        Audio output:
            "COM one swapped"
        """
        messages = [
            "MSG_WORD_COM",
            "MSG_DIGIT_1" if radio == "COM1" else "MSG_DIGIT_2",
            "MSG_WORD_SWAPPED",       # Need to add
        ]

        for msg in messages:
            self.tts.speak(msg)
```

---

## Additional Required Words

Add to speech.yaml and speech_messages.py:

```yaml
MSG_WORD_COM:
  text: "COM"
  voice: cockpit
MSG_WORD_ACTIVE:
  text: "active"
  voice: cockpit
MSG_WORD_STANDBY:
  text: "standby"
  voice: cockpit
MSG_WORD_SWAPPED:
  text: "swapped"
  voice: cockpit
MSG_WORD_FREQUENCY:
  text: "frequency"
  voice: cockpit
```

---

## Testing Plan

### Test 1: Phonetic Alphabet Playback
```python
# Test individual letters
tts.speak("MSG_PHONETIC_ALPHA")   # Should say "ALPHA"
tts.speak("MSG_PHONETIC_BRAVO")   # Should say "BRAVO"
```

### Test 2: Callsign Assembly
```python
builder = CallsignBuilder()
messages = builder.build_callsign("N123AB")
for msg in messages:
    tts.speak(msg)
# Should say: "November One Two Three Alpha Bravo"
```

### Test 3: Frequency Announcement
```python
messages = builder.build_frequency(121.5)
for msg in messages:
    tts.speak(msg)
# Should say: "One Two One Decimal Five"
```

### Test 4: Altitude Announcement
```python
messages = builder.build_altitude(2500)
for msg in messages:
    tts.speak(msg)
# Should say: "Two Thousand Five Hundred"
```

### Test 5: Keyboard Controls
```
Press F12: Frequency increases, beep plays
Hold F12: Frequency continues increasing
Release F12: "COM one active one two one decimal seven"
Press Alt+F12: "COM one active one two one decimal seven"
```

---

## Success Criteria

- [ ] All 26 phonetic alphabet files generated and playing correctly
- [ ] Aviation numbers (NINER, HUNDRED, THOUSAND) working
- [ ] CallsignBuilder correctly converts "N123AB"
- [ ] Frequency announcements are clear and accurate
- [ ] Keyboard controls work smoothly with audio feedback
- [ ] No stuttering or audio glitches in playback
- [ ] Seamless integration with existing AudioSpeechProvider

---

## Implementation Order

1. ✅ Generate phonetic alphabet WAV files (script)
2. ✅ Generate aviation number WAV files (script)
3. ✅ Update speech.yaml configuration
4. ✅ Add message keys to speech_messages.py
5. ✅ Create CallsignBuilder class
6. ✅ Create FrequencyAnnouncer class
7. ✅ Add keyboard controls to input system
8. ✅ Test complete workflow
9. ✅ Document usage

---

## File Checklist

### Scripts to Create:
- [ ] `scripts/generate_phonetic.sh`
- [ ] `scripts/generate_aviation_numbers.sh`
- [ ] `scripts/generate_radio_words.sh`

### Code Files to Create:
- [ ] `src/airborne/plugins/radio/callsign_builder.py`
- [ ] `src/airborne/plugins/radio/frequency_announcer.py`

### Code Files to Modify:
- [ ] `src/airborne/audio/tts/speech_messages.py` (add constants)
- [ ] `config/speech.yaml` (add message mappings)
- [ ] `src/airborne/core/input.py` (add keyboard shortcuts)

### Audio Files to Generate:
- [ ] 26 phonetic alphabet WAV files
- [ ] 5 aviation number WAV files
- [ ] 4 radio word WAV files (COM, ACTIVE, STANDBY, SWAPPED)

---

## Next Steps (Phase 2)

After Phase 1 complete:
- Airport frequency database
- Distance-based audio degradation
- Realistic ATC phraseology assembly
- Frequency handoff system

This foundation enables all future ATC features!
