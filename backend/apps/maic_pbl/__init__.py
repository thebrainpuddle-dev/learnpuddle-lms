"""MAIC v2 PBL (Project-Based Learning) Subsystem — Phase 7.

Separate from classroom playback (apps.maic). PBL is a chat-first,
multi-turn workspace where students pick a development role and
collaborate with AI agents (Question, Judge, plus 2-4 development
roles) on structured projects with sequenced issues.

Two graphs:
  - design_graph.py    — one-shot agentic loop that produces the
                          PBLProjectConfig via 13 MCP-style tools.
  - (chat handler)     — runtime no-tools LLM call per student message;
                          implemented inline in consumers.py.

State lives in MaicPBLSession.project_config (JSONField) — NOT in
OrchestratorState. PBL deliberately doesn't extend the LangGraph state
schema so cross-phase regression risk stays at zero.
"""

default_app_config = "apps.maic_pbl.apps.MaicPblConfig"
