# RED-TEAM ADVERSARIAL PENETRATION AUDIT & FAILURE REPORT
**Date of Audit**: 2026-09-07  
**Auditor**: Autonomous Red-Team Penetration Engineer (Adversarial QA)  
**Target Pipeline**: AI Video Production Pipeline (`video-scriptor`, `tts-audio-generator`, `image-generator`, `remotion-video-compiler`, `run_batch.py`)  
**Audit Policy**: READ-ONLY FORENSIC AUDIT (Zero source code modifications permitted)

---

## 1. Executive Breakdown

| Metric | Value |
| :--- | :--- |
| **Total Attack Vectors Executed** | **4 Major Vectors (11 Granular Sub-Vectors)** |
| **Total Pipeline Crashes (Unhandled Exceptions / Hard Failures)** | **4 Discovered** |
| **Total Silent Corruptions (Pipeline Completed, Corrupted Output)** | **5 Discovered** |
| **External API Rate Limit & Blocking Vulnerabilities** | **3 Discovered (Cloudflare Error 1010, IP Queue 429, Header 431)** |
| **Overall Pipeline Adversarial Resilience Rating** | **CRITICAL RISK / UNHANDLED BOUNDARY FAILURES** |

### Attack Vector Matrix Summary

| Vector ID | Target Subsystem | Attack Description | Outcome | Impact Classification |
| :--- | :--- | :--- | :--- | :--- |
| **V1.1** | `tts-audio-generator` | XML/SSML entity injection (`<break>`, `&`, `<`, `>`, `"`, `'`) | Literal token spoken aloud & subtitle timestamp desync | Silent Corruption |
| **V1.2a** | `tts-audio-generator` | Empty/whitespace string injection (`""`, `"   "`) | Loop bypass causes `UnboundLocalError` on `wave` | **Critical Crash** |
| **V1.2b** | `tts-audio-generator` | Mixed empty and micro-string scenes | `zip()` index misalignment overwrites scene cuts | Silent Corruption |
| **V1.3** | `tts-audio-generator` / Video Compiler | Monolithic 400-word sentence into 2.0s scene | 189.6s audio generated; video pans at 0.000038/frame | Silent Corruption & Platform Rejection |
| **V2.1** | `image-generator` | Extreme URI Length Boundary (2,000 to 16,384 chars) | Upstream queue drop & HTTP 431 Header Too Large | External API Drop |
| **V2.2** | `image-generator` | Concurrent request flooding (6 parallel workers) | Strict IP queue limit = 1 triggers HTTP 429 & timeouts | External API Rate Limit / Failure |
| **V2.3** | `image-generator` | Default Python `urllib` user agent without desktop headers | Cloudflare Error 1010: HTTP 403 Forbidden | External API Block |
| **V2.4** | `image-generator` | Truncated/corrupted file cache poisoning (> 5KB) | False positive cache hits; FFmpeg crashes exit 69 | **Critical Crash** |
| **V3.1** | `remotion-video-compiler` | Storyboard scene duration edge clamp (0.0s) | Silent fallback to 3.0s; audio cut misalignment | Silent Corruption |
| **V3.2** | `remotion-video-compiler` | Explicit non-existent stem/BGM path passed | Silently ignored, arbitrary substitute track chosen | Silent Failure |
| **V4.1** | `run_batch.py` | Mid-batch kill/crash during generation | State leaves zombie `in_progress`; corrupted frames poison cache | State Inconsistency & Pipeline Stall |
| **V4.2** | `run_batch.py` / Compiler | Cross-topic subtitle and topic state contamination | Shared global `state/captions.ass` and fallback `state/topic.json` | Silent Cross-Contamination |

---

## 2. Critical Vulnerabilities (Pipeline Crashes)

