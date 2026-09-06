#!/usr/bin/env python3
"""
render_short.py - High-Tempo Short-Form Video Compilation Engine

Compiles vertical 9:16 video (1080x1920) across 12–16 rapid micro-scenes with alternating
dynamic Ken Burns camera grammar (push-in, tilt, tracking pan, snap zoom), burned kinetic captions
in safe zones, and sidechain auto-ducked soundtrack.
"""

import argparse
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path


def generate_ambient_drone_wav(output_path: Path, duration_seconds: float = 60.0, sample_rate: int = 44100):
    """
    Synthesizes a warm, non-pulsing granular textural ambient drone pad.
    Avoids low-frequency LFO swells that clash with sidechain ducking envelopes.
    Uses multiple detuned harmonics with gentle warm roll-off, soft noise bed, and slow global fade.
    """
    import random
    output_path.parent.mkdir(parents=True, exist_ok=True)
    num_samples = int(sample_rate * duration_seconds)
    samples = []

    # Layered detuned foundation pitches (C1 / C2 octave drone cluster: 55Hz, 55.4Hz, 110Hz, 110.7Hz, 164.8Hz, 220Hz)
    # Detuning creates natural acoustic phasing without global amplitude pulsing.
    tones = [
        (55.0, 0.35, 0.0),
        (55.35, 0.30, 1.2),
        (110.0, 0.20, 0.4),
        (110.7, 0.18, 2.1),
        (164.8, 0.12, 1.0),
        (220.0, 0.08, 3.0),
        (221.2, 0.06, 0.7),
    ]

    fade_in_samples = int(sample_rate * 2.5)
    fade_out_samples = int(sample_rate * 3.0)
    fade_out_start = num_samples - fade_out_samples

    rng = random.Random(42)
    noise_val = 0.0

    for i in range(num_samples):
        t = i / sample_rate

        # Smooth linear envelope at boundaries; 1.0 throughout the body
        if i < fade_in_samples:
            env = i / fade_in_samples
        elif i > fade_out_start:
            env = max(0.0, (num_samples - i) / fade_out_samples)
        else:
            env = 1.0

        val = 0.0
        for freq, amp, phase in tones:
            val += amp * math.sin(2 * math.pi * freq * t + phase)

        # Soft low-pass filtered noise bed (tape warmth texture)
        white = rng.uniform(-0.04, 0.04)
        noise_val = 0.95 * noise_val + 0.05 * white
        val += noise_val

        combined = val * env * 0.4
        sample_int = int(combined * 32767)
        samples.append(max(-32768, min(32767, sample_int)))

    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        raw_data = struct.pack(f"<{len(samples)}h", *samples)
        wf.writeframes(raw_data)

    print(f"[INFO] Synthesized textural ambient drone pad: {output_path.resolve()}")


