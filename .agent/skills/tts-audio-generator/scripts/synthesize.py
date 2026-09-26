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
import numpy as np

try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False


# Coarse beat-type driven prosody variation (rate offset and pitch)
PROSODY_BY_BEAT = {
    "establishing": {"rate_offset": 0, "pitch": "+0Hz"},
    "rising_tension": {"rate_offset": 0, "pitch": "+0Hz"},
    "climax_impact": {"rate_offset": -5, "pitch": "-5Hz"},
    "resolution_loop": {"rate_offset": 0, "pitch": "+3Hz"},
}



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


def get_emphasis_intervals(words: list, emphasis_phrases: list, audio_dur: float) -> list:
    """
    Finds word intervals matching 1-2 emphasis words/phrases, marks is_emphasis=True
    on matched word objects, and returns merged (start, end) tuples for audio DSP boost.
    """
    if not words or not emphasis_phrases:
        return []
    
    clean_phrases = [p.lower().strip() for p in emphasis_phrases if p.strip()]
    if not clean_phrases:
        return []

    matched_indices = set()
    for phrase in clean_phrases:
        phrase_words = re.findall(r"\b\w+\b", phrase)
        if not phrase_words:
            continue
        p_len = len(phrase_words)
        for i in range(len(words) - p_len + 1):
            sub_words = [re.sub(r"[^\w]", "", words[i + j].get("word", "")).lower() for j in range(p_len)]
            if sub_words == phrase_words:
                for j in range(p_len):
                    matched_indices.add(i + j)
        for i, w in enumerate(words):
            cw = re.sub(r"[^\w]", "", w.get("word", "")).lower()
            if cw and any(cw == pw for pw in phrase_words):
                matched_indices.add(i)

    if not matched_indices:
        return []

    for i in matched_indices:
        words[i]["is_emphasis"] = True

    raw_intervals = sorted([(words[i]["start"], words[i]["end"]) for i in matched_indices])
    
    merged = []
    for st, et in raw_intervals:
        st = max(0.0, round(st, 3))
        et = min(audio_dur, round(et, 3))
        if not merged:
            merged.append([st, et])
        else:
            prev_st, prev_et = merged[-1]
            if st <= prev_et + 0.10:
                merged[-1][1] = max(prev_et, et)
            else:
                merged.append([st, et])

    return [(m[0], m[1]) for m in merged]


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


def probe_audio_duration(file_path: Path) -> float:
    """
    Probes exact physical duration of an audio file in seconds.
    Prioritizes byte-accurate PCM wave header inspection for WAV files,
    then ffprobe CLI, then ffmpeg banner probing.
    """
    file_path = Path(file_path)
    import wave
    if file_path.suffix.lower() == ".wav" and file_path.exists():
        try:
            with wave.open(str(file_path), "rb") as wf:
                return round(float(wf.getnframes()) / float(wf.getframerate()), 4)
        except Exception:
            pass

    ffprobe_bin = shutil.which("ffprobe")
    if ffprobe_bin:
        try:
            probe = subprocess.check_output([
                ffprobe_bin, "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)
            ])
            return round(float(probe.decode().strip()), 4)
        except Exception:
            pass

    ffmpeg_bin = get_ffmpeg_bin()
    if ffmpeg_bin:
        try:
            res = subprocess.run([ffmpeg_bin, "-hide_banner", "-i", str(file_path)], capture_output=True, text=True)
            m = re.search(r"Duration:\s*(\d+):(\d+):([\d\.]+)", res.stderr)
            if m:
                h, m_val, s = map(float, m.groups())
                return round(h * 3600 + m_val * 60 + s, 4)
        except Exception:
            pass

    return 0.0



