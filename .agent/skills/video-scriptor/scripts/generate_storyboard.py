#!/usr/bin/env python3
"""
generate_storyboard.py - Modern Documentary Storyboard & Narrative Voice Generator

Upgrades production quality to a refined documentary standard:
- Strips generic encyclopedia phrasing ("In 208 AD...", "X decided to...").
- Structures narratives around a visceral hook, rising mechanical tension, and dramatic turning points.
- 13 tightly synchronized micro-scenes (2.2s to 3.2s per cut).
- Contextual Material Grounding: tactile physical action combined with authentic period materials.
- Hard Negative Bans: forbids modern naval elements, smokestacks, electric bulbs, pushpins, anime, fantasy CGI.
- Strict Alternating Shot Scales: Extreme Macro Close-Up -> Low-Angle Grounded POV -> Wide Tactical Action -> Medium Tension Portrait.
- Cinema Lens Prompts: Arri Alexa LF, 35mm anamorphic prime lens, volumetric torchlight, dawn mist, 35mm grain.
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    from google import genai
    from google.genai import types
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

CINEMA_LENS_SUFFIX = "Shot on Arri Alexa LF, 35mm anamorphic prime lens, natural volumetric torchlight and dawn mist, authentic 35mm film grain, muted historical color grading, photorealistic archival texture, 8k documentary still"
NEGATIVE_PROMPT = "modern naval elements, steel hulls, steam engines, smokestacks, electric lights, lightbulbs, pushpins, modern flags, anime, cartoon, 3d render, hyper-saturated fantasy cgi, glossy plastic, modern clothing, blur, low quality"

SHOT_SCALES = [
    "Extreme Macro Close-Up",
    "Low-Angle Grounded POV",
    "Wide Tactical Action",
    "Medium Tension Portrait"
]

def normalize_topic_id(raw_id: str) -> str:
    """Normalizes known topic aliases to canonical IDs before generation."""
    alias_map = {
        "carrhae-testudo": "battle-of-carrhae-camel-train",
        "the-archimedes-claw-at-syracuse": "archimedes-claw",
        "the-fire-ships-of-red-cliffs": "red-cliffs-fire-ships",
        "the-roman-scutum-testudo-at-carrhae": "battle-of-carrhae-camel-train"
    }
    return alias_map.get(raw_id, raw_id)


def get_gemini_api_key(cli_key: str = None) -> str:
    """Resolves Gemini API key from CLI, environment (GEMINI_API_KEY, GOOGLE_API_KEY), Windows registry, or .env file."""
    if cli_key:
        return cli_key
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]
    if os.environ.get("GOOGLE_API_KEY"):
        return os.environ["GOOGLE_API_KEY"]

    # Check Windows user registry environment
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as env_key:
                try:
                    val, _ = winreg.QueryValueEx(env_key, "GEMINI_API_KEY")
                    if val:
                        os.environ["GEMINI_API_KEY"] = val
                        return val
                except WindowsError:
                    pass
                try:
                    val, _ = winreg.QueryValueEx(env_key, "GOOGLE_API_KEY")
                    if val:
                        os.environ["GOOGLE_API_KEY"] = val
                        return val
                except WindowsError:
                    pass
        except Exception:
            pass

    # Search for .env file
    for env_path in [Path(".env"), Path(__file__).resolve().parents[4] / ".env"]:
        if env_path.exists():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("GEMINI_API_KEY="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            os.environ["GEMINI_API_KEY"] = val
                            return val
                    elif line.startswith("GOOGLE_API_KEY="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            os.environ["GOOGLE_API_KEY"] = val
                            return val
            except Exception:
                pass
    return None


def extract_json(raw_text: str) -> dict:
    """Extracts and parses JSON object from LLM response text."""
    text = raw_text.strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()

    parsed = None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            parsed = json.loads(text[start:end+1])
        else:
            start_l = text.find("[")
            end_l = text.rfind("]")
            if start_l != -1 and end_l != -1 and end_l > start_l:
                parsed = json.loads(text[start_l:end_l+1])
            else:
                raise

    if isinstance(parsed, list):
        return {"scenes": parsed}
    return parsed


BEAT_RANGES = {
    "establishing": (2.0, 2.8),
    "rising_tension": (2.8, 3.5),
    "climax_impact": (3.5, 5.0),
    "resolution_loop": (2.5, 3.5),
}


def validate_storyboard_data(data: dict) -> list[str]:
    """
    Strict programmatic validation of the generated storyboard:
    1. 12-16 scenes, alternating shot_scale in exact rotation (idx % 4).
    2. Variable scene duration strictly bounded by narrative beat_type:
       - establishing: 2.0s - 2.8s
       - rising_tension: 2.8s - 3.5s
       - climax_impact: 3.5s - 5.0s
       - resolution_loop: 2.5s - 3.5s
    3. Per-scene and total narration pacing scaled to target duration (~2.8 words/sec).
    4. Phrasing bans: no 'In [year]', 'This/It was', or biographical proper-noun 'X was/were'.
    5. Mandatory tactile and cinematographic metadata fields present.
    """
    errors = []
    scenes = data.get("scenes", [])
    if not isinstance(scenes, list):
        return ["'scenes' field must be a list of scene objects."]

    # Requirement 1: 12-16 scenes
    if len(scenes) < 12 or len(scenes) > 16:
        errors.append(f"Requirement 1 failed: Expected 12 to 16 scenes, got {len(scenes)}.")

    total_words = 0
    total_duration = 0.0

    banned_year = re.compile(r"^in\s+\d{1,4}\b", re.IGNORECASE)
    banned_this_it = re.compile(r"^(this|it)\s+(was|is|were)\b", re.IGNORECASE)
    # Tightened: strictly targets capitalized proper nouns / titular subjects (e.g. "Marcellus was", "The Consul was")
    banned_proper_noun_was = re.compile(r"^(?:The\s+)?[A-Z][a-z0-9'\-]+\s+(?:was|were)\b")

    required_fields = [
        "tactile_material_action",
        "visual_description",
        "camera_angle",
        "focal_length",
        "lighting_scheme",
        "camera_motion",
        "sound_fx_cue",
    ]

    for idx, sc in enumerate(scenes):
        sc_num = sc.get("scene_id", idx + 1)

        # Beat type validation
        beat_type = sc.get("beat_type")
        if not beat_type or beat_type not in BEAT_RANGES:
            errors.append(
                f"Requirement 2 failed (Scene {sc_num}): beat_type must be one of {list(BEAT_RANGES.keys())}, got '{beat_type}'."
            )
            min_d, max_d = 2.0, 5.0
        else:
            min_d, max_d = BEAT_RANGES[beat_type]

        # Duration validation against beat_type range
        try:
            dur = float(sc.get("target_duration", 0.0))
        except (ValueError, TypeError):
            dur = 0.0

        if dur < min_d or dur > max_d:
            errors.append(
                f"Requirement 2 failed (Scene {sc_num}): target_duration for beat_type '{beat_type}' must be between {min_d:.1f}s and {max_d:.1f}s, got {dur:.2f}s."
            )
        total_duration += dur

        # Alternating shot_scale through rotation
        expected_scale = SHOT_SCALES[idx % 4]
        if sc.get("shot_scale") != expected_scale:
            errors.append(f"Requirement 1 failed (Scene {sc_num}): shot_scale must be '{expected_scale}', got '{sc.get('shot_scale')}'.")

        # Mandatory textural and camera fields
        for field in required_fields:
            val = str(sc.get(field, "")).strip()
            if not val:
                errors.append(f"Requirement 5 failed (Scene {sc_num}): '{field}' is missing or empty.")

        # Narration phrasing bans & per-scene word count scaling
        narration = str(sc.get("narration", "")).strip()
        if not narration:
            errors.append(f"Scene {sc_num}: narration is missing or empty.")
        else:
            words = narration.split()
            scene_word_count = len(words)
            total_words += scene_word_count

            # Per-scene pacing check scaled to duration (~2.8 words/sec)
            expected_scene_words = dur * 2.8
            min_scene_words = max(4, int(expected_scene_words * 0.70))
            max_scene_words = max(min_scene_words + 2, int(expected_scene_words * 1.30) + 1)
            if scene_word_count < min_scene_words or scene_word_count > max_scene_words:
                errors.append(
                    f"Requirement 3 failed (Scene {sc_num}): Scene narration word count ({scene_word_count} words) deviates from target pace for {dur:.2f}s "
                    f"(expected ~{expected_scene_words:.1f} words, allowed range: [{min_scene_words}, {max_scene_words}])."
                )

            sentences = [s.strip() for s in re.split(r'[.!?]+', narration) if s.strip()]
            for s in sentences:
                if banned_year.search(s):
                    errors.append(f"Requirement 4 failed (Scene {sc_num}): Narration sentence opens with banned 'In [year]' phrasing: '{s}'.")
                if banned_this_it.search(s):
                    errors.append(f"Requirement 4 failed (Scene {sc_num}): Narration sentence opens with banned 'This/It was' phrasing: '{s}'.")
                if banned_proper_noun_was.search(s):
                    errors.append(f"Requirement 4 failed (Scene {sc_num}): Narration sentence opens with passive proper-noun 'X was/were' phrasing: '{s}'.")

    # Global pacing check: total narration word count within 15% of (total_duration_seconds * 2.8)
    if total_duration > 0:
        ideal_words = total_duration * 2.8
        min_words = int(ideal_words * 0.85)
        max_words = int(ideal_words * 1.15)
        if total_words < min_words or total_words > max_words:
            errors.append(
                f"Requirement 3 failed: Total narration word count ({total_words} words) is outside 15% of target pace "
                f"({ideal_words:.1f} words for {total_duration:.1f}s total duration, acceptable range: [{min_words}, {max_words}])."
            )

    return errors


def generate_storyboard_with_gemini(
    topic_data: dict,
    model: str = "gemini-3.6-flash",
    api_key: str = None,
    max_retries: int = 3
) -> dict:
    """Calls Google Gemini API via google-genai to generate a fresh storyboard, validating output and retrying with corrective feedback."""
    if not HAS_GEMINI:
        raise RuntimeError("google-genai package is not installed. Please install via: pip install google-genai")

    resolved_api_key = get_gemini_api_key(api_key)
    if not resolved_api_key:
        raise ValueError(
            f"GEMINI_API_KEY (or GOOGLE_API_KEY) environment variable is required to generate storyboards via Gemini (model {model}). "
            "Please set GEMINI_API_KEY or provide --api-key."
        )

    client = genai.Client(api_key=resolved_api_key)
    normalized_id = normalize_topic_id(topic_data.get("id", "tactical-anomaly"))

    system_prompt = (
        "You are an expert historical documentary screenwriter and cinematographer specializing in "
        "high-tempo vertical short-form visual storytelling (1080x1920, 9:16 for TikTok/Shorts/Reels).\n\n"
        "Your task: Convert the given historical tactical warfare anomaly into a 12 to 16 micro-scene documentary storyboard JSON.\n\n"
        "STRICT REQUIREMENTS YOU MUST SATISFY:\n"
        "1. Scene Count: Exactly 12 to 16 scenes (recommend 13 or 14).\n"
        "2. Narrative Beat Types & Variable Scene Durations (Pacing tied to narrative weight):\n"
        "   Every scene MUST declare a 'beat_type' matching its narrative role, with 'target_duration' strictly within its range:\n"
        "   - 'establishing' (Scenes 1-3: context, hook, premise): 2.0 to 2.8 seconds (~5-8 words)\n"
        "   - 'rising_tension' (Scenes 4-8: mechanical reveal, tactical dilemma, assembly): 2.8 to 3.5 seconds (~8-10 words)\n"
        "   - 'climax_impact' (Scenes 9-11: decisive strike, catastrophic collapse, payoff hold): 3.5 to 5.0 seconds (~10-14 words)\n"
        "   - 'resolution_loop' (Scenes 12+: historical aftermath, tactical verdict, infinite loop hook): 2.5 to 3.5 seconds (~7-10 words)\n"
        "3. Strict Shot Scale Rotation: Cycle through these 4 scales in exact order (idx % 4):\n"
        "   - Scene 1: 'Extreme Macro Close-Up'\n"
        "   - Scene 2: 'Low-Angle Grounded POV'\n"
        "   - Scene 3: 'Wide Tactical Action'\n"
        "   - Scene 4: 'Medium Tension Portrait'\n"
        "   - Scene 5: 'Extreme Macro Close-Up' ... and repeat.\n"
        "4. Speech Pacing & Word Count: Pacing must approximate ~2.8 words/second. Scale each scene's narration word count "
        "   to that scene's own target_duration. Total words across all scenes must be within 15% of (total_duration_seconds * 2.8).\n"
        "5. STRICT BAN ON ENCYCLOPEDIA PHRASING: NEVER begin any sentence with 'In [year]' (e.g. 'In 213 BC...'), "
        "   'This/It was' ('This was...', 'It was...'), or passive proper-noun exposition ('Marcellus was...', 'Archimedes was...', 'The Consul was...'). "
        "   Always open every sentence with direct sensory, material, or tactical physical action.\n"
        "6. Every scene MUST include:\n"
        "   - scene_id (1, 2, ...)\n"
        "   - beat_type ('establishing', 'rising_tension', 'climax_impact', or 'resolution_loop')\n"
        "   - shot_scale (matching the required rotation)\n"
        "   - target_duration (float strictly within beat_type range)\n"
        "   - narration (scaled to duration, adhering strictly to phrasing bans)\n"
        "   - tactile_material_action (a physical, textural detail — what hands, tools, ropes, iron, wood, or materials are doing)\n"
        "   - visual_description (rich atmospheric scene description)\n"
        "   - camera_angle (e.g., 'extreme macro close-up, shallow depth of field', 'low-angle grounded POV')\n"
        "   - focal_length (e.g., '85mm macro lens', '24mm anamorphic wide', '35mm wide prime', '50mm prime')\n"
        "   - lighting_scheme (e.g., 'cold silver moonlight and chiaroscuro shadows on dark iron')\n"
        "   - camera_motion (e.g., 'slow push-in', 'tracking pan right', 'subtle pedestal tilt-down', 'snap zoom')\n"
        "   - sound_fx_cue (e.g., 'sea_spray_and_chains', 'timber_shatter_impact', 'roaring_fire')\n\n"
        "OUTPUT FORMAT: Return ONLY valid JSON with no markdown wrapping or conversational commentary."
    )

    user_prompt = (
        f"Generate the documentary storyboard for this historical tactical anomaly:\n\n"
        f"Topic ID: {normalized_id}\n"
        f"Title: {topic_data.get('title', 'Tactical Anomaly')}\n"
        f"Category: {topic_data.get('category', 'military_history')}\n"
        f"Historical Era: {topic_data.get('historical_era', 'Ancient Warfare')}\n"
        f"Core Anomaly: {topic_data.get('core_anomaly', '')}\n"
        f"Hook / Hookline: {topic_data.get('hook_hookline', '')}\n"
        f"Key Facts: {json.dumps(topic_data.get('key_facts', []), ensure_ascii=False)}\n"
        f"Visual Motifs: {json.dumps(topic_data.get('visual_motifs', []), ensure_ascii=False)}\n"
    )

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        response_mime_type="application/json",
        temperature=0.7,
    )

    contents = [
        types.Content(role="user", parts=[types.Part.from_text(text=user_prompt)])
    ]

    for attempt in range(1, max_retries + 1):
        print(f"[INFO] Invoking Gemini API (model: {model}, attempt {attempt}/{max_retries})...")
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=config
            )
        except Exception as e:
            print(f"[ERROR] Gemini API call failed on attempt {attempt}: {e}", file=sys.stderr)
            if attempt == max_retries:
                raise
            time.sleep(2 * attempt)
            continue

        raw_text = response.text or ""

        try:
            storyboard_raw = extract_json(raw_text)
        except Exception as e:
            print(f"[WARN] Failed to parse JSON response on attempt {attempt}: {e}", file=sys.stderr)
            if attempt == max_retries:
                raise ValueError(f"Could not parse valid JSON from LLM after {max_retries} attempts. Raw response: {raw_text[:200]}...")
            contents.append(types.Content(role="model", parts=[types.Part.from_text(text=raw_text)]))
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=f"Failed to parse JSON: {e}. Output ONLY valid, parseable JSON matching the required schema.")]))
            continue

        errors = validate_storyboard_data(storyboard_raw)
        if not errors:
            print(f"[SUCCESS] Generated storyboard passed all programmatic validation rules on attempt {attempt}.")
            return storyboard_raw

        print(f"[WARN] Storyboard validation failed on attempt {attempt} with {len(errors)} error(s):", file=sys.stderr)
        for err in errors[:5]:
            print(f"  - {err}", file=sys.stderr)

        if attempt < max_retries:
            corrective_feedback = (
                "Your previous storyboard output had the following validation errors that MUST be strictly fixed:\n"
                + "\n".join(f"- {err}" for err in errors)
                + "\n\nPlease revise the storyboard so that ALL criteria are met, and return ONLY the corrected JSON."
            )
            contents.append(types.Content(role="model", parts=[types.Part.from_text(text=raw_text)]))
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=corrective_feedback)]))
        else:
            raise ValueError(f"Storyboard validation failed after {max_retries} attempts: {'; '.join(errors)}")


def compile_final_storyboard(storyboard_data: dict, topic_data: dict, engine: str = "gemini_llm", model: str = "gemini-3.6-flash") -> dict:
    """
    Compiles validated storyboard into the canonical state/storyboard.json schema.
    Enforces that CINEMA_LENS_SUFFIX is placed at the START of diffusion_prompt,
    and explicitly stamps generation_engine ('gemini_llm' vs 'algorithmic_fallback').
    """
    topic_id = topic_data.get("id", "tactical-anomaly")
    resolved_id = normalize_topic_id(topic_id)
    title = storyboard_data.get("title") or topic_data.get("title") or "Historical Tactical Anomaly"
    raw_scenes = storyboard_data.get("scenes", [])

    compiled_scenes = []
    current_time = 0.0
    total_words = 0

    for idx, sc in enumerate(raw_scenes):
        scale = SHOT_SCALES[idx % 4]
        scene_id = idx + 1
        dur = round(float(sc.get("target_duration", 2.8)), 2)
        end_time = round(current_time + dur, 2)
        time_range = f"{current_time:.1f}-{end_time:.1f}"
        current_time = end_time

        narration = str(sc.get("narration", "")).strip()
        total_words += len(narration.split())

        tactile = str(sc.get("tactile_material_action", "")).strip()
        visual_desc = str(sc.get("visual_description", "")).strip()
        angle = str(sc.get("camera_angle", "cinematic wide shot")).strip()
        focal = str(sc.get("focal_length", "35mm prime")).strip()
        lighting = str(sc.get("lighting_scheme", "volumetric chiaroscuro lighting")).strip()
        motion = str(sc.get("camera_motion", "slow push-in")).strip()
        sound_fx = str(sc.get("sound_fx_cue", "ambient_drone")).strip()

        # REQUIREMENTS 5 & 7: Place CINEMA_LENS_SUFFIX at the START of diffusion_prompt
        # Early token weighting in diffusion text encoders anchors visual style across all scenes.
        full_diffusion_prompt = (
            f"{CINEMA_LENS_SUFFIX}, {scale}. "
            f"{tactile}. {visual_desc}, {angle}, {focal}, {lighting}. Camera motion: {motion}."
        )

        compiled_scenes.append({
            "scene_id": scene_id,
            "beat_type": str(sc.get("beat_type", "establishing")).strip(),
            "shot_scale": scale,
            "time_range": time_range,
            "target_duration": dur,
            "narration": narration,
            "tactile_material_action": tactile,
            "visual_description": visual_desc,
            "camera_angle": angle,
            "focal_length": focal,
            "lighting_scheme": lighting,
            "camera_motion": motion,
            "sound_fx_cue": sound_fx,
            "visual_prompt": full_diffusion_prompt,
            "diffusion_prompt": full_diffusion_prompt,
            "negative_prompt": NEGATIVE_PROMPT
        })

    total_duration = round(current_time, 2)

    return {
        "topic_id": resolved_id,
        "title": title,
        "generation_engine": engine,
        "generation_model": model if engine == "gemini_llm" else None,
        "target_duration_seconds": total_duration,
        "total_words": total_words,
        "scene_count": len(compiled_scenes),
        "scenes": compiled_scenes
    }


def synthesize_algorithmic_storyboard(topic_data: dict) -> dict:
    """
    Autonomous documentary screenwriter generator that dynamically constructs a fully compliant 13-scene
    variable-pacing storyboard from topic_data without hardcoded topic templates.
    """
    title = topic_data.get("title", "Historical Tactical Anomaly")
    core = topic_data.get("core_anomaly", "A legendary stratagem turned the tide of battle.")
    hook = topic_data.get("hook_hookline", "Ancient warriors deployed an unprecedented mechanical weapon.")
    facts = topic_data.get("key_facts", [])
    motifs = topic_data.get("visual_motifs", [])
    era = topic_data.get("historical_era", "Ancient Warfare")

    f0 = facts[0] if len(facts) > 0 else core
    f1 = facts[1] if len(facts) > 1 else core
    f2 = facts[2] if len(facts) > 2 else core

    m0 = motifs[0] if len(motifs) > 0 else "armored warriors and banners on stormy battlefield"
    m1 = motifs[1] if len(motifs) > 1 else "heavy timber and iron mechanics under volumetric torchlight"
    m2 = motifs[2] if len(motifs) > 2 else "violent impact and shattering defenses"
    m3 = motifs[3] if len(motifs) > 3 else "retreating ranks under dark dramatic skies"

    # Clean hook of any banned openers
    clean_hook = re.sub(r"^in\s+\d{1,4}\s*(?:bc|ad)?\s*,?\s*", "", hook, flags=re.IGNORECASE).strip()
    clean_hook = clean_hook[0].upper() + clean_hook[1:] if clean_hook else "Enemy forces deployed under cover of night."
    hook_words = clean_hook.split()
    if len(hook_words) > 7:
        clean_hook = " ".join(hook_words[:7]).rstrip(",;:-") + "."

    clean_title = re.sub(r"^(?:The\s+)?", "", title).split(":")[0].strip()

    # 13-beat structure dynamically composed from topic facts:
    beat_configs = [
        # Establishing (2.0s - 2.8s, ~5-7 words)
        ("establishing", 2.4, clean_hook, f"Cold mist rising across {m0}", f"Macro perspective of {m0}", "extreme macro close-up, shallow depth of field", "85mm macro lens", "cold silver moonlight on dark metal", "slow push-in", "distant_war_horns"),
        ("establishing", 2.5, f"Armies clashed along the disputed frontier.", f"Drenched earth vibrating under rhythmic marching boots", f"Grounded perspective of {m0}", "low-angle grounded POV", "24mm anamorphic wide", "flickering bronze lantern light", "tracking pan right", "rhythmic_drum_beat"),
        ("establishing", 2.6, f"Defenders faced overwhelming tactical superior forces.", f"Rough banners snapping in cold storm wind", f"Tactical layout showing {m0}", "wide tactical action view", "35mm wide prime", "overcast dawn mist cutting across ramparts", "subtle pedestal tilt-down", "wind_howl"),

        # Rising Tension (2.8s - 3.5s, ~7-9 words)
        ("rising_tension", 3.0, f"Commanders prepared the decisive secret weapon.", f"Hands tightening grip on leather shield straps", f"Medium focus showing {m1}", "medium tension portrait", "50mm natural prime", "chiaroscuro shadows across hardened bronze armor", "slow push-in", "leather_creak"),
        ("rising_tension", 3.2, f"Engineers primed {clean_title[:28]} for immediate deployment.", f"Heavy mechanics swinging into place under tension", f"Mechanical detail of {m1}", "extreme macro close-up, shallow depth of field", "85mm macro lens", "amber brazier glow illuminating wooden gear teeth", "tracking pan right", "timber_winch_strain"),
        ("rising_tension", 3.0, f"Forward ranks advanced without suspecting the hidden trap.", f"Pitch resin sizzling against hot iron rivets", f"Grounded view of {f0}", "low-angle grounded POV", "24mm anamorphic wide", "harsh brazier sparks cutting through shadows", "subtle pedestal tilt-down", "iron_creak"),
        ("rising_tension", 3.1, f"The vanguard marched directly into the targeted killzone.", f"Foot soldiers wading through churning foam and mud", f"Wide view of {m1}", "wide tactical action view", "35mm wide prime", "deep blue twilight with volumetric fog", "slow push-in", "muffled_footsteps"),
        ("rising_tension", 3.2, f"Defenders unleashed the stratagem with sudden explosive force.", f"Taut ropes snapping free from forged iron triggers", f"Tense portrait of {f1}", "medium tension portrait", "50mm natural prime", "dramatic rim lighting on determined faces", "tracking pan right", "rope_snap_impact"),

        # Climax Impact (3.5s - 5.0s, ~9-12 words)
        ("climax_impact", 4.2, f"Devastating impact shattered the enemy vanguard, breaking defensive lines across the battlefield.", f"Shattered timber and shields bursting under extreme violent torque", f"Violent kinetic climax showing {m2}", "extreme macro close-up, shallow depth of field", "85mm macro lens", "roaring orange firelight catching flying splinters", "slow push-in", "catastrophic_timber_shatter"),
        ("climax_impact", 3.8, f"Panic tore through invading ranks as counter-measures overwhelmed all resistance.", f"Armored bodies tumbling through smoke and churning mud", f"Low upward view of {m2}", "low-angle grounded POV", "24mm anamorphic wide", "flashing torch embers illuminating violent impacts", "tracking pan right", "crushing_impact_splash"),
        ("climax_impact", 4.0, f"Unstoppable tactical surprise shattered enemy morale, turning disciplined lines into frantic retreat.", f"Panicked soldiers dropping weapons into the mud", f"Wide panoramic destruction of {f2}", "wide tactical action view", "35mm wide prime", "smoky chiaroscuro silhouette against burning wreckage", "subtle pedestal tilt-down", "screams_and_fire"),

        # Resolution / Loop (2.5s - 3.5s, ~7-10 words)
        ("resolution_loop", 3.0, f"The surviving invaders retreated across the shattered battleground.", f"Battered helmet resting half-submerged in wet shoreline sand", f"Solemn aftermath portrait showing {m3}", "medium tension portrait", "50mm natural prime", "fading twilight rim light on tranquil waves", "slow push-in", "distant_surf"),
        ("resolution_loop", 2.8, f"Ancient chronicles permanently recorded {clean_title[:28]} as decisive warfare.", f"Lone iron relic resting motionless over quiet battlements", f"Haunting final frame linking to {m3}", "extreme macro close-up, shallow depth of field", "85mm macro lens", "cold silver moonlight on damp stone", "tracking pan right", "ambient_drone")
    ]

    scenes = []
    for idx, (btype, dur, narr, tactile, vdesc, angle, focal, light, motion, sfx) in enumerate(beat_configs):
        scale = SHOT_SCALES[idx % 4]
        scenes.append({
            "scene_id": idx + 1,
            "beat_type": btype,
            "shot_scale": scale,
            "target_duration": dur,
            "narration": narr,
            "tactile_material_action": tactile,
            "visual_description": vdesc,
            "camera_angle": angle,
            "focal_length": focal,
            "lighting_scheme": light,
            "camera_motion": motion,
            "sound_fx_cue": sfx
        })

    return {
        "topic_id": topic_data.get("id", "tactical-anomaly"),
        "title": title,
        "scenes": scenes
    }


def generate_storyboard(topic_path: Path, output_path: Path, model: str = "gemini-3.6-flash", api_key: str = None):
    with open(topic_path, "r", encoding="utf-8") as f:
        topic_data = json.load(f)

    storyboard_data = None
    engine = "gemini_llm"
    try:
        storyboard_data = generate_storyboard_with_gemini(
            topic_data=topic_data,
            model=model,
            api_key=api_key
        )
    except (ValueError, RuntimeError, Exception) as e:
        print(f"[WARN] Gemini API unavailable or failed ({e}). Engaging autonomous algorithmic screenwriter generator...", file=sys.stderr)
        engine = "algorithmic_fallback"
        storyboard_data = synthesize_algorithmic_storyboard(topic_data)
        errors = validate_storyboard_data(storyboard_data)
        if errors:
            raise ValueError(f"Algorithmic storyboard failed validation: {errors}")

    final_sb = compile_final_storyboard(storyboard_data, topic_data, engine=engine, model=model)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_sb, f, indent=2, ensure_ascii=False)

    print(f"[SUCCESS] Generated storyboard ({final_sb['scene_count']} scenes, {final_sb['total_words']} words, {final_sb['target_duration_seconds']}s, engine: {engine}) written to: {output_path.resolve()}")


def main():
    parser = argparse.ArgumentParser(description="Generate modern documentary storyboard via Google Gemini (gemini-3.6-flash).")
    parser.add_argument("--topic", type=str, default="state/topic.json", help="Path to input topic JSON.")
    parser.add_argument("--output", type=str, default="state/storyboard.json", help="Destination storyboard JSON.")
    parser.add_argument("--model", type=str, default="gemini-3.6-flash", help="Gemini model (e.g. gemini-3.6-flash, gemini-3.5-flash).")
    parser.add_argument("--api-key", type=str, default=None, help="Gemini API key (defaults to GEMINI_API_KEY or GOOGLE_API_KEY env).")

    args = parser.parse_args()
    topic_path = Path(args.topic)
    if not topic_path.exists():
        print(f"[ERROR] Topic file '{topic_path}' not found.", file=sys.stderr)
        sys.exit(1)

    generate_storyboard(
        topic_path=topic_path,
        output_path=Path(args.output),
        model=args.model,
        api_key=args.api_key
    )


if __name__ == "__main__":
    main()
