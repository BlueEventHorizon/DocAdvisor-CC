#!/bin/bash
# Analyze bw-cc-plugins source state for Codex install profile generation.
# Created by: k2moons

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

exec "${SCRIPT_DIR}/generate_codex_skill_set.sh" --analyze-only "$@"
