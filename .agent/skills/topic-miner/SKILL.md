---
name: topic-miner
description: Query and select niche historical warfare topics (tactical anomalies, forgotten siege engines, bizarre military inventions) and output a standardized topic state JSON.
---

# Topic Miner Skill

This skill queries, evaluates, and structures niche topics from military history, ancient warfare, and tactical anomalies into a structured `state/topic.json` file used by downstream short-form video generation pipelines.

## Target Domains
- **Forgotten Siege Engines & Mechanical Artillery**: Archimedes' Claw, Helepolis of Rhodes, Roman Sambuca, Warwolf trebuchet, Greek Fire siphon projectors, Gastraphetes.
- **Tactical Anomalies & Asymmetric Stratagems**: Battle of Carrhae arrow camels, Pelusium cat shields, Silver Shields treachery, Teutoburg forest choke traps, elephant panic counter-measures (flaming pigs).
- **Bizarre Military Inventions**: Corvus naval spike bridge, Byzantine Cheirosiphona hand-held flamethrowers, Korean Hwacha rocket carts, Hussite War Wagons.

## Workflow Instructions

1. **Topic Generation / Extraction**:
   - Run `python .agent/skills/topic-miner/scripts/mine_topics.py` with optional category flags or query terms.
   - Alternatively, evaluate an ad-hoc historical scenario against the **Engagement Criteria**:
     * **High Shock/Curiosity Factor**: Can it be summarized in a 3-second hook?
     * **Visual Drama**: Does it lend itself to dark, atmospheric, cinematic imagery (smoke, bronze, iron, flame, desert storms)?
     * **Tactical Substance**: Is there a concrete tactical problem and an unconventional mechanical/tactical resolution?

2. **Output Specification**:
   Output must be saved to `state/topic.json` conforming to this schema:
   ```json
   {
     "id": "archimedes-claw",
     "title": "The Claw of Archimedes: The Iron Hand That Lifted Roman Warships",
     "category": "forgotten_siege_engine",
     "historical_era": "Second Punic War (214-212 BC)",
     "core_anomaly": "A hidden city-wall crane dropped an iron grappling claw that gripped Roman galleys by the prow, lifted them vertically out of the sea, and dropped them to capsize.",
     "hook_hookline": "In 213 BC, the Roman navy attacked Syracuse—only to be plucked out of the ocean by an invisible iron hand.",
     "key_facts": [
       "Designed by the mathematician Archimedes during the Siege of Syracuse.",
       "Operated via massive counterweighted cranes concealed behind seaward battlements.",
       "Terrified Roman sailors so badly they fled whenever a beam poked over Syracuse's walls."
     ],
     "visual_motifs": [
       "Carthaginian and Roman quinqueremes on stormy Aegean waves",
       "Massive bronze and timber cranes behind stone fortifications",
       "A Roman warship dangling vertically in mid-air",
       "Shattered oars, churning sea foam, and panicked legionaries"
     ]
   }
   ```

3. **Validation**:
   Ensure `state/topic.json` exists and is valid JSON before handing off to `video-scriptor`.
