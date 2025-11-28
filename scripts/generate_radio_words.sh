#!/bin/bash
# Generate radio control vocabulary for audio feedback
# Uses macOS 'say' command with Samantha voice (cockpit computer)

VOICE="Samantha"
RATE=200
OUTPUT_DIR="data/speech/en/cockpit"

echo "Generating radio control vocabulary..."
echo "Voice: $VOICE | Rate: $RATE | Output: $OUTPUT_DIR"
echo ""

# Radio control words
declare -a WORDS=(
  "COM"
  "active"
  "standby"
  "swapped"
  "frequency"
  "tuned"
  "selected"
)

count=0
for word in "${WORDS[@]}"; do
  filename=$(echo "$word" | tr '[:lower:]' '[:upper:]')
  echo -n "Generating $filename... "
  say -v "$VOICE" -r "$RATE" -o "$OUTPUT_DIR/$filename.wav" "$word"

  if [ $? -eq 0 ]; then
    echo "✓"
    ((count++))
  else
    echo "✗ FAILED"
  fi
done

echo ""
echo "✓ Generated $count/${#WORDS[@]} radio control words"
echo ""
echo "Output directory: $OUTPUT_DIR"
echo ""
echo "Test playback:"
echo "  afplay $OUTPUT_DIR/COM.wav"
echo "  afplay $OUTPUT_DIR/ACTIVE.wav"