### Critical Vulnerability 1: `UnboundLocalError` on Empty/Whitespace Narration Scenes
- **Target File**: [`.agent/skills/tts-audio-generator/scripts/synthesize.py`](file:///c:/Projects/Videos/.agent/skills/tts-audio-generator/scripts/synthesize.py#L247-L402)
- **Trigger Condition**: A storyboard containing scenes where all narration values are empty strings `""` or whitespace `"   "`.
- **Root Cause**:
  In `synthesize_storyboard_edge_tts`, line 186 skips empty narration:
  ```python
  narration_raw = scene.get("narration", "").strip()
  if not narration_raw:
      continue
  ```
  The standard library module `wave` is imported only *inside* the scene processing loop at line 247 (`import wave`). If all scenes are skipped due to empty narration, line 247 is never executed.
  Downstream at line 402:
  ```python
  with wave.open(str(output_audio.resolve()), "rb") as wf:
      total_duration = round(wf.getnframes() / wf.getframerate(), 3)
  ```
  Python throws an unhandled `UnboundLocalError`. Furthermore, before reaching line 402, FFmpeg concat filter fails with `concat=n=0:v=0:a=1` because no scene audio files were generated:
  ```text
  [Parsed_concat_0] Value 0.000000 for parameter 'n' out of range [1 - 2.14748e+09]
  Error applying option 'n' to filter 'concat': Result too large
  ```
- **Exact Traceback**:
  ```text
  [INFO] Synthesizing 2 scenes with edge-tts (Voice: en-US-ChristopherNeural, Base Rate: +14%)...
  [INFO] Mastering narration track with lossless clean concatenation to C:\Projects\Videos\scratch\empty_audio.wav...
  [WARN] Concat filter failed ([Parsed_concat_0 @ 0000023c599719c0] Value 0.000000 for parameter 'n' out of range [1 - 2.14748e+09]
  Error applying option 'n' to filter 'concat': Result too large
  Failed to set value 'concat=n=0:v=0:), falling back to concat demuxer...
  Traceback (most recent call last):
    File "<string>", line 18, in test_all_empty
    File "C:\Projects\Videos\.agent/skills/tts-audio-generator/scripts\synthesize.py", line 402, in synthesize_storyboard_edge_tts
      with wave.open(str(output_audio.resolve()), "rb") as wf:
           ^^^^
  UnboundLocalError: cannot access local variable 'wave' where it is not associated with a value
  ```

---

### Critical Vulnerability 2: Cache Poisoning with Corrupted Frames Traps Video Compiler (Exit Code 69)
- **Target File**: [`.agent/skills/image-generator/scripts/generate_frames.py`](file:///c:/Projects/Videos/.agent/skills/image-generator/scripts/generate_frames.py#L38-L40) and [`.agent/skills/remotion-video-compiler/scripts/render_short.py`](file:///c:/Projects/Videos/.agent/skills/remotion-video-compiler/scripts/render_short.py#L377-L502)
- **Trigger Condition**: An aborted download, interrupted network stream, or partial HTTP response leaves a file in `assets/frames/{topic_id}/scene_X.png` that exceeds 5,000 bytes but contains invalid or truncated PNG data.
- **Root Cause**:
  `download_single_frame()` performs an unsafe byte-size check without verifying image integrity or magic headers:
  ```python
  if output_path.exists() and output_path.stat().st_size > 5000:
      print(f"[CACHE] Scene {scene_id:02d} already rendered ({output_path.stat().st_size/1024:.1f} KB): {output_path.name}")
      return True
  ```
  A 6KB corrupt file (e.g. valid 8-byte PNG header followed by nulls or an interrupted download) returns `True`. Every subsequent batch run skips downloading.
  When `render_short.py` invokes FFmpeg to read this frame, FFmpeg fails during video decoding with return code 69, completely halting the pipeline. Because the file remains cached on disk, every batch retry fails identically, causing a permanent deadlock.
- **Exact Traceback / Error Log**:
  ```text
  [CACHE] Scene 01 already rendered (5.9 KB): scene_1.png
  FFmpeg probe return code: 69
  [png @ 000001e11c9aba80] 0 bytes left
  [vist#0:0/png @ 000001e11c9bf740] [dec:png @ 000001e11c9a6d40] Decoding error: Invalid data found when processing input
  [vist#0:0/png @ 000001e11c9bf740] [dec:png @ 000001e11c9a6d40] Decode error rate 1 exceeds maximum 0.666667
  [vist#0:0/png @ 000001e11c9bf740] [dec:png @ 000001e11c9a6d40] Task finished with error code: -1145393733 (Error number -1145393733 occurred)
  [vist#0:0/png @ 000001e11c9bf740] [dec:png @ 000001e11c9a6d40] Terminating thread with return code -1145393733 (Error number -1145393733 occurred)
  Cannot determine format of input 0:0 after EOF
  [vf#0:0 @ 000001e11c9c9440] Task finished with error code: -1094995529 (Invalid data found when processing input)
  [vost#0:0/wrapped_avframe @ 000001e11c9cad00] Could not open encoder before EOF
  [out#0/null @ 000001e11c9bea80] Nothing was written into output file, because at least one of its streams received no packets.
  [ERROR] FFmpeg exited with error code 1
  ```

---

### Critical Vulnerability 3: Zero-Duration Cut / Frame Division by Zero
- **Target File**: [`.agent/skills/remotion-video-compiler/scripts/render_short.py`](file:///c:/Projects/Videos/.agent/skills/remotion-video-compiler/scripts/render_short.py#L406)
- **Trigger Condition**: In an edge case where a storyboard cut has `target_duration: 0.0` or `< 0.016` and the fallback logic is bypassed or duration is 0 frames (`scene_frames = int(duration * fps) = 0`).
- **Root Cause**:
  In `render_short.py`:
  ```python
  scene_frames = int(duration * fps)
  ...
  z_step = 0.22 / scene_frames
  ```
  If `scene_frames == 0`, Python raises `ZeroDivisionError`. While lines 337-348 contain a fallback `dur = 3.0` if `dur <= 0`, any fractional duration between 0.001s and 0.033s yields `scene_frames = 0`, triggering an unhandled exception before FFmpeg is ever launched.

---

### Critical Vulnerability 4: Immediate Process Termination on Missing Assets
- **Target File**: [`.agent/skills/remotion-video-compiler/scripts/render_short.py`](file:///c:/Projects/Videos/.agent/skills/remotion-video-compiler/scripts/render_short.py#L545-L566)
- **Trigger Condition**: Missing `voiceover.wav` or missing keyframe during compilation.
- **Root Cause**:
  `render_short.py` invokes `sys.exit(1)` directly in `main()` instead of raising structured exceptions, preventing parent scripts from executing cleanup handlers, leaving abandoned lockfiles or un-synchronized progress states.

---

## 3. Silent Failures (Pipeline Passed, but Output Corrupted)

### Silent Failure 1: Narrative & Timeline Misalignment from Skipped Empty/Whitespace Scenes
- **Target File**: [`.agent/skills/tts-audio-generator/scripts/synthesize.py`](file:///c:/Projects/Videos/.agent/skills/tts-audio-generator/scripts/synthesize.py#L187-L432)
- **Forensic Evidence**:
  When a storyboard has 3 scenes where Scene 1 is `""`, Scene 2 is `"   "`, and Scene 3 is `"A"`:
  1. `synthesize.py` skips scenes 1 and 2, appending only Scene 3 to `scene_records` (1 record).
  2. At line 425:
     ```python
     for sc, rec in zip(storyboard.get("scenes", []), scene_records):
         sc_dur = round(rec["end_time"] - rec["start_time"], 3)
         sc["target_duration"] = sc_dur
         sc["time_range"] = f"{rec['start_time']:.2f}-{rec['end_time']:.2f}"
     ```
     `storyboard["scenes"][0]` (Scene 1, empty) is matched with `scene_records[0]` (Scene 3)!
     Scene 1 is overwritten with Scene 3's spoken time range (`0.00-2.00`).
     Scene 2 and Scene 3 in `storyboard.json` are never updated!
  3. `timestamps.json` contains only 1 scene (`scene_id: 3`, duration: 2.0s).
  4. Downstream `render_short.py` reads `storyboard.json` (3 scenes, total target duration 6.0s), builds a video filtergraph for all 3 scenes (6.0s), but audio ends at 2.0s.
  - **Output Impact**: A 6-second video with 4.0 seconds of frozen black frames / dead silence and completely scrambled subtitles.

---

### Silent Failure 2: Monolithic Narration Overwrite Destroys Short-Form Platform Compliance
- **Target File**: [`.agent/skills/tts-audio-generator/scripts/synthesize.py`](file:///c:/Projects/Videos/.agent/skills/tts-audio-generator/scripts/synthesize.py#L427-L431)
- **Forensic Evidence**:
  When a 400-word sentence was injected into a 2.0-second scene:
  - `edge_tts` generated **189.574 seconds** (3 minutes 9 seconds) of audio.
  - `synthesize.py` unconditionally overwrote `sc["target_duration"] = 189.574` and `storyboard["target_duration_seconds"] = 189.574`.
  - In `render_short.py`:
    `scene_frames = int(189.574 * 30) = 5687 frames`.
    `z_step = 0.22 / 5687 = 0.00003868` zoom per frame.
  - **Output Impact**: The resulting video violates TikTok, YouTube Shorts, and Instagram Reels duration limits (hard maximum 60s/90s). The single still image appears completely static for over 3 minutes due to imperceptibly microscopic camera motion, inducing immediate audience drop-off.

---

### Silent Failure 3: SSML/XML Entity Tokenization Corrupts Spoken Word Subtitles
- **Target File**: [`.agent/skills/tts-audio-generator/scripts/synthesize.py`](file:///c:/Projects/Videos/.agent/skills/tts-audio-generator/scripts/synthesize.py#L204-L208)
- **Forensic Evidence**:
  When narration contains `<break time="500ms"/>`:
  - `edge_tts` reads the tag literally, emitting 5 word boundary tokens: `['break', 'time', '=', '500ms', '/']`.
  - In `synthesize.py`:
    ```python
    orig_words = narration_raw.split()
    if words and len(words) == len(orig_words):
        for w_obj, orig_w in zip(words, orig_words):
            w_obj["word"] = orig_w
    ```
    Because `len(words)` is 5 and `len(orig_words)` is 1, the length equality fails. The original script words are never mapped back into `timestamps.json`.
  - **Output Impact**: The voiceover speaks aloud the literal computer code ("break time equals five hundred milliseconds slash"), and the burned on-screen subtitles display each syntax token.

---

### Silent Failure 4: Global Caption Overwrite (`state/captions.ass`) Induces Cross-Topic Contamination
- **Target File**: [`.agent/skills/remotion-video-compiler/scripts/render_short.py`](file:///c:/Projects/Videos/.agent/skills/remotion-video-compiler/scripts/render_short.py#L447-L457)
- **Forensic Evidence**:
  In `render_short.py`, the ASS subtitle destination path is hardcoded to a global shared location:
  ```python
  ass_path = (repo_root / "state" / "captions.ass").resolve() if (repo_root / "state").exists() else Path("state/captions.ass").resolve()
  ```
  `render_short.py` ignores `--topic-id` when generating captions.
  If Topic A compiles, followed by Topic B:
  1. Both write to `state/captions.ass`.
  2. If Topic B encounters an error in `generate_ass_subtitles` (e.g. corrupt timestamps), `render_short.py` proceeds to burn whatever already exists in `state/captions.ass` ? which is Topic A's subtitles!
  - **Output Impact**: Topic B's video is rendered with Topic A's text subtitles burned across every frame.

---

### Silent Failure 5: Missing Stem / BGM Auto-Substitution Without Logging
- **Target File**: [`.agent/skills/remotion-video-compiler/scripts/render_short.py`](file:///c:/Projects/Videos/.agent/skills/remotion-video-compiler/scripts/render_short.py#L106-L107)
- **Forensic Evidence**:
  When caller passes an explicit `--bgm assets/audio/stems/non_existent_ambient_drone_dark.wav`:
  ```python
  if bgm_path is not None and bgm_path.exists() and bgm_path.name != "soundtrack.wav" and bgm_path.stat().st_size > 5000:
      return bgm_path
  ```
  Because the requested file does not exist, `bgm_path.exists()` is False. `resolve_bgm_track` silently ignores the user's explicit CLI argument and falls back to selecting an arbitrary track (`tense_drone.wav`).
  - **Output Impact**: The video compiles successfully without any warning that the specified musical score or stem was absent, producing mood and thematic dissonance.

---

## 4. External API Downtime & Vulnerabilities

Empirical penetration testing and live latency probing were conducted against all three upstream third-party services on 2026-09-07.

```
====================================================================================================
SERVICE                 STATUS              AVG LATENCY      THROTTLING / BLOCK THRESHOLD
====================================================================================================
Google Gemini 3.6 Flash OPERATIONAL         2.181s           Standard Quota (Resilient)
Microsoft Edge-TTS      OPERATIONAL         1.078s           Unconstrained for single streams
Pollinations (Flux)     HIGHLY CONGESTED    24.317s          IP Queue = 1 (Immediate HTTP 429)
Pollinations (Turbo)    OPERATIONAL         0.669s           IP Queue = 1
====================================================================================================
```

### 1. Pollinations API (image.pollinations.ai)
- **Status**: Operational but extremely congested on `flux` model.
- **Header Vulnerability (Cloudflare Error 1010)**:
  Any request sent using default Python `urllib` or lacking a desktop browser `User-Agent` (`Mozilla/5.0...`) is instantly blocked with **HTTP 403 Forbidden** (`error code: 1010`).
- **Concurrent Rate Throttling**:
  Pollinations enforces a strict per-IP concurrency queue limit of **1 request**:
  ```json
  {"error":"Too Many Requests","message":"Queue full for IP: 136.233.9.106: 1 requests already queued (max: 1). Get unlimited access at https://enter.pollinations.ai"}
  ```
  Flooding with 6 parallel threads resulted in immediate **HTTP 429** on 4 workers within 1.1s, 1 worker delayed 22.6s, and 1 worker aborted with a 51.7s `TimeoutError`.
- **URI Length Boundary**:
  - URLs up to ~2,000 characters succeed.
  - URLs between 4,000 and 11,000 characters induce queue congestion and timeouts.
  - URLs exceeding 16,000 characters fail with **HTTP 431 Request Header Fields Too Large**.

### 2. Microsoft Edge-TTS (WebSocket Speech Endpoint)
- **Status**: Fully Operational.
- **Latency**: Sub-second to low 1.2s across tested phrases (Avg: 1.078s).
- **Protocol Boundary**:
  Does not reject raw XML or SSML tags at the WebSocket layer, but parses tags into literal phonetic word tokens, corrupting word-level alignment downstream.

### 3. Google Gemini (gemini-3.6-flash via google-genai)
- **Status**: Operational.
- **Latency**: 2.13s ? 2.23s round-trip response time for validation ping.
- **Validation Fallback**:
  If Gemini API key is missing or quota is exhausted, `generate_storyboard.py` cleanly engages `algorithmic_fallback` via `synthesize_algorithmic_storyboard()`.

---

## 5. Summary & Audit Verdict

This adversarial red-team audit has successfully uncovered:
- **4 Critical Pipeline Crashes** (unhandled `UnboundLocalError`, corrupt cache deadlock exit 69, potential `ZeroDivisionError`, and unhandled `sys.exit` halts).
- **5 Silent Corruptions** (timeline desync, platform-violating durations, spoken code syntax in subtitles, global caption contamination, and silent BGM replacement).
- **3 External API Vulnerabilities** (Cloudflare Error 1010 HTTP 403 blocks, strict single-request concurrency HTTP 429 throttling, and HTTP 431 URI boundary drops).

In strict compliance with operational directives, **no source code has been altered, refactored, or fixed**. All findings are forensically documented above.
