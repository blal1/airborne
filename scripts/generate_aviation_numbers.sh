#!/bin/bash
# Generate aviation-specific number audio files
# Uses macOS 'say' command with Evan voice (same as ATC)

VOICE="Evan"
RATE=180
OUTPUT_DIR="data/speech/en/atc/numbers"

# Create output directory
mkdir -p "$OUTPUT_DIR"

echo "Generating aviation number audio files..."
echo "Voice: $VOICE | Rate: $RATE | Output: $OUTPUT_DIR"
echo ""

# Aviation-specific pronunciations
# Note: "niner" instead of "nine" is standard aviation pronunciation
echo -n "Generating NINER... "
say -v "$VOICE" -r "$RATE" -o "$OUTPUT_DIR/NINER.wav" "niner"
[ $? -eq 0 ] && echo "✓" || echo "✗"

echo -n "Generating HUNDRED... "
say -v "$VOICE" -r "$RATE" -o "$OUTPUT_DIR/HUNDRED.wav" "hundred"
[ $? -eq 0 ] && echo "✓" || echo "✗"

echo -n "Generating THOUSAND... "
say -v "$VOICE" -r "$RATE" -o "$OUTPUT_DIR/THOUSAND.wav" "thousand"
[ $? -eq 0 ] && echo "✓" || echo "✗"

echo -n "Generating DECIMAL... "
say -v "$VOICE" -r "$RATE" -o "$OUTPUT_DIR/DECIMAL.wav" "decimal"
[ $? -eq 0 ] && echo "✓" || echo "✗"

echo -n "Generating POINT... "
say -v "$VOICE" -r "$RATE" -o "$OUTPUT_DIR/POINT.wav" "point"
[ $? -eq 0 ] && echo "✓" || echo "✗"

echo ""
echo "✓ Generated 5 aviation number files"
echo ""
echo "Output directory: $OUTPUT_DIR"
echo ""
echo "Test playback:"
echo "  afplay $OUTPUT_DIR/NINER.wav"
echo "  afplay $OUTPUT_DIR/HUNDRED.wav"
