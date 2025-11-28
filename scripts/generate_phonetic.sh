#!/bin/bash
# Generate phonetic alphabet audio files for ATC callsigns
# Uses macOS 'say' command with Evan voice (same as ATC)

VOICE="Evan"
RATE=180
OUTPUT_DIR="data/speech/en/atc/phonetic"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# ICAO phonetic alphabet
declare -a PHONETIC=(
  "ALPHA" "BRAVO" "CHARLIE" "DELTA" "ECHO" "FOXTROT"
  "GOLF" "HOTEL" "INDIA" "JULIETT" "KILO" "LIMA"
  "MIKE" "NOVEMBER" "OSCAR" "PAPA" "QUEBEC" "ROMEO"
  "SIERRA" "TANGO" "UNIFORM" "VICTOR" "WHISKEY"
  "XRAY" "YANKEE" "ZULU"
)

echo "Generating phonetic alphabet audio files..."
echo "Voice: $VOICE | Rate: $RATE | Output: $OUTPUT_DIR"
echo ""

count=0
for word in "${PHONETIC[@]}"; do
  echo -n "Generating $word... "
  say -v "$VOICE" -r "$RATE" -o "$OUTPUT_DIR/$word.wav" "$word"

  if [ $? -eq 0 ]; then
    echo "✓"
    ((count++))
  else
    echo "✗ FAILED"
  fi
done

echo ""
echo "✓ Generated $count/26 phonetic alphabet files"
echo ""
echo "Output directory: $OUTPUT_DIR"
echo ""
echo "Test playback:"
echo "  afplay $OUTPUT_DIR/ALPHA.wav"
echo "  afplay $OUTPUT_DIR/NOVEMBER.wav"
