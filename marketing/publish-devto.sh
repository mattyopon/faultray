#!/bin/bash
# Publish marketing/devto-article.md to dev.to via the v1 articles API.
# Run from the developer machine (not WSL).
#
# Usage:
#   chmod +x publish-devto.sh
#   DEVTO_API_KEY=... ./publish-devto.sh
#
# #148: the API key is read from the environment instead of being baked
# into the script. Set it inline (`DEVTO_API_KEY=... ./publish-devto.sh`)
# to keep it out of shell history (when your shell is configured to skip
# space-prefixed lines) and out of git entirely.

set -euo pipefail

if [[ -z "${DEVTO_API_KEY:-}" ]]; then
  echo "error: DEVTO_API_KEY is not set." >&2
  echo "       Generate one at https://dev.to/settings/extensions and run as:" >&2
  echo "       DEVTO_API_KEY=... ./publish-devto.sh" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTICLE="${SCRIPT_DIR}/devto-article.md"

if [[ ! -f "${ARTICLE}" ]]; then
  echo "error: article not found at ${ARTICLE}" >&2
  exit 1
fi

# Strip the leading --- ... --- frontmatter block.
BODY=$(sed '1{/^---$/d}; /^---$/,/^---$/d' "${ARTICLE}")

PAYLOAD=$(python3 - "$BODY" <<'PY'
import json, sys

body = sys.argv[1]
payload = {
    "article": {
        "title": "How We Simulate 2,000+ Infrastructure Failures Without Touching Production",
        "body_markdown": body,
        "published": True,
        "tags": ["chaosengineering", "devops", "python", "terraform"],
        "description": "FaultRay scores your infrastructure resilience before terraform apply — catching cascade risks, SPOFs, and availability ceiling violations in seconds.",
    }
}
print(json.dumps(payload))
PY
)

curl -fsS -X POST "https://dev.to/api/articles" \
  -H "api-key: ${DEVTO_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}" | python3 -m json.tool

echo
echo "Done. Check the URL above."
