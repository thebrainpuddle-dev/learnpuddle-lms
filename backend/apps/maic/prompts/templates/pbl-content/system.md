# PBL Content Generator (STUB — Phase 4)

> **Status**: STUB. The real PBL content generator (`lib/pbl/generate-pbl.ts`,
> 414 LoC + 4 MCP modules: project-info-mcp, agent-mcp, issueboard-mcp,
> chat-mcp) is an agentic loop that uses tool-calling to incrementally
> build a `PBLProjectConfig`. That work is **deferred to Phase 5+** per
> MAIC-432 research; this template exists so the prompt-loader diagnostic
> finds zero missing templates at Phase 4 close. **Phase 4 PBL scenes are
> built programmatically from the outline + pblConfig — no LLM call hits
> this template.**

You are a PBL (Project-Based Learning) project designer.

## Output Format

Output a single JSON object with this shape:

```json
{
  "projectInfo": {"title": "...", "description": "..."},
  "agents": [],
  "issueboard": {"agent_ids": [], "issues": [], "current_issue_id": null},
  "chat": {"messages": []}
}
```
