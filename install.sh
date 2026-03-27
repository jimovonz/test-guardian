#!/bin/bash
set -e

GUARDIAN_HOME="$(cd "$(dirname "$0")" && pwd)"
COMMANDS_DIR="$HOME/.claude/commands"

mkdir -p "$COMMANDS_DIR"

# Symlink slash command
ln -sf "$GUARDIAN_HOME/guardian.md" "$COMMANDS_DIR/guardian.md"

echo "test-guardian installed."
echo ""
echo "Usage (from any Claude Code session):"
echo "  /guardian              — review tests for staged/uncommitted changes"
echo "  /guardian --all        — review full test suite"
echo "  /guardian --base main  — review tests for changes since main"
