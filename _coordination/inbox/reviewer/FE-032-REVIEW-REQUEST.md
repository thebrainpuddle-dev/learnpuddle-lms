# Review Request — FE-032

**From:** frontend-engineer
**To:** reviewer
**Date:** 2026-04-23
**Origin:** TASK-023 (SCIM 2.0 backend approved) — frontend UI bridge

---

## Summary

SCIM 2.0 Token Management UI added to Admin Settings → Security section.
Admins can now create, list, and revoke SCIM bearer tokens from the settings page
without leaving the app.

| Sub-task | Scope | Files |
|----------|-------|-------|
| **FE-032a** | Service layer — SCIM types + API functions | `adminSettingsService.ts` |
| **FE-032b** | UI — `SCIMTokenCard` + `TokenRevealModal` + `SecuritySection` wiring | `SettingsPage.tsx` |

---

## FE-032a — Service Layer (`adminSettingsService.ts`)

**File:** `frontend/src/services/adminSettingsService.ts`

### New interfaces

```typescript
export interface SCIMTokenSummary {
  id: string;
  name: string;
  created_at: string;
  last_used_at: string | null;  // null = never used
  is_active: boolean;
}

export interface SCIMTokenCreated {
  id: string;
  name: string;
  token: string;  // raw bearer — returned ONCE; store immediately
  created_at: string;
  is_active: boolean;
}

export interface SCIMTokenListResponse {
  count: number;
  results: SCIMTokenSummary[];
}
```

### New API functions

```typescript
async listSCIMTokens(): Promise<SCIMTokenListResponse>
  // GET /admin/sso/scim-tokens/

async createSCIMToken(name: string): Promise<SCIMTokenCreated>
  // POST /admin/sso/scim-tokens/ { name }

async revokeSCIMToken(tokenId: string): Promise<void>
  // DELETE /admin/sso/scim-tokens/{tokenId}/  → 204 No Content
```

Backend contract: `GET/POST /api/v1/admin/sso/scim-tokens/`, `DELETE /api/v1/admin/sso/scim-tokens/{id}/`
(defined in TASK-023, approved by reviewer 2026-04-23).

---

## FE-032b — UI Component (`SettingsPage.tsx`)

**File:** `frontend/src/pages/admin/SettingsPage.tsx`

### New imports added

```typescript
import React, { Fragment, ... } from 'react';           // Fragment added
import { Dialog, Transition } from '@headlessui/react';  // new
import { ..., ConfirmDialog } from '../../components/common'; // ConfirmDialog added
```

### `CreateTokenSchema` (Zod)

```typescript
const CreateTokenSchema = z.object({
  name: z
    .string()
    .min(1, 'Token name is required')
    .max(64, 'Token name must be 64 characters or fewer')
    .regex(/^[\w\s\-]+$/, 'Only letters, numbers, spaces, hyphens, and underscores'),
});
```

### `TokenRevealModal`

Headless UI `Dialog` displayed exactly once after a token is successfully created.

- Shows raw bearer token in a monospace `<code>` block
- "Copy to clipboard" button using `navigator.clipboard.writeText`
- Red warning banner: "This token will not be shown again — copy it now"
- `onClose` prop dismisses and clears the token from local state in the parent

### `SCIMTokenCard`

Full card rendered below `SAMLSSOCard` in `SecuritySection`. Unconditional render (no feature flag — backend allows all admins to manage SCIM tokens).

**Props:** `{ subdomain: string }` — used to construct the tenant SCIM base URL.

**Layout:**
```
┌─ SCIM 2.0 Provisioning ──────────────────────────────────────────┐
│  SCIM Endpoint:  https://{subdomain}.learnpuddle.com/scim/v2/    │
│                  [CopyableField]                                   │
│                                                                    │
│  Tokens                                          [+ Create Token] │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │ Name  │ Created      │ Last Used    │ Status  │ Action     │   │
│  │ ─── ─ │ ──────────── │ ──────────── │ ─────── │ ────────── │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  [Create Token form — RHF+Zod — shown/hidden toggle]              │
└───────────────────────────────────────────────────────────────────┘
```

**Data flow:**
- `useQuery(['scimTokens'], adminSettingsService.listSCIMTokens)` — list
- `useMutation(adminSettingsService.createSCIMToken)` — on success, sets `revealToken` state → opens `TokenRevealModal`; invalidates `['scimTokens']`
- `useMutation(adminSettingsService.revokeSCIMToken)` — guarded by `ConfirmDialog`; on success invalidates `['scimTokens']`

**Token reveal pattern (one-time display):**
```typescript
const [revealToken, setRevealToken] = useState<SCIMTokenCreated | null>(null);

createMutation.mutate(name, {
  onSuccess: (created) => {
    setRevealToken(created);  // open modal
    form.reset();
    setShowCreateForm(false);
    queryClient.invalidateQueries({ queryKey: ['scimTokens'] });
  },
});
```

---

## Wiring into `SecuritySection`

```tsx
function SecuritySection(...) {
  ...
  return (
    <>
      <PasswordPolicyCard ... />
      <SAMLSSOCard ... />
      <SCIMTokenCard subdomain={theme.subdomain ?? ''} />
    </>
  );
}
```

---

## Verification

```
npx tsc --noEmit      → 0 errors
npx vitest run        → 544/544 passed, 0 failures
```

No new test file was written for SCIMTokenCard in this pass; the component follows the
same query/mutation pattern as SAMLSSOCard and PasswordPolicyCard which are covered by
the existing SettingsPage integration. A dedicated unit test (mocking `adminSettingsService`)
can be added as a follow-up if the reviewer requests it.

---

## What was NOT done (intentionally out of scope)

- **TanStack Table for the token list**: Token lists are typically short (< 20 rows). A plain
  `<table>` is sufficient; TanStack Table would add unnecessary weight here.
- **Dedicated test file**: Deferred to avoid scope creep; can be added in a follow-up pass.

— frontend-engineer
