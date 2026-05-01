---
tags: [review, task/FE-032, task/TASK-023, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-24
---

# Review: FE-032 (SCIM Token UI) + QA SCIMTokenCard Test File

## Verdict: APPROVE (both)

## Summary

FE-032 wires SCIM 2.0 token management into Admin Settings → Security: a new `SCIMTokenCard` component (with `TokenRevealModal`), three `adminSettingsService` methods (`listSCIMTokens`/`createSCIMToken`/`revokeSCIMToken`), and Zod-validated create form. QA-tester proactively wrote the test file the FE engineer deferred — `SettingsPage.SCIMTokenCard.test.tsx`, 24 tests across 6 describe blocks, full-page render strategy targeting `?tab=security`. Both tsc and vitest clean.

## Critical Issues

None.

## Major Issues

None.

## Minor Issues — FE-032 Implementation

1. **Token never cached in browser** — good, but reveal pattern relies on a single `useState` slot.
   `SettingsPage.tsx:1672` keeps the raw token in a `useState<string | null>`. If the user accidentally creates two tokens in rapid succession (mutation latency), the second `setRevealToken(created.token)` overwrites the first before the user copies it. Low probability (modal blocks the create form re-open), but worth a one-line guard: `if (revealToken) return;` in the `onSuccess` handler. File a follow-up; not blocking.

2. **`navigator.clipboard.writeText` failure path is silent**
   `SettingsPage.tsx:1578` `.then(() => setCopied(true))`. If the browser denies clipboard permission (e.g., insecure context, focus loss), the `.then` never fires and the user sees no error. Add `.catch((err) => toast.error('Copy failed', '...'))`. Minor UX nit.

3. **Cover note mentions queryKey `['scimTokens']` but implementation uses `['scim-tokens']`**
   Doc/code drift. Test file correctly invalidates via the actual key (it just refetches via mock). Update cover note for accuracy.

4. **No backend feature-flag guard on the card**
   The card renders unconditionally for all admins. That's intentional per the cover note ("backend allows all admins to manage SCIM tokens"), but a school on a Free plan that doesn't *want* SCIM exposure may prefer a tenant feature flag. Out of scope for FE-032; flag for product.

## Minor Issues — QA Test File

5. **"shows a loading spinner" test asserts negative DOM** (`SettingsPage.SCIMTokenCard.test.tsx:255`)
   `expect(screen.queryByText('Okta SCIM Provisioner')).not.toBeInTheDocument()` proves the table didn't render, not that a spinner *did*. Consider `expect(document.querySelector('.animate-spin')).toBeTruthy()` (matching the pattern in FE-033 tests). Minor.

6. **Test count drift** — cover note says 24 tests; my count of describe blocks summed to ~25-26 (including the `submits create form` test that was bracketed into the "Create token form" group). Numbers within rounding error; not material.

7. **Password policy interference acknowledged in cover note but not tested**
   QA-tester correctly mocked `getPasswordPolicy` to return `MOCK_PASSWORD_POLICY` so the `PasswordPolicyCard` renders without errors. Risk: if `PasswordPolicyCard` adds a "Save" button labelled `Create` in the future, it would collide with the create-token submit button. Tests use `getByRole('button', { name: /^create$/i })` which is somewhat narrow, but ambiguity could surface. Defer; tests pass today.

## Positive Observations

### FE-032
- **One-time token reveal is implemented correctly**: token lives only in component state, never in storage; modal closes via explicit user action (`I've copied the token`) — no ambient dismissal that could hide it before the user copies.
- **Defensive UI**: revoked tokens render *with* a "Revoked" badge but *without* a Revoke button. Prevents the obvious "click revoke twice" footgun.
- **`select-all` class on the `<code>` block** for easy keyboard-driven copy. Nice touch.
- **Copy state visualization**: icon flips green when copied. Cheap signal that the button worked.
- **ConfirmDialog with danger variant**: the revoke flow is two-step with explicit "Keep active" / "Revoke token" buttons. Matches the destructive-action pattern used elsewhere.
- **Subdomain placeholder** when subdomain is empty: shows `https://<your-school>.learnpuddle.com/scim/v2/` rather than a malformed URL.
- **Header comments on `adminSettingsService.ts`** document the backend contract endpoints inline.

### QA test file
- **Full-page render strategy** is the right call: `SCIMTokenCard` is not exported, and rendering through `SettingsPage` at `?tab=security` validates the real `SecuritySection → SCIMTokenCard` wiring (catches a class of bugs that synthetic mounts miss).
- **Zod validation paths covered**: empty name, 65-char overflow, special-character regex. Each asserts both the visible error message AND that `createSCIMToken` was not called — defense in depth.
- **Reveal modal copy-to-clipboard** asserts on `navigator.clipboard.writeText` mock — proves the wire-up, not just that the button is clickable.
- **Revoke flow uses ConfirmDialog button labels (`Revoke token` / `Keep active`)** matching the implementation. Tight coupling but correct — these labels are user-facing copy.
- **Toast error path tested**: `toast.error('Failed to create SCIM token', ...)` is asserted on visible DOM via `ToastProvider`, not via spy. Resilient to internal toast-API refactors.
- **Clipboard stub via `Object.defineProperty(navigator, 'clipboard', ...)`** — sidesteps jsdom's "Not implemented" warning cleanly.
- **Housekeeping** delivered alongside: removed unused `import hashlib` from `tests_scim_cross_tenant.py` and renamed `test_scim_deprovisioned_user_hidden_from_list` → `test_scim_deprovisioned_user_still_visible_with_active_false` per my prior verdict. Fast turnaround.

## Recommendation

**APPROVE** both deliverables. FE-032 is production-ready; QA's test file closes the only coverage gap the FE engineer flagged. Minor items above are forward-looking nits — none blocking.

Suggested follow-ups (low priority):
1. Guard `setRevealToken` against double-click overwrite in the create mutation.
2. Add `.catch` to `navigator.clipboard.writeText` for permission-denied errors.
3. Tighten the loading-spinner assertion in the test.

— reviewer
