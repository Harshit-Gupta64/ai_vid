---
name: video-scriptor
description: Convert a historical military anomaly topic into a high-retention 5-scene vertical cinematic storyboard JSON with explicit cinematographic camera grammar for TikTok/Shorts/Reels.
---

# Cinematic Storyboarder Skill (video-scriptor)

This skill transforms a tactical history topic from `state/topic.json` into an engaging, high-retention 5-scene vertical storyboard saved at `state/storyboard.json`. It enforces strict vertical pacing, retention mechanics, and professional filmic camera grammar.

## Core Directives & Constraints

1. **Format**: Vertical 9:16 aspect ratio (1080x1920).
2. **Total Target Duration**: ~45 seconds total (~130 words of narration at ~165 WPM).
3. **Pacing Structure (5 Scenes)**:
   - **Scene 1 (0-3s | ~10-12 words)**: **Visual Hook**. High-impact visual paradox or shocking premise. Must stop the scroll in under 1.5 seconds.
   - **Scene 2 (3-12s | ~25 words)**: **Tactical Dilemma**. The seemingly insurmountable threat or conventional military stalemate.
   - **Scene 3 (12-24s | ~35 words)**: **The Secret Weapon / Stratagem**. The mechanical invention, forbidden weapon, or asymmetric logistical trick.
   - **Scene 4 (24-38s | ~40 words)**: **The Climax & Battlefield Impact**. The chaotic execution, structural collapse, or panic of the enemy force.
   - **Scene 5 (38-45s | ~18 words)**: **The Tactical Legacy & Loop Hook**. Historical verdict and a seamless narrative phrase that loops naturally back to Scene 1.

4. **Explicit Cinematic Camera Grammar**:
   Every scene MUST specify explicit cinematographic parameters:
   - **`camera_angle`**: e.g., `low-angle hero shot`, `Dutch tilt`, `high-angle tactical view`, `worm's-eye perspective`, `extreme close-up`.
   - **`focal_length`**: e.g., `24mm anamorphic wide`, `35mm documentary`, `50mm natural`, `85mm portrait shallow depth of field`, `135mm telephoto compressed perspective`.
   - **`lighting_scheme`**: e.g., `chiaroscuro rim lighting`, `volumetric god rays cutting through sea spray`, `backlit dust motes`, `harsh lantern glow with deep shadows`, `twilight chiaroscuro silhouette`.
   - **`camera_motion`**: e.g., `slow push-in`, `subtle pedestal pan`, `tracking pull-out`, `whip pan right`, `high-angle tracking tilt`.

5. **Cinematic Visual Prompt Synthesis**:
   The agent MUST naturally synthesize the camera grammar keys directly into the `visual_prompt` (and `diffusion_prompt`) alongside the enforced stylistic suffix:
   `{core visual description}, shot on {focal_length}, {camera_angle}, {lighting_scheme}, --ar 9:16, dark atmospheric oil painting, volumetric lighting, high fidelity`

## Schema Specification (`state/storyboard.json`)