def resolve_bgm_track(bgm_path: Path = None, topic_path: Path = None, topic_id: str = None, duration_seconds: float = 60.0) -> Path:
    """
    Selects or generates appropriate background score from per-category libraries:
    1. Direct user-specified BGM file if custom (non-default) and exists.
    2. Category-based deterministic selection from assets/bgm/ using SHA-256 hash of topic_id:
       - 'siege_engine' / 'forgotten_siege_engine' -> rites.mp3, tense_drone.wav, SCP-x3x.mp3, the_descent.mp3, hitman.mp3
       - 'cavalry_battle' -> percussive_war.wav, volatile_reaction.mp3, soundtrack.mp3, clash_defiant.mp3
       - 'tactical_anomaly' -> volatile_reaction.mp3, hitman.mp3, percussive_war.wav, soundtrack.mp3, clash_defiant.mp3
       - 'bizarre_invention' -> soundtrack_s1.mp3, hitman.mp3, rites.mp3, tense_drone.wav, SCP-x3x.mp3
       - 'naval_clash' -> clash_defiant.mp3, soundtrack.mp3, volatile_reaction.mp3, percussive_war.wav, the_descent.mp3
    3. Cross-checks selected track against assets/bgm/LICENSES.json.
    4. Granular/textural drone pad synthesis fallback if no files exist.
    """
    repo_root = Path(__file__).resolve().parents[4]
    bgm_dir = repo_root / "assets" / "bgm"
    if not bgm_dir.exists():
        bgm_dir = Path("assets/bgm")

    # If caller explicitly provided a non-default existing path
    if bgm_path is not None and bgm_path.exists() and bgm_path.name != "soundtrack.wav" and bgm_path.stat().st_size > 5000:
        return bgm_path

    if topic_path is None or not topic_path.exists():
        fallback_topic = repo_root / "state" / "topic.json"
        if fallback_topic.exists():
            topic_path = fallback_topic

    category = ""
    resolved_topic_id = topic_id or ""
    if topic_path and topic_path.exists():
        try:
            with open(topic_path, "r", encoding="utf-8") as f:
                topic_data = json.load(f)
                category = str(topic_data.get("category", "")).lower()
                if not resolved_topic_id:
                    resolved_topic_id = topic_data.get("topic_id", "") or topic_data.get("title", "")
        except Exception:
            pass

    import hashlib
    category_pools = {
        "siege_engine": ["rites.mp3", "tense_drone.wav", "SCP-x3x.mp3", "the_descent.mp3", "hitman.mp3"],
        "forgotten_siege_engine": ["rites.mp3", "tense_drone.wav", "SCP-x3x.mp3", "soundtrack_s1.mp3", "the_descent.mp3"],
        "cavalry_battle": ["percussive_war.wav", "volatile_reaction.mp3", "soundtrack.mp3", "clash_defiant.mp3"],
        "tactical_anomaly": ["volatile_reaction.mp3", "hitman.mp3", "percussive_war.wav", "soundtrack.mp3", "clash_defiant.mp3"],
        "bizarre_invention": ["soundtrack_s1.mp3", "hitman.mp3", "rites.mp3", "tense_drone.wav", "SCP-x3x.mp3"],
        "naval_clash": ["clash_defiant.mp3", "soundtrack.mp3", "volatile_reaction.mp3", "percussive_war.wav", "the_descent.mp3"],
        "default": ["soundtrack.mp3", "volatile_reaction.mp3", "rites.mp3", "percussive_war.wav", "hitman.mp3", "clash_defiant.mp3"]
    }

    pool = category_pools.get(category, category_pools["default"])
    valid_candidates = [t for t in pool if (bgm_dir / t).exists() and (bgm_dir / t).stat().st_size > 5000]

    if not valid_candidates:
        all_local = list(bgm_dir.glob("*.mp3")) + list(bgm_dir.glob("*.wav"))
        valid_candidates = [f.name for f in all_local if f.stat().st_size > 5000]

    if valid_candidates:
        seed_key = resolved_topic_id or category or "default_seed"
        seed_hash = int(hashlib.sha256(seed_key.encode("utf-8")).hexdigest(), 16)
        chosen_filename = valid_candidates[seed_hash % len(valid_candidates)]
        chosen_path = bgm_dir / chosen_filename

        # Cross-reference with LICENSES.json
        lic_file = bgm_dir / "LICENSES.json"
        lic_info = ""
        if lic_file.exists():
            try:
                with open(lic_file, "r", encoding="utf-8") as lf:
                    lic_data = json.load(lf)
                    track_meta = lic_data.get("tracks", {}).get(chosen_filename, {})
                    if track_meta:
                        lic_info = f" [License: {track_meta.get('license', 'Unknown')}, Artist: {track_meta.get('artist', 'Unknown')}]"
                    else:
                        print(f"[WARN] BGM track '{chosen_filename}' lacks entry in LICENSES.json!", file=sys.stderr)
            except Exception:
                pass

        print(f"[INFO] Deterministically selected BGM track for category '{category or 'default'}' (topic='{seed_key}'): {chosen_filename}{lic_info}")
        return chosen_path

    # Fallback to granular/textural synthesis if no bundled tracks exist
    fallback_synth = bgm_dir / "soundtrack_ai.wav"
    generate_ambient_drone_wav(fallback_synth, duration_seconds=duration_seconds)
    return fallback_synth


