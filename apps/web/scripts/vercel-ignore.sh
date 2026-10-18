#!/usr/bin/env bash
# Vercel "Ignored Build Step" (vercel.json ignoreCommand). Vercel runs it from
# the project's Root Directory (apps/web): exit 0 skips the deployment, any
# other status builds. In the monorepo this skips commits that don't touch
# apps/web (Python package, docs, other workflows).
#
# The base is the last successfully deployed commit for this branch
# (VERCEL_GIT_PREVIOUS_SHA), not HEAD^: with HEAD^, an apps/web change
# followed by a core-only commit on the same branch would never ship.
set -uo pipefail

base="${VERCEL_GIT_PREVIOUS_SHA:-}"

# No usable base (a branch's first deployment, or a base outside Vercel's
# shallow clone): build, so an earlier apps/web change is never skipped.
if [ -z "$base" ] || ! git cat-file -e "${base}^{commit}" 2>/dev/null; then
  exit 1
fi

# Redeploying the already-deployed commit (env var change, deploy hook,
# manual redeploy) has an empty diff by construction but is intentional.
if [ "$(git rev-parse "${base}^{commit}")" = "$(git rev-parse HEAD)" ]; then
  exit 1
fi

# Any git error exits non-zero, i.e. builds.
git diff --quiet "$base" HEAD -- .