async def synthesize_scene_edge_tts(text: str, voice: str, rate: str = "+0%", pitch: str = "+0Hz", max_retries: int = 3) -> tuple:
    """
    Synthesizes a single text block using edge-tts with exponential backoff on network timeouts.
    Emits native millisecond word timestamps using boundary="WordBoundary".
    Returns (audio_bytes, word_events).
    """
    for attempt in range(1, max_retries + 1):
        try:
            communicate = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch, boundary="WordBoundary")
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
                        "start": round(offset_sec, 3),
                        "end": round(offset_sec + duration_sec, 3)
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
    rate: str = "+14%"
):
    scenes = storyboard.get("scenes", [])
    if not scenes:
        raise ValueError("Storyboard contains no scenes.")

    ffmpeg_bin = get_ffmpeg_bin()
    temp_dir = Path(tempfile.mkdtemp(prefix="tts_edge_"))
    
    scene_records = []
    current_time_offset = 0.0
    scene_audio_files = []

    # Parse base rate and clamp strictly between 0% and +25%
    base_rate_match = re.search(r"[-+]?\d+", rate)
    base_rate_val = int(base_rate_match.group()) if base_rate_match else 20
    base_rate_val = max(0, min(25, base_rate_val))

    print(f"[INFO] Synthesizing {len(scenes)} scenes with edge-tts (Voice: {voice}, Base Rate: +{base_rate_val}%)...")

    try:
        for idx, scene in enumerate(scenes):
            scene_id = scene.get("scene_id", idx + 1)
            narration_raw = scene.get("narration", "").strip()
            if not narration_raw:
                continue

            # Layer 1: Beat-type driven prosody variation (rate and pitch)
            beat_type = str(scene.get("beat_type", "rising_tension")).lower().strip()
            beat_prosody = PROSODY_BY_BEAT.get(beat_type, PROSODY_BY_BEAT.get("rising_tension", {"rate_offset": 0, "pitch": "+0Hz"}))
            rate_offset = beat_prosody.get("rate_offset", 0)
            eff_rate_val = max(-10, min(25, base_rate_val + rate_offset))
            scene_rate = f"{eff_rate_val:+d}%"
            scene_pitch = beat_prosody.get("pitch", "+0Hz")

            narration_spoken = apply_phonetics(narration_raw)
            print(f"[INFO] Synthesizing Scene {scene_id} [{beat_type} (rate={scene_rate}, pitch={scene_pitch})]: \"{narration_raw[:45]}...\"")
            audio_bytes, words = await synthesize_scene_edge_tts(
                narration_spoken, voice=voice, rate=scene_rate, pitch=scene_pitch
            )

            # Map authentic historical display words back to timestamps so subtitles display correctly
            orig_words = narration_raw.split()
            if words and len(words) == len(orig_words):
                for w_obj, orig_w in zip(words, orig_words):
                    w_obj["word"] = orig_w

            # Save temporary scene MP3
            scene_mp3 = temp_dir / f"scene_{scene_id}.mp3"
            with open(scene_mp3, "wb") as f:
                f.write(audio_bytes)

            # Pass 1: Clean conversion to 24kHz mono WAV (strip leading digital silence so voice starts at t=0)
            scene_wav = temp_dir / f"scene_{scene_id}.wav"
            trim_cmd = [
                ffmpeg_bin, "-y", "-hide_banner",
                "-i", str(scene_mp3),
                "-af", "silenceremove=start_periods=1:start_duration=0.01:start_threshold=-50dB",
                "-ar", "24000", "-ac", "1",
                str(scene_wav)
            ]
            trim_res = subprocess.run(trim_cmd, capture_output=True, text=True)
            target_audio = scene_wav if (trim_res.returncode == 0 and scene_wav.exists()) else scene_mp3

            # Calculate leading silence offset between scene_mp3 and scene_wav using numpy cross-correlation
            lead_silence_sec = 0.0
            if words and scene_wav.exists():
                try:
                    p1 = subprocess.run([ffmpeg_bin, "-i", str(scene_mp3), "-f", "s16le", "-ar", "24000", "-ac", "1", "-t", "0.6", "-"], capture_output=True)
                    p2 = subprocess.run([ffmpeg_bin, "-i", str(scene_wav), "-f", "s16le", "-ar", "24000", "-ac", "1", "-t", "0.6", "-"], capture_output=True)
                    s1 = np.frombuffer(p1.stdout, dtype=np.int16).astype(np.float64)
                    s2 = np.frombuffer(p2.stdout, dtype=np.int16).astype(np.float64)
                    if len(s1) > 0 and len(s2) > 0:
                        offset_samples = np.argmax(np.correlate(s1, s2[:min(len(s2), int(0.25*24000))], mode='valid'))
                        lead_silence_sec = offset_samples / 24000.0
                except Exception:
                    lead_silence_sec = 0.0

            # Shift raw WordBoundary timestamps by stripped leading silence
            if lead_silence_sec > 0.0:
                for w in words:
                    w["start"] = max(0.0, round(w["start"] - lead_silence_sec, 3))
                    w["end"] = max(w["start"] + 0.05, round(w["end"] - lead_silence_sec, 3))

            # Measure exact audible speech duration from post-processed audio using probe_audio_duration
            raw_audio_dur = probe_audio_duration(target_audio)
            if raw_audio_dur <= 0:
                raw_audio_dur = float(scene.get("target_duration", 3.0))

            # Fallback word boundary interpolation if edge-tts did not yield WordBoundary
            words_list = narration_raw.split()
            if not words and words_list:
                char_counts = [max(len(w.strip(".,!?;:\"'")), 1) for w in words_list]
                total_chars = sum(char_counts)
                curr = 0.05
                usable_dur = max(raw_audio_dur - 0.40, 1.0)
                for w, cnt in zip(words_list, char_counts):
                    w_dur = (cnt / total_chars) * usable_dur
                    words.append({
                        "word": w,
                        "start": round(curr, 3),
                        "end": round(curr + w_dur * 0.9, 3)
                    })
                    curr += w_dur

            # Fix 1: Calibrated vocal decay (120ms) + explicit breath gap (200ms of pure digital silence)
            last_word_end = words[-1]["end"] if words else raw_audio_dur
            decay_dur = 0.120
            decay_end = round(last_word_end + decay_dur, 3)
            breath_gap = 0.200
            planned_scene_dur = max(round(decay_end + breath_gap, 3), 2.0)
            silence_pad = max(breath_gap, round(planned_scene_dur - decay_end, 3))

            # Layer 2: Targeted word-level emphasis boost (+2.5dB volume, +3.0dB presence EQ at 3kHz)
            emphasis_phrases = scene.get("emphasis_words", [])
            emphasis_intervals = get_emphasis_intervals(words, emphasis_phrases, raw_audio_dur)
            if emphasis_intervals:
                print(f"  [EMPHASIS] Scene {scene_id} emphasis intervals: {emphasis_intervals} for {emphasis_phrases}")

            # Pass 2: Apply word emphasis, onset fade, micro-fade out on vocal decay tail, and explicit silence breath gap
            padded_wav = temp_dir / f"scene_{scene_id}_padded.wav"
            af_filters = []
            for e_st, e_et in emphasis_intervals:
                af_filters.append(
                    f"volume=enable='between(t,{e_st:.3f},{e_et:.3f})':volume=2.5dB,"
                    f"equalizer=f=3000:t=q:w=1.0:g=3.0:enable='between(t,{e_st:.3f},{e_et:.3f})'"
                )
            af_filters.append("afade=t=in:ss=0:d=0.04:curve=exp")
            af_filters.append(f"atrim=0:{decay_end:.3f}")
            fade_out_st = max(0.0, decay_end - 0.030)
            af_filters.append(f"afade=t=out:st={fade_out_st:.3f}:d=0.030:curve=exp")
            af_filters.append(f"apad=pad_dur={silence_pad:.3f}")

            pad_cmd = [
                ffmpeg_bin, "-y", "-hide_banner",
                "-i", str(target_audio),
                "-af", ",".join(af_filters),
                "-t", f"{planned_scene_dur:.3f}",
                "-ar", "24000", "-ac", "1",
                str(padded_wav)
            ]
            pad_res = subprocess.run(pad_cmd, capture_output=True, text=True)
            if pad_res.returncode == 0 and padded_wav.exists():
                target_audio = padded_wav

            # Measure exact physical duration of the final audio slice
            actual_scene_dur = probe_audio_duration(target_audio)

            # Shift word timestamps by global timeline offset and retain is_emphasis flag
            scene_words = []
            for w in words:
                scene_words.append({
                    "word": w["word"],
                    "start": round(current_time_offset + w["start"], 3),
                    "end": round(current_time_offset + w["end"], 3),
                    "is_emphasis": bool(w.get("is_emphasis", False))
                })

            scene_start = current_time_offset
            scene_end = round(current_time_offset + actual_scene_dur, 3)

            scene_records.append({
                "scene_id": scene_id,
                "beat_type": beat_type,
                "prosody": {"rate": scene_rate, "pitch": scene_pitch},
                "emphasis_words": emphasis_phrases,
                "start_time": round(scene_start, 3),
                "end_time": round(scene_end, 3),
                "narration": narration_raw,
                "words": scene_words
            })

            scene_audio_files.append(target_audio)
            
            # Also persist individual scene audio in scenes subfolder for transparency
            scenes_dir = output_audio.parent / "scenes"
            scenes_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target_audio, scenes_dir / f"scene_{scene_id}.wav")

            # Advance time offset directly to physical end of scene audio
            current_time_offset = scene_end

        output_audio.parent.mkdir(parents=True, exist_ok=True)
        print(f"[INFO] Mastering narration track with lossless clean concatenation to {output_audio.resolve()}...")
        
        # Lossless clean concatenation (zero time loss, zero audio drift, preserves 0.35s decay buffers)
        if len(scene_audio_files) == 1:
            concat_cmd = [
                ffmpeg_bin, "-y", "-hide_banner",
                "-i", str(scene_audio_files[0]),
                "-ar", "24000", "-ac", "1",
                str(output_audio.resolve())
            ]
        else:
            inputs = []
            for s_file in scene_audio_files:
                inputs.extend(["-i", str(s_file.resolve())])
            
            filter_inputs = "".join([f"[{i}:a]" for i in range(len(scene_audio_files))])
            filter_complex = f"{filter_inputs}concat=n={len(scene_audio_files)}:v=0:a=1[a_master]"
            
            concat_cmd = [
                ffmpeg_bin, "-y", "-hide_banner",
                *inputs,
                "-filter_complex", filter_complex,
                "-map", "[a_master]",
                "-ar", "24000", "-ac", "1",
                str(output_audio.resolve())
            ]
        
        res = subprocess.run(concat_cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"[WARN] Concat filter failed ({res.stderr[:200]}), falling back to concat demuxer...", file=sys.stderr)
            concat_list_file = temp_dir / "concat_list.txt"
            with open(concat_list_file, "w", encoding="utf-8") as f:
                for s_file in scene_audio_files:
                    f.write(f"file '{s_file.resolve()}'\n")
            fallback_cmd = [
                ffmpeg_bin, "-y", "-hide_banner",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_list_file),
                "-ar", "24000", "-ac", "1",
                str(output_audio.resolve())
            ]
            subprocess.run(fallback_cmd, capture_output=True)

        total_duration = probe_audio_duration(output_audio.resolve())

        # Write timestamps.json
        timestamp_data = {
            "audio_file": str(output_audio.name),
            "total_duration": total_duration,
            "sample_rate": 24000,
            "voice": voice,
            "rate": f"+{base_rate_val}%",
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
                sc_dur = round(rec["end_time"] - rec["start_time"], 3)
                sc["target_duration"] = sc_dur
                sc["time_range"] = f"{rec['start_time']:.2f}-{rec['end_time']:.2f}"
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
    parser.add_argument("--rate", type=str, default="+18%", help="Speech rate modification.")


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