```json
{
  "topic_id": "archimedes-claw",
  "title": "The Claw of Archimedes: Rome's Maritime Nightmare",
  "target_duration_seconds": 45.0,
  "total_words": 130,
  "scenes": [
    {
      "scene_id": 1,
      "time_range": "0.0-3.0",
      "target_duration": 3.0,
      "narration": "In 213 BC, Rome's invincible navy was grabbed by an invisible iron hand.",
      "visual_description": "A colossal dark iron claw suspended by thick chains descending from coastal fortress walls, gripping the wooden prow of an ancient Roman war galley in stormy waters.",
      "camera_angle": "worm's-eye low-angle shot",
      "focal_length": "24mm anamorphic wide",
      "lighting_scheme": "volumetric god rays cutting through dark storm clouds and sea spray",
      "camera_motion": "dramatic slow push-in",
      "visual_prompt": "A colossal dark iron claw suspended by thick chains descending from coastal fortress walls, gripping the wooden prow of an ancient Roman war galley in stormy waters, dramatic ocean spray, shot on 24mm anamorphic wide, worm's-eye low-angle shot, volumetric god rays cutting through dark storm clouds and sea spray, --ar 9:16, dark atmospheric oil painting, volumetric lighting, high fidelity",
      "diffusion_prompt": "A colossal dark iron claw suspended by thick chains descending from coastal fortress walls, gripping the wooden prow of an ancient Roman war galley in stormy waters, dramatic ocean spray, shot on 24mm anamorphic wide, worm's-eye low-angle shot, volumetric god rays cutting through dark storm clouds and sea spray, --ar 9:16, dark atmospheric oil painting, volumetric lighting, high fidelity",
      "sound_fx_cue": "thunder_sea_swell_creaking_chains"
    },
    {
      "scene_id": 2,
      "time_range": "3.0-12.0",
      "target_duration": 9.0,
      "narration": "Consul Marcellus had sixty quinqueremes armed with boarding towers, expecting Syracuse to fall in hours. But mathematician Archimedes had secretly turned the entire city wall into a machine.",
      "visual_description": "Armored Roman naval fleet advancing towards towering ancient Greek limestone sea fortifications under stormy skies.",
      "camera_angle": "high-angle tactical wide view",
      "focal_length": "35mm cinematic wide",
      "lighting_scheme": "overcast diffuse tempest light with dramatic broken sunbeams",
      "camera_motion": "slow wide tracking pan left",
      "visual_prompt": "Armored Roman naval fleet advancing towards towering ancient Greek limestone sea fortifications, dark stormy clouds, Roman legionaries with bronze helmets and red plumes on wooden decks, shot on 35mm cinematic wide, high-angle tactical wide view, overcast diffuse tempest light with dramatic broken sunbeams, --ar 9:16, dark atmospheric oil painting, volumetric lighting, high fidelity",
      "diffusion_prompt": "Armored Roman naval fleet advancing towards towering ancient Greek limestone sea fortifications, dark stormy clouds, Roman legionaries with bronze helmets and red plumes on wooden decks, shot on 35mm cinematic wide, high-angle tactical wide view, overcast diffuse tempest light with dramatic broken sunbeams, --ar 9:16, dark atmospheric oil painting, volumetric lighting, high fidelity",
      "sound_fx_cue": "war_horns_distant_drums"
    },
    {
      "scene_id": 3,
      "time_range": "12.0-24.0",
      "target_duration": 12.0,
      "narration": "Hidden behind the battlements were colossal counterweight cranes. As Roman galleys drew near, iron talons were dropped from the ramparts, clamping deep into timber hulls.",
      "visual_description": "Internal view behind Syracuse battlements showing Archimedes' massive wooden crane levers and iron pulleys operated by engineers.",
      "camera_angle": "Dutch tilt medium shot",
      "focal_length": "50mm natural prime",
      "lighting_scheme": "harsh brazier lantern glow casting long dramatic chiaroscuro shadows",
      "camera_motion": "subtle pedestal tilt-down",
      "visual_prompt": "Inside an ancient Greek stone citadel, massive wooden crane levers and iron pulleys operated by engineers, glowing braziers, heavy ropes straining under immense counterweight tension, tactical blueprints on stone tables, shot on 50mm natural prime, Dutch tilt medium shot, harsh brazier lantern glow casting long dramatic chiaroscuro shadows, --ar 9:16, dark atmospheric oil painting, volumetric lighting, high fidelity",
      "diffusion_prompt": "Inside an ancient Greek stone citadel, massive wooden crane levers and iron pulleys operated by engineers, glowing braziers, heavy ropes straining under immense counterweight tension, tactical blueprints on stone tables, shot on 50mm natural prime, Dutch tilt medium shot, harsh brazier lantern glow casting long dramatic chiaroscuro shadows, --ar 9:16, dark atmospheric oil painting, volumetric lighting, high fidelity",
      "sound_fx_cue": "timber_groaning_winch_grinding"
    },
    {
      "scene_id": 4,
      "time_range": "24.0-38.0",
      "target_duration": 14.0,
      "narration": "With counterweights released, the cranes hoisted sixty-ton warships completely out of the water. Suspended upright in mid-air, legionaries tumbled into the sea before the release mechanism dropped the hulls to shatter against the rocks.",
      "visual_description": "A sixty-ton Roman quinquereme hoisted completely vertical above sea waves by an enormous iron claw crane, spilling armored legionaries into foaming water.",
      "camera_angle": "dynamic low-angle upward tracking shot",
      "focal_length": "24mm anamorphic wide",
      "lighting_scheme": "chiaroscuro rim lighting catching flying sea spray and splintering wood",
      "camera_motion": "high-angle tracking tilt",
      "visual_prompt": "A Roman quinquereme warship suspended vertically in the air above churning sea waves by an enormous iron claw crane, armored soldiers falling from wooden decks, violent splashes and flying timber splinters, shot on 24mm anamorphic wide, dynamic low-angle upward tracking shot, chiaroscuro rim lighting catching flying sea spray and splintering wood, --ar 9:16, dark atmospheric oil painting, volumetric lighting, high fidelity",
      "diffusion_prompt": "A Roman quinquereme warship suspended vertically in the air above churning sea waves by an enormous iron claw crane, armored soldiers falling from wooden decks, violent splashes and flying timber splinters, shot on 24mm anamorphic wide, dynamic low-angle upward tracking shot, chiaroscuro rim lighting catching flying sea spray and splintering wood, --ar 9:16, dark atmospheric oil painting, volumetric lighting, high fidelity",
      "sound_fx_cue": "catastrophic_wood_splintering_splash"
    },
    {
      "scene_id": 5,
      "time_range": "38.0-45.0",
      "target_duration": 7.0,
      "narration": "Roman soldiers fled if even a wooden beam poked over the walls. Archimedes proved physics could crush an empire.",
      "visual_description": "Elderly philosopher Archimedes in draped robes standing silhouetted atop high fortress ramparts looking out at shattered burning Roman fleet.",
      "camera_angle": "low-angle hero silhouette shot",
      "focal_length": "85mm telephoto shallow depth of field",
      "lighting_scheme": "backlit twilight moonlit glow with embers rising from smoking harbor",
      "camera_motion": "slow pull-out to black",
      "visual_prompt": "Elderly Greek philosopher Archimedes in draped robes standing silhouetted atop a fortress wall overlooking burning shattered ships in twilight harbor, smoke rising into dramatic moonlit sky, shot on 85mm telephoto shallow depth of field, low-angle hero silhouette shot, backlit twilight moonlit glow with embers rising from smoking harbor, --ar 9:16, dark atmospheric oil painting, volumetric lighting, high fidelity",
      "diffusion_prompt": "Elderly Greek philosopher Archimedes in draped robes standing silhouetted atop a fortress wall overlooking burning shattered ships in twilight harbor, smoke rising into dramatic moonlit sky, shot on 85mm telephoto shallow depth of field, low-angle hero silhouette shot, backlit twilight moonlit glow with embers rising from smoking harbor, --ar 9:16, dark atmospheric oil painting, volumetric lighting, high fidelity",
      "sound_fx_cue": "eerie_wind_resonance"
    }
  ]
}
```

## Generation & Verification Procedure

1. Inspect `state/topic.json`.
2. Construct the 5-scene narrative ensuring:
   - Word count is between 120 and 135 words (~45s target duration).
   - Every scene includes explicit `camera_angle`, `focal_length`, `lighting_scheme`, and `camera_motion`.
   - The `visual_prompt` and `diffusion_prompt` synthesize the scene description, focal length, camera angle, and lighting scheme, ending with `--ar 9:16, dark atmospheric oil painting, volumetric lighting, high fidelity`.
   - Scene 1 narration is punchy, shocking, and under 3.0 seconds.
3. Save output to `state/storyboard.json`.
4. Validate JSON syntax and key presence.
