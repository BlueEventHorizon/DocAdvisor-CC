#!/bin/bash
# Test script for .doc_structure.yaml version migration (REQ-003)
# Tests: version detection, staged migration, error handling, idempotency
# Usage: ./test_migration.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_PROJECT="$SCRIPT_DIR/test_project"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

PASS_COUNT=0
FAIL_COUNT=0

test_result() {
    local name="$1"
    local expected="$2"
    local actual="$3"

    if [[ "$expected" == "$actual" ]]; then
        echo -e "${GREEN}PASS${NC}: $name"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: $name (expected=$expected, actual=$actual)"
        ((FAIL_COUNT++))
    fi
}

# Ensure test project has been set up
SCRIPTS_DIR="$TEST_PROJECT/.claude/doc-advisor/scripts"
if [[ ! -f "$SCRIPTS_DIR/toc_utils.py" ]]; then
    echo "Error: Test project not set up. Run setup.sh first."
    exit 1
fi

PYTHON_CMD=python3

echo "=================================================="
echo "Migration Test Suite (REQ-003)"
echo "=================================================="
echo ""

# ==================================================
echo "=================================================="
echo "Test M-01: Version detection - no comment (v1)"
echo "=================================================="

RESULT=$($PYTHON_CMD -c "
import sys; sys.path.insert(0, '$SCRIPTS_DIR')
from toc_utils import _detect_version
v = _detect_version('rules:\n  rule:\n    paths: [rules/]')
print(v)
" 2>&1)
test_result "No version comment → v1" "1" "$RESULT"
echo ""

# ==================================================
echo "=================================================="
echo "Test M-02: Version detection - v2.0"
echo "=================================================="

RESULT=$($PYTHON_CMD -c "
import sys; sys.path.insert(0, '$SCRIPTS_DIR')
from toc_utils import _detect_version
v = _detect_version('# doc_structure_version: 2.0\nrules:\n')
print(v)
" 2>&1)
test_result "Version 2.0 comment → 2" "2" "$RESULT"
echo ""

# ==================================================
echo "=================================================="
echo "Test M-03: Version detection - v3.0"
echo "=================================================="

RESULT=$($PYTHON_CMD -c "
import sys; sys.path.insert(0, '$SCRIPTS_DIR')
from toc_utils import _detect_version
v = _detect_version('# doc_structure_version: 3.0\nrules:\n')
print(v)
" 2>&1)
test_result "Version 3.0 comment → 3" "3" "$RESULT"
echo ""

# ==================================================
echo "=================================================="
echo "Test M-04: Version detection - future version (v4)"
echo "=================================================="

RESULT=$($PYTHON_CMD -c "
import sys; sys.path.insert(0, '$SCRIPTS_DIR')
from toc_utils import apply_migrations
result = apply_migrations({'rules': {'root_dirs': ['rules/']}}, 4)
print('root_dirs' in result.get('rules', {}))
" 2>&1)
test_result "Future version v4 → skip (data unchanged)" "True" "$RESULT"
echo ""

# ==================================================
echo "=================================================="
echo "Test M-05: v1 → v3 chain migration"
echo "=================================================="

RESULT=$($PYTHON_CMD -c "
import sys; sys.path.insert(0, '$SCRIPTS_DIR')
from toc_utils import _parse_config_yaml, apply_migrations

v1_content = '''rules:
  rule:
    paths:
      - rules/
      - guidelines/
specs:
  requirement:
    paths:
      - specs/requirements/
  design:
    paths:
      - specs/design/'''

parsed = _parse_config_yaml(v1_content)
result = apply_migrations(parsed, 1)

# Check rules
assert result['rules']['root_dirs'] == ['rules/', 'guidelines/'], f'rules root_dirs: {result[\"rules\"][\"root_dirs\"]}'
assert result['rules']['doc_types_map'] == {'rules/': 'rule', 'guidelines/': 'rule'}, f'rules doc_types_map: {result[\"rules\"][\"doc_types_map\"]}'

# Check specs
assert 'specs/requirements/' in result['specs']['root_dirs']
assert 'specs/design/' in result['specs']['root_dirs']
assert result['specs']['doc_types_map']['specs/requirements/'] == 'requirement'
assert result['specs']['doc_types_map']['specs/design/'] == 'design'

# v3: no internal fields
assert 'toc_file' not in result['rules']
assert 'common' not in result

print('OK')
" 2>&1)
test_result "v1 → v3 chain: root_dirs + doc_types_map correct" "OK" "$RESULT"
echo ""

# ==================================================
echo "=================================================="
echo "Test M-06: v2 → v3 internal fields removed"
echo "=================================================="

RESULT=$($PYTHON_CMD -c "
import sys; sys.path.insert(0, '$SCRIPTS_DIR')
from toc_utils import _parse_config_yaml, apply_migrations

v2_content = '''# doc_structure_version: 2.0
rules:
  root_dirs:
    - rules/
  doc_types_map:
    rules/: rule
  toc_file: .claude/doc-advisor/toc/rules/rules_toc.yaml
  checksums_file: .claude/doc-advisor/toc/rules/.toc_checksums.yaml
  work_dir: .claude/doc-advisor/toc/rules/.toc_work/
  output:
    header_comment: test
common:
  parallel:
    max_workers: 5'''

parsed = _parse_config_yaml(v2_content)
result = apply_migrations(parsed, 2)

assert 'toc_file' not in result.get('rules', {}), 'toc_file should be removed'
assert 'checksums_file' not in result.get('rules', {}), 'checksums_file should be removed'
assert 'work_dir' not in result.get('rules', {}), 'work_dir should be removed'
assert 'output' not in result.get('rules', {}), 'output should be removed'
assert 'common' not in result, 'common section should be removed'
assert result['rules']['root_dirs'] == ['rules/'], 'root_dirs should be preserved'
assert result['rules']['doc_types_map'] == {'rules/': 'rule'}, 'doc_types_map should be preserved'

print('OK')
" 2>&1)
test_result "v2 → v3: internal fields removed, structure preserved" "OK" "$RESULT"
echo ""

# ==================================================
echo "=================================================="
echo "Test M-07: v3 → no-op"
echo "=================================================="

RESULT=$($PYTHON_CMD -c "
import sys; sys.path.insert(0, '$SCRIPTS_DIR')
from toc_utils import _parse_config_yaml, apply_migrations

v3_content = '''# doc_structure_version: 3.0
rules:
  root_dirs:
    - rules/
  doc_types_map:
    rules/: rule
  patterns:
    target_glob: \"**/*.md\"
    exclude: []'''

parsed = _parse_config_yaml(v3_content)
import copy
original = copy.deepcopy(parsed)
result = apply_migrations(parsed, 3)

assert result == original, f'v3 should be unchanged: {result}'
print('OK')
" 2>&1)
test_result "v3 → no-op (data unchanged)" "OK" "$RESULT"
echo ""

# ==================================================
echo "=================================================="
echo "Test M-08: Idempotency (apply twice → same result)"
echo "=================================================="

RESULT=$($PYTHON_CMD -c "
import sys; sys.path.insert(0, '$SCRIPTS_DIR')
from toc_utils import _parse_config_yaml, apply_migrations
import copy

v1_content = '''rules:
  rule:
    paths:
      - rules/'''

parsed = _parse_config_yaml(v1_content)
first = apply_migrations(copy.deepcopy(parsed), 1)
second = apply_migrations(copy.deepcopy(first), 1)

assert first == second, f'Not idempotent: first={first}, second={second}'
print('OK')
" 2>&1)
test_result "Idempotency: apply twice → same result" "OK" "$RESULT"
echo ""

# ==================================================
echo "=================================================="
echo "Test M-09: Rollback on migration failure (FR-04-1)"
echo "=================================================="

RESULT=$($PYTHON_CMD -c "
import sys, copy; sys.path.insert(0, '$SCRIPTS_DIR')
from toc_utils import _parse_config_yaml, apply_migrations, MIGRATIONS, _migrate_v1_to_v2

# v1 format input
v1_content = '''rules:
  rule:
    paths:
      - custom_rules/'''

parsed = _parse_config_yaml(v1_content)
original_copy = copy.deepcopy(parsed)

# Inject a failing migration at v3
def _fail_migration(p):
    raise RuntimeError('Intentional failure for testing')

saved_migrations = dict(MIGRATIONS)
MIGRATIONS[3] = _fail_migration

try:
    result = apply_migrations(parsed, 1)
    # Should return original data (before any migration)
    assert result == original_copy, f'Rollback failed: got {result}, expected {original_copy}'
    print('OK')
finally:
    MIGRATIONS.clear()
    MIGRATIONS.update(saved_migrations)
" 2>&1)
test_result "Rollback on v2→v3 failure returns original v1 data" "OK" "$RESULT"
echo ""

# ==================================================
echo "=================================================="
echo "Test M-10: load_config integration with v1 format file"
echo "=================================================="

# Create a temporary v1 .doc_structure.yaml and verify load_config works end-to-end
RESULT=$($PYTHON_CMD -c "
import sys, os, tempfile, copy
sys.path.insert(0, '$SCRIPTS_DIR')

# Write a v1 format .doc_structure.yaml to a temp dir
tmpdir = tempfile.mkdtemp()
v1_content = '''rules:
  rule:
    paths:
      - rules/
specs:
  requirement:
    paths:
      - docs/requirements/
  design:
    paths:
      - docs/design/'''

with open(os.path.join(tmpdir, '.doc_structure.yaml'), 'w') as f:
    f.write(v1_content)

# Monkey-patch Path.cwd() to point to tmpdir
from pathlib import Path
original_cwd = Path.cwd
Path.cwd = staticmethod(lambda: Path(tmpdir))

try:
    from toc_utils import load_config
    config = load_config('rules')

    # Verify v1→v3 migration happened + defaults merged
    assert 'root_dirs' in config, f'Missing root_dirs: {config}'
    assert config['root_dirs'] == ['rules/'], f'Wrong root_dirs: {config[\"root_dirs\"]}'
    assert 'toc_file' in config, f'Missing toc_file (code default): {config}'
    print('OK')
finally:
    Path.cwd = original_cwd
    import shutil
    shutil.rmtree(tmpdir)
" 2>&1)
test_result "load_config integration: v1 file → migrated + defaults merged" "OK" "$RESULT"
echo ""

# ==================================================
# Summary
echo "=================================================="
echo "Summary"
echo "=================================================="
echo ""
echo -e "Passed: ${GREEN}$PASS_COUNT${NC}"
echo -e "Failed: ${RED}$FAIL_COUNT${NC}"
echo ""

if [[ $FAIL_COUNT -eq 0 ]]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed.${NC}"
    exit 1
fi
