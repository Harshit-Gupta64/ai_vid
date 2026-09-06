#!/usr/bin/env python3
"""
verify_video.py - Short-Form Video Quality & Specification Validator

Performs 4 hard assertions on rendered videos:
1. Duration Check: Video duration matches storyboard target duration (within ±2 seconds).
2. Dual Stream Presence: Exactly 1 video stream (h264, 1080x1920, yuv420p) and 1 audio stream (aac, mono or stereo).
3. Multi-Scene Cut Verification: Midpoint frame hashes across adjacent scenes differ (anti-freeze check).
4. Dialogue Audio Presence: Audio volume is non-silent with mean volume > -35 dB (anti-silent voiceover check).
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def find_binaries():
    """Locates ffmpeg and ffprobe binaries."""
    ffmpeg_bin = shutil.which("ffmpeg")
    ffprobe_bin = shutil.which("ffprobe")

    if not ffmpeg_bin:
        try:
            import imageio_ffmpeg
            ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ffmpeg_bin = None

    if not ffprobe_bin and ffmpeg_bin:
        candidate = Path(ffmpeg_bin).parent / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
        if candidate.exists():
            ffprobe_bin = str(candidate)

    return ffmpeg_bin, ffprobe_bin


def get_media_info(video_path: Path, ffmpeg_bin: str, ffprobe_bin: str | None):
    """
    Extracts stream information and duration using ffprobe if available,
    or falls back to parsing ffmpeg -i output.
    """
    if ffprobe_bin:
        cmd = [
            ffprobe_bin,
            "-v", "error",
            "-show_entries", "stream=index,codec_name,codec_type,width,height,pix_fmt,channels",
            "-show_entries", "format=duration",
            "-of", "json",
            str(video_path.resolve())
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            try:
                data = json.loads(res.stdout)
                duration = float(data.get("format", {}).get("duration", 0.0))
                streams = data.get("streams", [])
                video_streams = [s for s in streams if s.get("codec_type") == "video"]
                audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
                return {
                    "duration": duration,
                    "video_streams": [
                        {
                            "codec": s.get("codec_name", "").lower(),
                            "width": s.get("width", 0),
                            "height": s.get("height", 0),
                            "pix_fmt": s.get("pix_fmt", "").lower()
                        }
                        for s in video_streams
                    ],
                    "audio_streams": [
                        {
                            "codec": s.get("codec_name", "").lower(),
                            "channels": s.get("channels", 0)
                        }
                        for s in audio_streams
                    ]
                }
            except Exception:
                pass

    # Fallback to ffmpeg -i parsing
    res = subprocess.run([ffmpeg_bin, "-i", str(video_path.resolve())], capture_output=True, text=True)
    stderr = res.stderr

    duration = 0.0
    dur_match = re.search(r"Duration:\s*(\d+):(\d+):([\d\.]+)", stderr)
    if dur_match:
        h, m, s = map(float, dur_match.groups())
        duration = h * 3600 + m * 60 + s

    video_streams = []
    audio_streams = []

    for line in stderr.splitlines():
        if "Stream #" in line:
            if ": Video:" in line:
                codec_m = re.search(r": Video:\s*([a-zA-Z0-9_-]+)", line)
                codec = codec_m.group(1).lower() if codec_m else ""
                dim_m = re.search(r",\s*(\d{2,5})x(\d{2,5})", line)
                w, h = (int(dim_m.group(1)), int(dim_m.group(2))) if dim_m else (0, 0)
                pix_m = re.search(r",\s*([a-zA-Z0-9_]+)(?:\([^\)]*\))?,\s*\d+x\d+", line)
                pix_fmt = pix_m.group(1).lower() if pix_m else ""
                video_streams.append({"codec": codec, "width": w, "height": h, "pix_fmt": pix_fmt})
            elif ": Audio:" in line:
                codec_m = re.search(r": Audio:\s*([a-zA-Z0-9_-]+)", line)
                codec = codec_m.group(1).lower() if codec_m else ""
                channels = 0
                if "mono" in line:
                    channels = 1
                elif "stereo" in line:
                    channels = 2
                else:
                    ch_m = re.search(r"(\d+)\s*channels", line)
                    if ch_m:
                        channels = int(ch_m.group(1))
                audio_streams.append({"codec": codec, "channels": channels})

    return {
        "duration": duration,
        "video_streams": video_streams,
        "audio_streams": audio_streams
    }


def verify_duration(actual_duration: float, storyboard: dict) -> bool:
    """Assertion 1: Duration Check (within +/- 2 seconds of target)."""
    target_duration = float(storyboard.get("target_duration_seconds", 0.0))
    if target_duration <= 0:
        scenes = storyboard.get("scenes", [])
        target_duration = sum(float(s.get("target_duration", 0.0)) for s in scenes)

    if target_duration <= 0:
        print("ERROR: Storyboard does not specify a valid target duration.", file=sys.stderr)
        return False

    diff = abs(actual_duration - target_duration)
    if diff > 2.0:
        print(
            f"ERROR: Duration check failed: Video duration ({actual_duration:.2f}s) "
            f"deviates from storyboard target ({target_duration:.2f}s) by {diff:.2f}s (tolerance: +/-2.0s).",
            file=sys.stderr
        )
        return False

    print(f"[PASS] Duration Check: {actual_duration:.2f}s (Target: {target_duration:.2f}s +/-2s, diff: {diff:.2f}s)")
    return True


def verify_streams(media_info: dict) -> bool:
    """Assertion 2: Dual Stream Presence (1 video: h264/1080x1920/yuv420p, 1 audio: aac/mono or stereo)."""
    v_streams = media_info.get("video_streams", [])
    a_streams = media_info.get("audio_streams", [])

    if len(v_streams) != 1:
        print(f"ERROR: Expected exactly 1 video stream, found {len(v_streams)}.", file=sys.stderr)
        return False

    v = v_streams[0]
    codec = v["codec"]
    w, h = v["width"], v["height"]
    pix_fmt = v["pix_fmt"]

    if codec not in ["h264", "avc1"]:
        print(f"ERROR: Video stream codec must be h264 (found '{codec}').", file=sys.stderr)
        return False

    if (w, h) != (1080, 1920):
        print(f"ERROR: Video resolution must be 1080x1920 (found {w}x{h}).", file=sys.stderr)
        return False

    if not (pix_fmt == "yuv420p" or pix_fmt.startswith("yuv420p") or pix_fmt.startswith("yuvj420p")):
        print(f"ERROR: Video pixel format must be yuv420p (found '{pix_fmt}').", file=sys.stderr)
        return False

    if len(a_streams) != 1:
        print(f"ERROR: Expected exactly 1 audio stream, found {len(a_streams)}.", file=sys.stderr)
        return False

    a = a_streams[0]
    a_codec = a["codec"]
    channels = a["channels"]

    if a_codec not in ["aac", "mp4a"]:
        print(f"ERROR: Audio stream codec must be aac (found '{a_codec}').", file=sys.stderr)
        return False

    if channels not in [1, 2]:
        print(f"ERROR: Audio stream must be mono (1-channel) or stereo (2-channel), found {channels} channels.", file=sys.stderr)
        return False

    print(f"[PASS] Dual Stream Presence: 1 video stream ({codec}, {w}x{h}, {pix_fmt}) & 1 audio stream ({a_codec}, {channels}ch)")
    return True


def verify_scene_cuts(video_path: Path, storyboard: dict, ffmpeg_bin: str) -> bool:
    """Assertion 3: Multi-Scene Cut Verification (Anti-Freeze Check)."""
    scenes = storyboard.get("scenes", [])
    if not scenes:
        print("[ERROR] No scenes defined in storyboard.", file=sys.stderr)
        return False

    # Calculate midpoint timecode for each scene
    midpoints = []
    current_time = 0.0

    for idx, scene in enumerate(scenes):
        time_range = scene.get("time_range")
        if time_range and "-" in time_range:
            try:
                parts = time_range.split("-")
                s_start = float(parts[0])
                s_end = float(parts[1])
                midpoint = (s_start + s_end) / 2.0
            except ValueError:
                dur = float(scene.get("target_duration", 5.0))
                midpoint = current_time + dur / 2.0
                current_time += dur
        elif "start_time" in scene and "end_time" in scene:
            midpoint = (float(scene["start_time"]) + float(scene["end_time"])) / 2.0
        else:
            dur = float(scene.get("target_duration", 5.0))
            midpoint = current_time + dur / 2.0
            current_time += dur

        midpoints.append((idx + 1, midpoint))

    # Extract 1 frame at midpoint of each scene and hash it
    hashes = []
    for scene_id, t_mid in midpoints:
        cmd = [
            ffmpeg_bin,
            "-ss", str(t_mid),
            "-i", str(video_path.resolve()),
            "-vframes", "1",
            "-f", "image2pipe",
            "-vcodec", "png",
            "-"
        ]
        res = subprocess.run(cmd, capture_output=True)
        if res.returncode != 0 or not res.stdout:
            print(f"[ERROR] Failed to extract frame at {t_mid:.2f}s for Scene {scene_id}.", file=sys.stderr)
            return False

        frame_hash = hashlib.md5(res.stdout).hexdigest()
        hashes.append((scene_id, t_mid, frame_hash))

    # Compare adjacent scene frame hashes
    for i in range(len(hashes) - 1):
        sc_a, t_a, h_a = hashes[i]
        sc_b, t_b, h_b = hashes[i + 1]
        if h_a == h_b:
            print("ERROR: Video is frozen on a single image across all scenes.", file=sys.stderr)
            return False

    print(f"[PASS] Multi-Scene Cut Verification: {len(hashes)} scenes extracted at midpoints; all adjacent hashes unique.")
    return True


def verify_dialogue_audio(video_path: Path, ffmpeg_bin: str) -> bool:
    """Assertion 4: Dialogue Audio Presence (Anti-Silent Voiceover Check: mean volume > -35 dB)."""
    cmd = [
        ffmpeg_bin,
        "-i", str(video_path.resolve()),
        "-vn",
        "-af", "volumedetect",
        "-f", "null",
        "-"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print("[ERROR] FFmpeg volumedetect execution failed.", file=sys.stderr)
        return False

    stderr = res.stderr
    mean_vol_match = re.search(r"mean_volume:\s*(-?[\d\.]+)\s*dB", stderr)
    if not mean_vol_match:
        print("ERROR: Voiceover track is missing or muted.", file=sys.stderr)
        return False

    mean_vol = float(mean_vol_match.group(1))
    if mean_vol <= -35.0:
        print("ERROR: Voiceover track is missing or muted.", file=sys.stderr)
        return False

    print(f"[PASS] Dialogue Audio Presence: Mean volume {mean_vol:.1f} dB (> -35.0 dB threshold)")
    return True


def main():
    parser = argparse.ArgumentParser(description="Short-Form Video Quality & Spec Validator")
    parser.add_argument("--video", type=str, required=True, help="Path to input video MP4 file.")
    parser.add_argument("--storyboard", type=str, required=True, help="Path to storyboard JSON file.")

    args = parser.parse_args()

    video_path = Path(args.video)
    storyboard_path = Path(args.storyboard)

    if not video_path.exists():
        print(f"ERROR: Video file '{video_path.resolve()}' does not exist.", file=sys.stderr)
        sys.exit(1)

    if not storyboard_path.exists():
        print(f"ERROR: Storyboard file '{storyboard_path.resolve()}' does not exist.", file=sys.stderr)
        sys.exit(1)

    try:
        with open(storyboard_path, "r", encoding="utf-8") as f:
            storyboard = json.load(f)
    except Exception as e:
        print(f"ERROR: Failed to parse storyboard JSON: {e}", file=sys.stderr)
        sys.exit(1)

    ffmpeg_bin, ffprobe_bin = find_binaries()
    if not ffmpeg_bin:
        print("ERROR: FFmpeg binary not found in PATH or Python environment.", file=sys.stderr)
        sys.exit(1)

    print(f"=== Starting Video Quality Verification ===")
    print(f"Video: {video_path.resolve()}")
    print(f"Storyboard: {storyboard_path.resolve()}\n")

    media_info = get_media_info(video_path, ffmpeg_bin, ffprobe_bin)

    # Assertion 1: Duration Check
    if not verify_duration(media_info["duration"], storyboard):
        sys.exit(1)

    # Assertion 2: Dual Stream Presence
    if not verify_streams(media_info):
        sys.exit(1)

    # Assertion 3: Multi-Scene Cut Verification (Anti-Freeze Check)
    if not verify_scene_cuts(video_path, storyboard, ffmpeg_bin):
        sys.exit(1)

    # Assertion 4: Dialogue Audio Presence (Anti-Silent Voiceover Check)
    if not verify_dialogue_audio(video_path, ffmpeg_bin):
        sys.exit(1)

    print("\n[SUCCESS] All video verification assertions passed successfully.")
    sys.exit(0)


if __name__ == "__main__":
    main()