def format_ass_time(seconds: float) -> str:
    """Formats seconds into ASS timestamp: H:MM:SS.cs"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def generate_ass_subtitles(timestamps_path: Path, output_ass_path: Path, max_words_per_chunk: int = 3, max_chars_per_chunk: int = 21) -> bool:
    """
    Generates an Advanced SubStation Alpha (.ass) subtitle file tailored for vertical 9:16 video.
    Aligns text in TikTok/Reels safe zones (MarginV=420) and limits chunks to 2-3 words (<22 chars).
    """
    if not timestamps_path.exists():
        return False

    try:
        with open(timestamps_path, "r", encoding="utf-8") as f:
            ts_data = json.load(f)
    except Exception as e:
        print(f"[WARN] Failed to load timestamps for subtitles: {e}", file=sys.stderr)
        return False

    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Kinetic,Arial,60,&H00FFFFFF,&H0000D7FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,3,2,100,100,420,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    scenes = ts_data.get("scenes", [])
    for sc in scenes:
        words = sc.get("words", [])
        if not words:
            continue
        curr_chunk = []
        curr_chars = 0
        chunks = []
        for w in words:
            w_text = w.get("word", "")
            if len(curr_chunk) >= max_words_per_chunk or (curr_chunk and curr_chars + len(w_text) + 1 > max_chars_per_chunk):
                chunks.append(curr_chunk)
                curr_chunk = [w]
                curr_chars = len(w_text)
            else:
                curr_chunk.append(w)
                curr_chars += len(w_text) + (1 if curr_chunk else 0)
        if curr_chunk:
            chunks.append(curr_chunk)

        for chunk in chunks:
            t_start = chunk[0].get("start", 0.0)
            t_end = chunk[-1].get("end", t_start + 0.8)
            if t_end - t_start < 0.6:
                t_end = t_start + 0.6
            text = " ".join(w.get("word", "") for w in chunk).strip().upper()
            t_start_str = format_ass_time(t_start)
            t_end_str = format_ass_time(t_end)
            events.append(f"Dialogue: 0,{t_start_str},{t_end_str},Kinetic,,0,0,0,,{text}")

    output_ass_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events) + "\n")

    print(f"[INFO] Kinetic captions generated: {output_ass_path.resolve()} ({len(events)} cues)")
    return True


def compile_video_ffmpeg(storyboard: dict, audio_path: Path, timestamps_path: Path, frames_dir: Path, bgm_path: Path, output_path: Path, burn_captions: bool = True):
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        try:
            import imageio_ffmpeg
            ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
            print(f"[INFO] Using bundled FFmpeg binary: {ffmpeg_bin}")
        except Exception:
            ffmpeg_bin = None

    if not ffmpeg_bin:
        print("[ERROR] FFmpeg is not found in system PATH or imageio-ffmpeg.", file=sys.stderr)
        return False

    scenes = storyboard.get("scenes", [])
    if not scenes:
        print("[ERROR] No scenes found in storyboard.", file=sys.stderr)
        return False

    scene_durations = []
    for sc in scenes:
        dur = float(sc.get("target_duration", 0.0))
        if dur <= 0:
            time_range = sc.get("time_range", "")
            if "-" in time_range:
                try:
                    parts = time_range.split("-")
                    dur = float(parts[1]) - float(parts[0])
                except Exception:
                    dur = 3.0
            else:
                dur = 3.0
        scene_durations.append(dur)

    total_target_duration = sum(scene_durations)
    print(f"[INFO] Compiling {len(scenes)} micro-scenes (Total duration: {total_target_duration:.2f}s, avg: {total_target_duration/len(scenes):.2f}s/cut)...")

    input_args = []
    filter_complex_parts = []
    concat_inputs = []

    fps = 30
    width = 1080
    height = 1920

    for idx, (scene, duration) in enumerate(zip(scenes, scene_durations)):
        scene_id = scene.get("scene_id", idx + 1)
        frame_file = frames_dir / f"scene_{scene_id}.png"
        if not frame_file.exists():
            print(f"[ERROR] Required frame file missing: {frame_file.resolve()}", file=sys.stderr)
            return False

        input_args.extend(["-i", str(frame_file.resolve())])
        scene_frames = int(duration * fps)

        # Check for climax/reveal scenes with high-intensity keywords
        scene_cue_text = f"{scene.get('sound_fx_cue', '')} {scene.get('narration', '')}".lower()
        impact_keywords = ("shatter", "crush", "collapse", "scream", "explode")
        if any(kw in scene_cue_text for kw in impact_keywords):
            m_type = 4
        else:
            m_type = idx % 4

        # Dynamic Ken Burns motions (normalized velocity to ensure steady motion across variable 2.0s-5.0s durations):
        # 0: Fast push-in (steady zoom from 1.0 to 1.22)
        # 1: Dynamic tilt-down (steady vertical pedestal ~90px within boundary)
        # 2: Subtle tracking pan right (steady horizontal pan ~75px within boundary)
        # 3: Snap zoom out (steady pull from 1.22 to 1.02)
        # 4: Static hold (impact/climax beat)
        if m_type == 0:
            z_step = 0.22 / scene_frames
            zoom_filter = f"zoompan=z='min(zoom+{z_step:.5f},1.25)':d={scene_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps}"
        elif m_type == 1:
            y_step = 90.0 / scene_frames
            zoom_filter = f"zoompan=z='1.12':d={scene_frames}:x='iw/2-(iw/zoom/2)':y='if(eq(on,1),0,min(ih-(ih/zoom),y+{y_step:.3f}))':s={width}x{height}:fps={fps}"
        elif m_type == 2:
            x_step = 75.0 / scene_frames
            zoom_filter = f"zoompan=z='1.12':d={scene_frames}:x='if(eq(on,1),0,min(iw-(iw/zoom),x+{x_step:.3f}))':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps}"
        elif m_type == 3:
            z_step = 0.20 / scene_frames
            zoom_filter = f"zoompan=z='if(eq(on,1),1.22,max(1.02,zoom-{z_step:.5f}))':d={scene_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps}"
        else:
            # m_type == 4: Static hold reserved for climax/reveal scenes
            zoom_filter = f"zoompan=z='1.0':d={scene_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps}"

        filter_complex_parts.append(
            f"[{idx}:v]scale=1080:1920,{zoom_filter},trim=duration={duration},setpts=PTS-STARTPTS,setsar=1[v{idx}]"
        )
        concat_inputs.append(f"[v{idx}]")

    voice_idx = len(scenes)
    bgm_idx = len(scenes) + 1

    input_args.extend(["-i", str(audio_path.resolve())])
    input_args.extend(["-stream_loop", "-1", "-i", str(bgm_path.resolve())])

    # Concat video streams
    concat_str = "".join(concat_inputs) + f"concat=n={len(scenes)}:v=1:a=0[v_concat]"
    filter_complex_parts.append(concat_str)

    # Film emulation (subtle dynamic 35mm grain & archival color grading)
    film_emulation_filter = "[v_concat]noise=c0s=8:c0f=t+u,curves=vintage[v_film]"
    filter_complex_parts.append(film_emulation_filter)

    # Burned kinetic captions
    final_v_out = "v_film"
    repo_root = Path(__file__).resolve().parents[4]
    ass_path = (repo_root / "state" / "captions.ass").resolve() if (repo_root / "state").exists() else Path("state/captions.ass").resolve()
    if burn_captions and timestamps_path.exists():
        if generate_ass_subtitles(timestamps_path, ass_path):
            ass_resolved = str(ass_path).replace("\\", "/")
            if ":" in ass_resolved:
                ass_escaped = ass_resolved.replace(":", "\\\\:")
            else:
                ass_escaped = ass_resolved
            filter_complex_parts.append(f"[v_film]subtitles={ass_escaped}[v_captions]")
            final_v_out = "v_captions"

    # Sidechain audio ducking with boundary fades (empirically tuned for broadcast-grade voice activation)
    fade_out_start = max(0.0, total_target_duration - 1.5)
    audio_ducking_filter = (
        f"[{voice_idx}:a]volume=1.0,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,asplit=2[voice_main][voice_sidechain];"
        f"[{bgm_idx}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
        f"afade=t=in:ss=0:d=1.0,afade=t=out:st={fade_out_start:.2f}:d=1.5,volume=0.22[bgm_fmt];"
        f"[bgm_fmt][voice_sidechain]sidechaincompress="
        f"threshold=0.018:"
        f"ratio=12:"
        f"attack=15:"
        f"release=300:"
        f"makeup=1.0[ducked_bgm];"
        f"[voice_main][ducked_bgm]amix=inputs=2:duration=first:dropout_transition=2,"
        f"alimiter=limit=0.95[a_out]"
    )
    filter_complex_parts.append(audio_ducking_filter)

    full_filter = ";".join(filter_complex_parts)

    cmd = [
        ffmpeg_bin,
        "-y",
        "-hide_banner",
        *input_args,
        "-filter_complex", full_filter,
        "-map", f"[{final_v_out}]",
        "-map", "[a_out]",
        "-t", str(total_target_duration),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "22",
        "-r", "30",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-c:a", "aac",
        "-b:a", "192k",
        str(output_path.resolve())
    ]

    print("[INFO] Invoking FFmpeg compiler with high-tempo scene cuts, burned kinetic captions, and auto-ducking...")
    result = subprocess.run(cmd, stdout=None, stderr=None)

    if result.returncode != 0:
        print(f"[ERROR] FFmpeg exited with error code {result.returncode}", file=sys.stderr)
        return False

    print(f"[SUCCESS] Short-form video successfully rendered: {output_path.resolve()}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Remotion/FFmpeg Short-Form Video Compiler")
    parser.add_argument("--topic-id", type=str, default=None, help="Optional topic ID for path resolution (e.g. archimedes-claw).")
    parser.add_argument("--storyboard", type=str, default="state/storyboard.json", help="Path to storyboard JSON.")
    parser.add_argument("--topic", type=str, default="state/topic.json", help="Path to topic JSON for category-based BGM selection.")
    parser.add_argument("--audio", type=str, default="assets/audio/voiceover.wav", help="Path to voiceover WAV.")
    parser.add_argument("--timestamps", type=str, default="assets/audio/timestamps.json", help="Path to timestamps JSON.")
    parser.add_argument("--frames-dir", type=str, default="assets/frames", help="Directory of keyframe PNGs.")
    parser.add_argument("--bgm", type=str, default="assets/bgm/soundtrack.wav", help="Path to BGM WAV/MP3.")
    parser.add_argument("--output", type=str, default="out/final_short.mp4", help="Destination MP4.")
    parser.add_argument("--no-captions", action="store_true", help="Disable burned kinetic captions.")

    args = parser.parse_args()

    sb_path = Path(args.storyboard)
    topic_path = Path(args.topic)
    audio_path = Path(args.audio)
    ts_path = Path(args.timestamps)
    frames_dir = Path(args.frames_dir)
    bgm_path = Path(args.bgm)
    out_path = Path(args.output)

    if args.topic_id:
        topic_frames = Path("assets/frames") / args.topic_id
        if topic_frames.exists() and any(topic_frames.glob("scene_*.png")):
            frames_dir = topic_frames
        elif (frames_dir / args.topic_id).exists():
            frames_dir = frames_dir / args.topic_id

    if not sb_path.exists():
        print(f"[ERROR] Storyboard '{sb_path.resolve()}' does not exist.", file=sys.stderr)
        sys.exit(1)

    with open(sb_path, "r", encoding="utf-8") as f:
        storyboard = json.load(f)

    if not audio_path.exists():
        print(f"[ERROR] Voiceover audio '{audio_path.resolve()}' does not exist.", file=sys.stderr)
        sys.exit(1)

    # Resolve BGM by category or library track with textural synthesis fallback
    bgm_path = resolve_bgm_track(bgm_path, topic_path=topic_path, topic_id=args.topic_id, duration_seconds=60.0)

    out_path.parent.mkdir(parents=True, exist_ok=True)

    success = compile_video_ffmpeg(
        storyboard=storyboard,
        audio_path=audio_path,
        timestamps_path=ts_path,
        frames_dir=frames_dir,
        bgm_path=bgm_path,
        output_path=out_path,
        burn_captions=not args.no_captions
    )

    if not success:
        print("[ERROR] Video compilation failed.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
