#!/bin/bash
# FaultRay Demo Recording Script
# Records a scripted terminal demo using asciinema
# Output: demo/faultray-demo.cast

set -e

CAST_FILE="$(dirname "$0")/faultray-demo.cast"

echo "Recording FaultRay demo..."
echo "Output: $CAST_FILE"

# Use asciinema with a scripted input
asciinema rec "$CAST_FILE" \
  --title "FaultRay — Zero-Risk Chaos Engineering" \
  --idle-time-limit 2 \
  --command "bash $(dirname "$0")/demo-script.sh"

echo ""
echo "Done! Cast file: $CAST_FILE"
echo ""
echo "To preview:  asciinema play $CAST_FILE"
echo "To upload:   asciinema upload $CAST_FILE"
echo "To embed:    Use the SVG or embed link from asciinema.org"
