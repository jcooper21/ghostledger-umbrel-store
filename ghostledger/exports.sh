#!/bin/bash
# GhostLedger exports.sh
# ======================
# This script exports environment variables that can be used by other Umbrel apps.
# Currently GhostLedger doesn't export any variables since it's a standalone tool,
# but this file is required for Umbrel app structure.

# Export the app's web interface URL (internal Docker network)
export APP_GHOSTLEDGER_HOST="ghostledger_web_1"
export APP_GHOSTLEDGER_PORT="8501"
