#!/bin/bash
# Doc Advisor config check: verify document directories are configured.
# Called from skill Pre-check steps. If not configured, outputs a warning
# that tells Claude to run /classify-docs first.
# Exit 0 with no output = directories are configured (OK).
#
# Created by k_terada

# Hook cwd is not guaranteed to be project root; use $CLAUDE_PROJECT_DIR
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

CONFIG=".claude/doc-advisor/config.yaml"

# Case 1: .doc_structure.yaml exists → runtime derives root_dirs
[[ -f ".doc_structure.yaml" ]] && exit 0

# Case 2: root_dirs explicitly set in config.yaml
grep -q "^  root_dirs:" "$CONFIG" 2>/dev/null && exit 0

# Case 3: config.yaml doesn't exist → Doc Advisor not installed
[[ ! -f "$CONFIG" ]] && exit 0

# Not configured → warn
echo "[ACTION REQUIRED] Doc Advisor: Document directories are not configured. Run /classify-docs skill to auto-detect and configure document directories. This must be completed before document search or ToC generation will work. If in plan mode, run /classify-docs after exiting plan mode."
