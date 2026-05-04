# photosynthesis-stem (skeleton)

STEM coverage for the ADR-005 fixture set. A quintessential 7th-grade
biology topic — concrete, well-bounded, with natural opportunities for
diagrams + a quick check.

## Status

**Skeleton only** at MAIC-430.A. The parity test SKIPS this fixture
(golden_outline.json + golden_scenes.json not yet recorded). When
real-LLM Pass-B goldens land at MAIC-430.B, this fixture activates
automatically.

To bootstrap synthetic goldens (regression-only baseline) before
MAIC-430.B:
  1. Author `llm_responses.json` mirroring the numerator-denominator
     pattern.
  2. Run the pipeline once; save outputs as goldens.
  3. The parity test starts asserting drift here on the next run.
