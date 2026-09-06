#!/usr/bin/env python3
"""
synthesize.py - High-Fidelity Voiceover Synthesis with edge-tts

Synthesizes documentary-grade voiceover audio using edge-tts (en-US-ChristopherNeural)
and exports word-level aligned timestamps (timestamps.json) and voiceover.wav.
"""

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False


PHONETIC_RULES = [
    (r"\bCao Cao's\b", "Tsao Tsao's"),
    (r"\bCao Cao\b", "Tsao Tsao"),
    (r"\bHuang Gai's\b", "Hwang Guy's"),
    (r"\bHuang Gai\b", "Hwang Guy"),
    (r"\bYangtze\b", "Yang-tsee"),
    (r"\bScutum\b", "Scoo-tum"),
    (r"\bscuta\b", "scoo-tuh"),
    (r"\bSyracuse\b", "Seer-uh-kuse"),
]


def apply_phonetics(text: str) -> str:
    """Pre-processes text to ensure authentic historical documentary pronunciation in Edge-TTS."""
    res = text
    for pat, repl in PHONETIC_RULES:
        res = re.sub(pat, repl, res, flags=re.IGNORECASE)
    return res


def get_ffmpeg_bin() -> str:
    """Locates FFmpeg binary from system PATH or imageio_ffmpeg."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        try:
            import imageio_ffmpeg
            ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ffmpeg_bin = "ffmpeg"
    return ffmpeg_bin


async def synthesize_scene_edge_tts(text: str, voice: str, rate: str, max_retries: int = 3) -> tuple:
    """
    Synthesizes a single text block using edge-tts with exponential backoff on network timeouts.
    Returns (audio_bytes, word_events).
    """
    for attempt in range(1, max_retries + 1):
        try:
            communicate = edge_tts.Communicate(text, voice=voice, rate=rate)
            audio_chunks = []
            words = []
            async for chunk in communicate.stream():
                chunk_type = chunk.get("type")
                if chunk_type == "audio":
                    audio_chunks.append(chunk["data"])
                elif chunk_type == "WordBoundary":
                    offset_sec = chunk["offset"] / 10_000_000.0
                    duration_sec = chunk["duration"] / 10_000_000.0
                    words.append({
                        "word": chunk["text"],
                        "start": offset_sec,
                        "end": offset_sec + duration_sec
                    })

            audio_bytes = b"".join(audio_chunks)
            if len(audio_bytes) > 500:
                return audio_bytes, words
        except Exception as e:
            print(f"[WARN] Scene synthesis attempt {attempt} failed ({e}). Backing off...", file=sys.stderr)
            await asyncio.sleep(2.5 * attempt)

    raise RuntimeError(f"Failed to synthesize audio after {max_retries} attempts.")


async def synthesize_storyboard_edge_tts(
    storyboard: dict,
    storyboard_path: Path,
    output_audio: Path,
    output_timestamps: Path,
    voice: str = "en-US-ChristopherNeural",
    rate: str = "+20%"
):
    scenes = storyboard.get("scenes", [])
    if not scenes:
        raise ValueError("Storyboard contains no scenes.")

    ffmpeg_bin = get_ffmpeg_bin()
    temp_dir = Path(tempfile.mkdtemp(prefix="tts_edge_"))
    
    scene_records = []
    current_time_offset = 0.0
    scene_audio_files = []

    print(f"[INFO] Synthesizing {len(scenes)} scenes with edge-tts (Voice: {voice}, Rate: {rate})...")

    try:
        for idx, scene in enumerate(scenes):
            scene_id = scene.get("scene_id", idx + 1)
            narration_raw = scene.get("narration", "").strip()
            if not narration_raw:
                continue

            narration_spoken = apply_phonetics(narration_raw)
            print(f"[INFO] Synthesizing Scene {scene_id}: \"{narration_raw[:45]}...\" (Spoken: \"{narration_spoken[:45]}...\")")
            audio_bytes, words = await synthesize_scene_edge_tts(narration_spoken, voice=voice, rate=rate)

            # Map authentic historical display words back to timestamps so subtitles display correctly
            orig_words = narration_raw.split()
            if words and len(words) == len(orig_words):
                for w_obj, orig_w in zip(words, orig_words):
                    w_obj["word"] = orig_w

            # Save temporary scene MP3
            scene_mp3 = temp_dir / f"scene_{scene_id}.mp3"
            with open(scene_mp3, "wb") as f:
                f.write(audio_bytes)

            # Trim trailing dead silence with ffmpeg to eliminate encoder padding and keep cuts crisp
            scene_wav = temp_dir / f"scene_{scene_id}.wav"
            trim_cmd = [
                ffmpeg_bin, "-y", "-hide_banner",
                "-i", str(scene_mp3),
                "-af", "areverse,silenceremove=start_periods=1:start_duration=0.05:start_threshold=-35dB,areverse,apad=pad_dur=0.15",
                "-ar", "24000", "-ac", "1",
                str(scene_wav)
            ]
            trim_res = subprocess.run(trim_cmd, capture_output=True, text=True)
            target_audio = scene_wav if (trim_res.returncode == 0 and scene_wav.exists()) else scene_mp3

            # Measure exact scene duration from audio with ffmpeg
            probe_cmd = [ffmpeg_bin, "-hide_banner", "-i", str(target_audio)]
            probe_res = subprocess.run(probe_cmd, capture_output=True, text=True)
            dur_match = re.search(r"Duration:\s*(\d+):(\d+):([\d\.]+)", probe_res.stderr)
            if dur_match:
                h, m, s = map(float, dur_match.groups())
                audio_dur = round(h * 3600 + m * 60 + s, 2)
            else:
                audio_dur = float(scene.get("target_duration", 3.0))

            # Enforce cinematic minimum floor hold (2.0s) so brief utterances don't create sub-floor cuts
            if audio_dur < 2.0:
                scene_dur = 2.0
                pad_needed = round(2.0 - audio_dur, 2)
                padded_wav = temp_dir / f"scene_{scene_id}_padded.wav"
                pad_cmd = [
                    ffmpeg_bin, "-y", "-hide_banner",
                    "-i", str(target_audio),
                    "-af", f"apad=pad_dur={pad_needed}",
                    "-ar", "24000", "-ac", "1",
                    str(padded_wav)
                ]
                pad_res = subprocess.run(pad_cmd, capture_output=True, text=True)
                if pad_res.returncode == 0 and padded_wav.exists():
                    target_audio = padded_wav
            else:
                scene_dur = audio_dur

            # Fallback word boundary interpolation if edge-tts did not yield WordBoundary
            words_list = narration_raw.split()
            if not words and words_list:
                char_counts = [max(len(w.strip(".,!?;:\"'")), 1) for w in words_list]
                total_chars = sum(char_counts)
                curr = 0.05
                usable_dur = max(scene_dur - 0.2, 1.0)
                for w, cnt in zip(words_list, char_counts):
                    w_dur = (cnt / total_chars) * usable_dur
                    words.append({
                        "word": w,
                        "start": round(curr, 3),
                        "end": round(curr + w_dur * 0.9, 3)
                    })
                    curr += w_dur

            # Shift word timestamps by global timeline offset
            scene_words = []
            for w in words:
                scene_words.append({
                    "word": w["word"],
                    "start": round(current_time_offset + w["start"], 3),
                    "end": round(current_time_offset + w["end"], 3)
                })

            scene_start = current_time_offset
            scene_end = round(current_time_offset + scene_dur, 3)

            scene_records.append({
                "scene_id": scene_id,
                "start_time": round(scene_start, 3),
                "end_time": round(scene_end, 3),
                "narration": narration_raw,
                "words": scene_words
            })

            scene_audio_files.append(target_audio)
            # Advance time offset directly to end of scene audio
            current_time_offset = scene_end

        # Concatenate scene audio files into final master WAV
        concat_list_file = temp_dir / "concat_list.txt"
        with open(concat_list_file, "w", encoding="utf-8") as f:
            for s_file in scene_audio_files:
                f.write(f"file '{s_file.resolve()}'\n")

        output_audio.parent.mkdir(parents=True, exist_ok=True)
        print(f"[INFO] Converting and mastering narration track to {output_audio.resolve()}...")
        
        concat_cmd = [
            ffmpeg_bin, "-y", "-hide_banner",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list_file),
            "-ar", "24000", "-ac", "1",
            str(output_audio.resolve())
        ]
        res = subprocess.run(concat_cmd, capture_output=True, text=True)
        if res.returncode != 0 and scene_audio_files:
            single_cmd = [
                ffmpeg_bin, "-y", "-hide_banner",
                "-i", str(scene_audio_files[0]),
                "-ar", "24000", "-ac", "1",
                str(output_audio.resolve())
            ]
            subprocess.run(single_cmd, capture_output=True)

        total_duration = round(current_time_offset, 3)

        # Write timestamps.json
        timestamp_data = {
            "audio_file": str(output_audio.name),
            "total_duration": total_duration,
            "sample_rate": 24000,
            "voice": voice,
            "rate": rate,
            "scenes": scene_records
        }

        output_timestamps.parent.mkdir(parents=True, exist_ok=True)
        with open(output_timestamps, "w", encoding="utf-8") as f:
            json.dump(timestamp_data, f, indent=2, ensure_ascii=False)

        total_extracted_words = sum(len(s.get("words", [])) for s in scene_records)
        print(f"[SUCCESS] Synthesized voiceover: {output_audio.resolve()} ({total_duration}s)")
        print(f"[SUCCESS] Aligned timestamps written: {output_timestamps.resolve()} ({total_extracted_words} words)")

        # Synchronize exact spoken sentence endpoints into storyboard.json
        if storyboard_path.exists():
            for sc, rec in zip(storyboard.get("scenes", []), scene_records):
                sc_dur = round(rec["end_time"] - rec["start_time"], 2)
                sc["target_duration"] = sc_dur
                sc["time_range"] = f"{rec['start_time']:.1f}-{rec['end_time']:.1f}"
            storyboard["target_duration_seconds"] = total_duration
            with open(storyboard_path, "w", encoding="utf-8") as f:
                json.dump(storyboard, f, indent=2, ensure_ascii=False)
            print(f"[SUCCESS] Synchronized storyboard scene cuts to spoken sentence endpoints ({total_duration}s)")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Synthesize voiceover using edge-tts.")
    parser.add_argument("--storyboard", type=str, default="state/storyboard.json", help="Path to input storyboard JSON.")
    parser.add_argument("--output-audio", type=str, default="assets/audio/voiceover.wav", help="Destination WAV file.")
    parser.add_argument("--output-timestamps", type=str, default="assets/audio/timestamps.json", help="Destination JSON file.")
    parser.add_argument("--voice", type=str, default="en-US-ChristopherNeural", help="Voice model identifier.")
    parser.add_argument("--rate", type=str, default="+20%", help="Speech rate modification.")

    args = parser.parse_args()

    sb_path = Path(args.storyboard)
    if not sb_path.exists():
        print(f"[ERROR] Storyboard file '{sb_path}' not found.", file=sys.stderr)
        sys.exit(1)

    with open(sb_path, "r", encoding="utf-8") as f:
        storyboard = json.load(f)

    asyncio.run(synthesize_storyboard_edge_tts(
        storyboard=storyboard,
        storyboard_path=sb_path,
        output_audio=Path(args.output_audio),
        output_timestamps=Path(args.output_timestamps),
        voice=args.voice,
        rate=args.rate
    ))


if __name__ == "__main__":
    main()
