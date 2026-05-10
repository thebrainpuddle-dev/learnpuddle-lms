"""PDF ingest subsystem (Phase 10, MAIC-1001+).

Source: THU-MAIC/OpenMAIC lib/pdf/* (lifted under ADR-001a, no AGPL
        import). Pattern mirrors apps/maic/media/ from Phase 9.

Goal: a teacher uploads a textbook PDF; backend parses it (Mineru
cloud first cut) into structured sections + figures + extracted
text; the Phase 4 outline generator uses that structured content as
an alternative seed to the bare topic string.

Public surface (planned, sequentially):
  - types.py — Pydantic request/response + document types (MAIC-1001)
  - providers.py — Provider ABC + registry (MAIC-1002)
  - mineru_client.py — Mineru cloud client + async polling (MAIC-1002)
  - parser.py — Mineru response → PDFDocument (MAIC-1002)
  - views.py — POST /api/maic/v2/pdf/parse/ (MAIC-1003)
  - models.py — PDFDocument table for caching parsed results (MAIC-1003)
"""
