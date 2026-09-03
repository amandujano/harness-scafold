#!/usr/bin/env bash
# init.sh — Environment Verification and Initialization
#
# This script is executed by the agent at the START of a session and before
# declaring any task as `done`. If it fails, the session must not advance.
#
# Expected output: clear exit codes and blocks marked with [OK]/[FAIL].

set -u
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

ok()    { printf "${GREEN}[OK]${NC}    %s\n" "$1"; }
warn()  { printf "${YELLOW}[WARN]${NC}  %s\n" "$1"; }
fail()  { printf "${RED}[FAIL]${NC}  %s\n" "$1"; }

EXIT_CODE=0

echo "── 1. Verifying Environment ─────────────────────────────"

# Detect Language/Runtime
if [ -f "package.json" ]; then
  RUNTIME="Node.js"
  TEST_CMD="npm test"
elif [ -f "requirements.txt" ] || [ -f "pyproject.toml" ]; then
  RUNTIME="Python"
  TEST_CMD="python3 -m unittest discover -s tests -v"
elif [ -f "go.mod" ]; then
  RUNTIME="Go"
  TEST_CMD="go test ./..."
else
  RUNTIME="Unknown"
  TEST_CMD=""
fi

if [ "$RUNTIME" = "Unknown" ]; then
  warn "Could not detect runtime. Tests may not run."
else
  ok "Detected Runtime: $RUNTIME"
fi

echo ""
echo "── 2. Verifying Harness Base Files ─────────────────────"

for f in AGENTS.md feature_list.json progress/current.md docs/architecture.md docs/conventions.md docs/verification.md CHECKPOINTS.md; do
  if [ ! -f "$f" ]; then
    fail "Base file missing: $f"
    EXIT_CODE=1
  else
    ok "Exists $f"
  fi
done

echo ""
echo "── 3. Validating feature_list.json and specs ─────────────"

# Since JSON validation is complex in pure bash, we attempt to use a
# basic check for file existence. For deeper validation, the project
# should provide a `validate-specs` command.
if [ -f "feature_list.json" ]; then
  ok "feature_list.json exists"
else
  fail "feature_list.json missing"
  EXIT_CODE=1
fi

# Optional: check for specs folders if sdd is used
if [ -d "specs" ]; then
  ok "specs/ directory exists"
fi

echo ""
echo "── 4. Running Tests ─────────────────────────────────"

if [ -n "$TEST_CMD" ]; then
  if $TEST_CMD 2>&1; then
    ok "All tests pass"
  else
    fail "There are broken tests"
    EXIT_CODE=1
  fi
elif [ -d "tests" ]; then
  warn "tests/ folder exists but no test command was detected. Please configure the environment."
  EXIT_CODE=1
else
  warn "No tests found."
fi

echo ""
echo "── 5. Summary ──────────────────────────────────────────"

if [ $EXIT_CODE -eq 0 ]; then
  ok "Environment ready. You can start working."
else
  fail "Environment is NOT ready. Resolve the errors before proceeding."
fi

exit $EXIT_CODE
