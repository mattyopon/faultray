#!/bin/bash
# FaultRay v11.0.0 Release Script
# Run this AFTER patent filing is complete

set -e

VERSION="11.0.0"

echo "=== FaultRay v${VERSION} Release ==="

# 1. Create git tag
echo "Creating git tag v${VERSION}..."
git tag -a "v${VERSION}" -m "Release v${VERSION} — AI Agent Resilience Simulation"

# 2. Push tag
echo "Pushing tag..."
git push origin "v${VERSION}"

# 3. Build package
echo "Building package..."
python -m build

# 4. Verify package
echo "Verifying package..."
twine check dist/*

# 5. Upload to PyPI
echo "Uploading to PyPI..."
twine upload dist/faultray-${VERSION}*

# 6. Create GitHub Release
echo "Creating GitHub Release..."
gh release create "v${VERSION}" \
  --title "FaultRay v${VERSION} — AI Agent Resilience Simulation" \
  --notes-file CHANGELOG_RELEASE.md \
  dist/faultray-${VERSION}*

echo "=== Release complete! ==="
