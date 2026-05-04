"""MAIC v2 Generation Pipeline.

Port of OpenMAIC's `lib/generation/` directory — replaces the legacy
`apps.courses.maic_generation_service` (3,410 lines) with a clean
two-stage pipeline:

    Stage 1 — outline_generator.py:
        topic + agent count + language + level → 10 scene outlines
        (one LLM call)

    Stage 2 — scene_generator.py:
        per-outline content + actions LLM calls (parallel)
        → finalized scenes ready for the playback engine

Source:
    https://github.com/THU-MAIC/OpenMAIC/tree/main/lib/generation
    /Volumes/CrucialX9/OpenMAIC/lib/generation/

Phase 4 modules (planned, see `~/.claude/plans/mighty-painting-panda.md`):
    json_repair.py             — multi-strategy JSON parsing
    action_parser.py           — JSON → Action[] with fallbacks
    prompt_formatters.py       — buildCourseContext, formatAgents, etc.
    interactive_post_processor.py — KaTeX delim + script tag protection
    outline_generator.py       — Stage 1
    pipeline_runner.py         — orchestrator
    scene_builder.py           — standalone scene assembly
    scene_generator.py         — Stage 2 (the big one)
    tasks.py                   — Celery chain
    consumers.py               — WS progress events
    models.py                  — MaicGenerationJob

Out of scope for Phase 4 (see plan):
    - Per-tenant API keys (Phase 5+)
    - Vision / multimodal slides (Phase 5+)
    - Image generation (Phase 5+)
"""
