# Autonomous Execution Log & Architectural Decisions (DECISIONS.md)

**Session Mode**: Fully Unattended Operator-Free Run  
**Last Updated**: 2026-09-05T12:24:00+05:30  

This log records every technical judgment call, model selection, and tradeoff made autonomously during this unattended run without human intervention.

---

### Decision 1: Unattended Role Transition Without Human Gate
- **Context**: Operator is unavailable to review PLAN_V2.md before implementation.
- **Choice**: Transitioned automatically from Role 1 (Architect) to Role 2 (Implementer) based on verified criteria.
- **Rationale**: Strict compliance with unattended orchestration mandate. All planned changes are fully documented in PLAN_V2.md and re-derived from actual repo inspections.

### Decision 2: Gemini Model Selection (`gemini-3.6-flash`)
- **Context**: `gemini-2.5-flash` was deprecated by upstream API (404 NOT_FOUND). Candidate probe of `gemini-3.8-flash` returned temporary 503 UNAVAILABLE.
- **Choice**: Selected `gemini-3.6-flash` (confirmed available in `client.models.list()`, fast, stable, zero 404/503 errors).
- **Fallback Hierarchy**: `["gemini-3.6-flash", "gemini-3.8-flash", "gemini-flash-latest"]`.

### Decision 3: Availability-Over-Strictness on Missing API Key
- **Context**: When `GEMINI_API_KEY` is missing or uncallable, should the batch runner abort the entire queue or fall back?
- **Choice**: Log a loud console warning and mark the topic as `⚠️ DEGRADED (FALLBACK)` in `BATCH_REPORT.md` while allowing the batch run to proceed.
- **Rationale**: In unattended production environments, complete pipeline halting on single key expiration causes silent job death. Marking degraded state provides full audit transparency without crashing downstream stages.

### Decision 4: Post-TTS Lifecycle Validation Loop & TTS Floor Clamping
- **Context**: Edge-TTS synthesis and trailing silence removal can compress brief sentences below the 2.0s establishing beat floor.
- **Choice**:
  1. `synthesize.py` applies a visual scene hold floor: `scene_dur = max(scene_dur, 2.0)`.
  2. `deep_qa_inspector.py` adds a hard symmetric cut floor audit (`short_cuts = [d for d in durations if d < 2.0]`).
  3. `run_batch.py` re-runs `validate_storyboard_data()` post-TTS.

### Decision 5: Dynamic Topic Prose Synthesis in Algorithmic Fallback
- **Context**: The legacy algorithmic fallback used hardcoded Archimedes claw sentences regardless of the chosen topic.
- **Choice**: Refactored synthesize_algorithmic_storyboard() to extract 	actical_anomaly, isual_motifs, historical_context, and category directly from 	opic.json and build contextual, topic-specific prose dynamically across all 13-14 scenes.
- **Rationale**: Guarantees that if the pipeline is forced to degrade to offline fallback mode, it produces historically relevant, non-repetitive videos rather than mismatched Archimedes footage.

### Decision 6: Batch Report Engine Tagging & Degraded Visual Indicators
- **Context**: When a batch completes with fallback storyboards, operators could mistake algorithmic fallback for LLM generation.
- **Choice**: Stamped generation_engine (gemini_llm vs lgorithmic_fallback) directly into storyboard.json and displayed status as ⚠️ DEGRADED in BATCH_REPORT.md while keeping ✅ SUCCESS reserved strictly for verified LLM runs.
- **Rationale**: Full observability and transparency in automated production runs.

### Decision 7: Legal & Licensed BGM Sourcing Constraint Adherence
- **Context**: BGM tracks must never be scraped from unlicensed sites or YouTube rips due to platform copyright strike / Content ID risks.
- **Choice**: Sourced starter catalog exclusively from Incompetech (Kevin MacLeod, CC-BY 4.0 with explicit licensing and direct HTTP downloads), Pixabay Content License (Royalty-Free), and internal granular synth generators (CC0-1.0).
- **Rationale**: 100% legal compliance and platform-safe redistribution.

### Decision 8: EBU R128 Ingestion Loudness Normalization (-23 LUFS)
- **Context**: Ingesting tracks from different composers results in inconsistent audio levels across different videos.
- **Choice**: Pre-processed 100% of audio files in ssets/bgm/ via FFmpeg loudnorm=I=-23:LRA=7:tp=-2.0 at ingestion time and registered integrated LUFS values in ssets/bgm/LICENSES.json.
- **Rationale**: Ensures uniform mixing balances regardless of which track is deterministically selected.

### Decision 9: Deterministic Per-Category Pool Selection & Boundary Fades
- **Context**: Videos in the same tactical category previously always received identical music, and transitions used abrupt hard cuts.
- **Choice**: Defined 3-5 track candidate pools per category, selected deterministically via SHA-256(topic_id) % len(pool). Added fade=t=in:ss=0:d=1.0 and fade=t=out:st=(T-1.5):d=1.5 to the FFmpeg filtergraph.
- **Rationale**: Increases audio diversity across videos while maintaining reproducibility and smooth cinematic transitions.

### Decision 10: NEEDS OPERATOR ACTION Logging
- **Context**: Unattended run encountered services requiring manual credentials (Pixabay API key, YouTube Studio session).
- **Choice**: Documented exact manual ingestion workflows under 'NEEDS OPERATOR ACTION' in AUDIT_BGM.md and DECISIONS.md rather than attempting unauthorized web scraping.
