#!/bin/bash
# Doc Advisor SessionStart hook: check if document directories are configured.
# If not configured, outputs a warning that gets injected into Claude's context.
# Exit 0 with no output = no cost to the session.
#
# Created by k_terada

# Hook cwd is not guaranteed to be project root; use $CLAUDE_PROJECT_DIR
cd "$CLAUDE_PROJECT_DIR" || exit 0

CONFIG=".claude/doc-advisor/config.yaml"

# Case 1: .doc_structure.yaml exists → runtime derives root_dirs
[[ -f ".doc_structure.yaml" ]] && exit 0

# Case 2: root_dirs explicitly set in config.yaml
grep -q "^  root_dirs:" "$CONFIG" 2>/dev/null && exit 0

# Case 3: config.yaml doesn't exist → Doc Advisor not installed
[[ ! -f "$CONFIG" ]] && exit 0

# Not configured → warn
echo "Doc Advisor: Document directories not configured. Run /classify-docs to auto-detect and configure."
