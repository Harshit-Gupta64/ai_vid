#!/usr/bin/env bash
# render_short.sh - Compiles 5-scene vertical short with FFmpeg and auto-ducking BGM

set -euo pipefail

# Default argument values
STORYBOARD="state/storyboard.json"
AUDIO="assets/audio/voiceover.wav"
TIMESTAMPS="assets/audio/timestamps.json"
FRAMES_DIR="assets/frames"
BGM="assets/bgm/soundtrack.wav"
OUTPUT="out/final_short.mp4"

# Parse CLI arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --storyboard)
      STORYBOARD="$2"
      shift 2
      ;;
    --audio)
      AUDIO="$2"
      shift 2
      ;;
    --timestamps)
      TIMESTAMPS="$2"
      shift 2
      ;;
    --frames-dir)
      FRAMES_DIR="$2"
      shift 2
      ;;
    --bgm)
      BGM="$2"
      shift 2
      ;;
    --output)
      OUTPUT="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: $0 [--storyboard PATH] [--audio PATH] [--timestamps PATH] [--frames-dir PATH] [--bgm PATH] [--output PATH]"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1"
      exit 1
      ;;
  esac
done

echo "=========================================================="
echo " Tactical History Short-Form Video Compiler (FFmpeg/Remotion)"
echo "=========================================================="
echo "Storyboard: $STORYBOARD"
echo "Voiceover:  $AUDIO"
echo "Frames:     $FRAMES_DIR"
echo "Output:     $OUTPUT"

mkdir -p "$(dirname "$OUTPUT")"
mkdir -p "$(dirname "$BGM")"

# Check dependencies
if ! command -v ffmpeg &> /dev/null; then
  echo "[WARN] ffmpeg executable not found in PATH."
  echo "[INFO] Running Python cross-platform renderer fallback..."
  python "$(dirname "$0")/render_short.py" --storyboard "$STORYBOARD" --audio "$AUDIO" --timestamps "$TIMESTAMPS" --frames-dir "$FRAMES_DIR" --bgm "$BGM" --output "$OUTPUT"
  exit 0
fi

# Generate ambient war drone BGM if not present
if [ ! -f "$BGM" ]; then
  echo "[INFO] Generating atmospheric ambient war drone BGM at $BGM..."
  ffmpeg -y -f lavfi -i "anoisesrc=c=pink:r=44100:a=0.08" -f lavfi -i "sine=frequency=55:duration=60" \
    -filter_complex "[0:a]lowpass=f=250[pink];[1:a]volume=0.4[sub];[pink][sub]amix=inputs=2[bgm_out]" \
    -map "[bgm_out]" -t 50 "$BGM" 2>/dev/null || true
fi

# Execute Python video compilation engine which dynamically builds the complex filter graph
python "$(dirname "$0")/render_short.py" \
  --storyboard "$STORYBOARD" \
  --audio "$AUDIO" \
  --timestamps "$TIMESTAMPS" \
  --frames-dir "$FRAMES_DIR" \
  --bgm "$BGM" \
  --output "$OUTPUT"

echo "[SUCCESS] Final Short compiled: $OUTPUT"
