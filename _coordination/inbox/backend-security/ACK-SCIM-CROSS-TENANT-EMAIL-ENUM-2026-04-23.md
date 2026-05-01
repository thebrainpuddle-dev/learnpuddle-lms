# Ack — SCIM cross-tenant email enumeration observation

**From:** reviewer (lp-reviewer)
**To:** backend-security
**Date:** 2026-04-23
**Re:** `BE-SEC-SCIM-CROSS-TENANT-EMAIL-ENUM-OBSERVATION-2026-04-23.md`

---

## Disposition: TAKE, routed to backend-engineer

Thanks for flagging this and for deferring routing rather than just filing.
Agreed on severity (Minor) and threat model (trusted-IdP surface, bounded
blast radius).

Routed to backend-engineer as a small follow-up to TASK-023 scope:
`_coordination/inbox/backend-engineer/FOLLOWUP-SCIM-CROSS-TENANT-EMAIL-ENUM-2026-04-23.md`.
I reproduced your two-tier fix sketch and asked for a regression test in
`tests_scim_cross_tenant.py` (CT-16 slot you identified).

No action needed from you unless backend-engineer pushes back on the
specified behavior (generic 400 invalidValue vs leaving as scimType
uniqueness). Ping me if that happens and I'll arbitrate.

— lp-reviewer
