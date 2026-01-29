#!/bin/bash
# Hypertransparency auto-rebuild hook for Claude Code
# Add to your Claude Code settings: ~/.claude/settings.json
#
# "hooks": {
#   "postSession": ["~/.local/bin/hypertransparency-rebuild"]
# }

# Find the repo root from current directory
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)

if [ -z "$REPO_ROOT" ]; then
    exit 0  # Not in a git repo, skip
fi

# Check if this repo has hypertransparency configured
if [ -f "$REPO_ROOT/.hypertransparency.json" ]; then
    echo "[hypertransparency] Rebuilding docs..."
    hypertransparency build "$REPO_ROOT" 2>/dev/null

    # Auto-commit if there are changes
    cd "$REPO_ROOT"
    if [ -n "$(git status --porcelain docs/)" ]; then
        git add docs/
        git commit -m "Auto-update transparency docs" --no-verify 2>/dev/null
    fi
fi
