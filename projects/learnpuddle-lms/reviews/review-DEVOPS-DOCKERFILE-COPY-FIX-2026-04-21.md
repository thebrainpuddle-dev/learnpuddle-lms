---
tags: [review, task/devops-dockerfile-copy-fix, verdict/block, reviewer/lp-reviewer]
created: 2026-04-21
---

# Review: DevOps — nginx/Dockerfile COPY includes/ + proxy_params

## Verdict: BLOCK

## Summary

The proposed two-line `COPY` addition is technically correct in isolation
but **will break the production build the moment it lands** because it
re-introduces the exact regression that commit `04a1934` reverted only
three hours before this note was filed. `nginx/includes/` is **untracked
in git** (`git ls-files nginx/includes/` returns empty; `git status`
shows `?? nginx/includes/`). Any CI or deploy pipeline that builds from a
fresh `git clone` / `git pull` checkout will fail with:

```
ERROR: failed to compute cache key: "/nginx/includes": not found
```

This is the same failure mode that commit `5f1cbb4` shipped at
01:51 and `04a1934` had to revert at 01:54.

## Critical Issues

### 1. `nginx/includes/shared_locations.conf` is not tracked in git (BLOCK)

**Evidence:**

```text
$ git status --short nginx/
 M nginx/Dockerfile
 M nginx/nginx.conf
 M nginx/nginx.staging.conf
 M nginx/production.conf
?? nginx/includes/                          ← untracked directory

$ git ls-files nginx/includes/
(empty)

$ git log --all -- nginx/includes/shared_locations.conf
(empty — file has never been committed on any branch)
```

The revert commit `04a1934` — authored 3 hours 16 minutes before this
review request — explicitly documents the same trap:

> The previous commit 5f1cbb4 … accidentally picked up uncommitted
> working-tree changes to nginx/Dockerfile that added
> `COPY nginx/includes/ /etc/nginx/includes/`. That directory is
> untracked locally (sprint work not yet pushed), so the prod build at
> 5f1cbb4 failed with:
>
>     failed to compute cache key: "/nginx/includes": not found
>
> `nginx/includes/shared_locations.conf` should be reintroduced via its
> own commit when the sprint work is ready to land.

The current proposal reintroduces the COPY without first committing
`nginx/includes/shared_locations.conf`. This is functionally identical
to `5f1cbb4` and will have the same outcome on the next prod deploy.

**Required fix before this can land:**

1. Commit `nginx/includes/shared_locations.conf` (and any sibling
   includes) to the tree in a separate prior commit.
2. *Then* land the Dockerfile change in a follow-up commit.

A single squashed/combined commit works too — what matters is that at no
point in the committed history does `nginx/Dockerfile` reference a path
that is not in the same commit tree.

### 2. Verification gate was not actually executed

The note asks the reviewer to run
`docker build -f nginx/Dockerfile -t lms-nginx-test . && docker run --rm lms-nginx-test nginx -t`
"before merging." That is the one check that would have surfaced issue #1 —
a docker build from a clean git checkout (not the local working tree)
would fail immediately. Manual verification based on "the file exists in
the repo" is not sufficient here, precisely because "in the repo" was
being conflated with "in the working tree".

Given the agent sandbox cannot run `docker`, a human-operator test
build — or a CI job scoped just to `docker build nginx/Dockerfile` from
a fresh checkout — is a required pre-merge gate for this file going
forward.

## Major Issues

None beyond #1 above — if the tracking issue is resolved, the diff
itself is minimal and the rationale (self-contained image, defense in
depth against missing volume mounts) is sound.

## Minor Issues

### M1. Missing `chown` for the new paths

The original pre-revert version of this block chowned
`/etc/nginx/includes` to `nginx:nginx` as part of the
subsequent `RUN chown -R nginx:nginx …` chain. The new patch drops that
chown. The note argues root-owned, world-readable config files are fine
for a read-only path, which is correct — nginx only needs read access
to include files. No change required, but calling it out so the
divergence from the prior version is intentional, not an oversight.

### M2. `nginx/nginx.conf`, `nginx.staging.conf`, `production.conf` all
have uncommitted `M` modifications in the working tree. These are out
of scope for this particular review (they belong to prior devops work —
`review-DEVOPS-PROD-FLOWER-PROXY-2026-04-20.md` — that was approved but
apparently not yet committed). Flagging only so devops knows not to mix
them into the same commit as the Dockerfile change without explicit
scope-merging intent.

## Positive Observations

- The note correctly identified a real latent gap: `nginx.conf`
  references `include /etc/nginx/includes/shared_locations.conf` at
  lines 74 + 97, and `production.conf` references
  `include /etc/nginx/proxy_params` at 7 locations. Verified.
- `nginx/proxy_params` IS tracked in git (`git ls-files nginx/proxy_params`
  returns the path), so that half of the COPY is safe.
- Self-contained-image rationale is the right mental model; standalone
  `docker run <image> nginx -t` should pass without volume dependencies.
- Good diff hygiene — minimal two-line addition, clear inline comment
  explaining why baking the files in is valuable even when prod mounts
  override them.

## Required Before Re-Review

1. Add `nginx/includes/shared_locations.conf` (and any other include
   files the COPY directive will pull in) to git in a tracked commit.
2. Perform or request a clean-clone `docker build` to prove the image
   builds without the local working-tree providing the untracked files.
3. Confirm `docker run --rm <image> nginx -t` passes.

Once those three items are done, re-request review — this will flip to
APPROVE quickly.

— reviewer (lp-reviewer)
