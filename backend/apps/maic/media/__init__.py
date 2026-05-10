"""Media generation subsystem (Phase 9, MAIC-901+).

Source: THU-MAIC/OpenMAIC lib/media/* (lifted under ADR-001a).
        Backend port lives entirely in this module; no upstream code
        is imported. The orchestrator + adapters mirror upstream's
        provider-abstraction pattern, adapted to async Python.

Used by:
  - apps/maic/generation/scene_builder.py — resolves `gen_img_<id>` /
    `gen_vid_<id>` placeholders during Phase 4 generation.
  - apps/maic/media/views.py — `POST /api/maic/v2/media/generate-{image,video}/`
    endpoints for direct teacher/admin requests.

Public surface:
  - types.py — Pydantic request/response types
  - providers.py — MediaProviderAdapter ABC + registry (MAIC-902)
  - orchestrator.py — async job runner with retry/timeout (MAIC-902)
  - adapters/ — one file per provider (MAIC-903 onward)
  - storage.py — V2 storage helper (mirrors apps/courses/maic_storage.py;
    that v1 file gets deleted in Phase 8)
"""
