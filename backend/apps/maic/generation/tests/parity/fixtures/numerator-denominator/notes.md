# numerator-denominator (ADR-005's named fixture)

The named Phase 4 parity fixture. Topic: introducing fractions to a
4th-grade audience, using concrete visual examples + one quick quiz +
one interactive simulation. The outline shape (10 scenes: slide × 8
+ quiz × 1 + interactive × 1) matches Phase 4's "≥3 distinct
interactive scene types" Phase-close criterion in spirit (the v2
endpoint will produce a wider mix once real LLM calls drive outline
generation).

## Provenance of `llm_responses.json`

These are **synthetic** canned responses crafted to match the prompt
templates' expected output shapes (outline JSON object;
`{elements,…}` for slide content; question array for quiz content;
action array for slide/quiz/interactive actions; widget HTML for
simulation; teacher-actions JSON for Ultra Mode).

Markers were chosen from each template's distinctive header
(`# Slide Content Generator`, `# Quiz Content Generator`, etc.) so
the router routes each call to the right canned response without
matching adjacent templates by accident.

## Provenance of `golden_outline.json` + `golden_scenes.json`

Recorded from our pipeline run on 2026-05-04 against the synthetic
LLM responses above. This is a **regression baseline**, not a
fidelity-vs-upstream baseline:

  - Re-running the pipeline with the same fixture should produce
    identical outputs (deterministic — no real LLM, no temperature).
  - Drift > 15% on any metric implies a regression in our pipeline
    code, NOT divergence from upstream.

The fidelity-vs-upstream gate (real OpenRouter calls + comparison
against upstream-recorded outputs) is **MAIC-430.B** (Pass B,
Session 7). MAIC-430.A (this fixture) gates Session-5 close — it
prevents us from breaking the pipeline before Celery + WS land.

## Resync procedure

When real OpenRouter goldens land:
  1. Run the pipeline against real OpenRouter with the same input.
  2. Save the result over `golden_*.json` (overwrite).
  3. Delete `llm_responses.json` (no longer needed; the test will
     skip the synthetic-router step and go through real generate_text
     with `OPENROUTER_API_KEY` set).
  4. Update this notes.md provenance section.
