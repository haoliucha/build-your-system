#!/usr/bin/env bash
# Tier 1 content contract tests for goal-creator skill
# Run: bash tests/run-content-tests.sh
# Exit 0 = all pass, non-zero = failures

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
source "$SCRIPT_DIR/test-helpers.sh"

SKILL_MD="$PLUGIN_ROOT/skills/goal-creator/SKILL.md"
SAMPLES_MD="$PLUGIN_ROOT/samples.md"
PLUGIN_JSON="$PLUGIN_ROOT/.claude-plugin/plugin.json"

PASS=0
FAIL=0

run_test() {
    if "$@"; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
    fi
}

echo "=== Tier 1: goal-creator content contract tests ==="
echo ""

echo "--- plugin.json ---"
run_test assert_contains "$PLUGIN_JSON" '"name": "goal-creator"' "plugin name set"
run_test assert_contains "$PLUGIN_JSON" '"skills"' "skills directory declared"

echo ""
echo "--- SKILL.md: frontmatter ---"
run_test assert_contains "$SKILL_MD" '^name: goal-creator$' "frontmatter name = goal-creator"
run_test assert_skill_description "$SKILL_MD"

echo ""
echo "--- SKILL.md: mental model (the foundation) ---"
run_test assert_contains "$SKILL_MD" "## Mental Model" "Mental Model section present"
run_test assert_contains "$SKILL_MD" "Stop hook" "explains /goal is a Stop hook"
run_test assert_contains "$SKILL_MD" "evaluator" "mentions evaluator"
run_test assert_contains "$SKILL_MD" "transcript" "explains transcript constraint"
run_test assert_contains "$SKILL_MD" "Evidence over confidence" "constraint 1 present"
run_test assert_contains "$SKILL_MD" "Goodhart" "constraint 2 (Goodhart) present"
run_test assert_contains "$SKILL_MD" "Ack.*loop\|Acknowledgement loop" "constraint 3 (ack loop) present"

echo ""
echo "--- SKILL.md: HARD-GATE + Checklist ---"
run_test assert_contains "$SKILL_MD" "## HARD-GATE" "HARD-GATE section present"
run_test assert_contains "$SKILL_MD" "## Checklist" "Checklist section present"
run_test assert_contains "$SKILL_MD" "SlashCommand" "SlashCommand invocation referenced"

echo ""
echo "--- SKILL.md: 7 Brainstorm questions ---"
for i in 1 2 3 4 5 6 7; do
    run_test assert_contains "$SKILL_MD" "Q$i" "Brainstorm Q$i present"
done

echo ""
echo "--- SKILL.md: Generator + Validator + Decision log ---"
run_test assert_contains "$SKILL_MD" "## Step 3" "Step 3 Generator section"
run_test assert_contains "$SKILL_MD" "## Step 4" "Step 4 Validator section"
run_test assert_contains "$SKILL_MD" "## Step 5" "Step 5 Decision Log section"
run_test assert_contains "$SKILL_MD" "docs/goal-prompts" "decision log path specified"
run_test assert_contains "$SKILL_MD" "or stop after" "turn cap requirement explicit"
run_test assert_contains "$SKILL_MD" "STATUS.md" "STATUS.md failure path required"
run_test assert_contains "$SKILL_MD" "do not ask" "禁问 confirm clause required"

echo ""
echo "--- SKILL.md: Forbidden Vocabulary list ---"
run_test assert_contains "$SKILL_MD" "## Forbidden Vocabulary" "Forbidden Vocabulary section"
# Sample of required forbidden words (both languages)
for word in 高级 热门 反常识 good great complete thorough; do
    run_test assert_contains "$SKILL_MD" "$word" "Forbidden Vocab includes '$word'"
done

echo ""
echo "--- SKILL.md: Rationalizations table (≥10 entries) ---"
run_test assert_contains "$SKILL_MD" "## Rationalizations Table" "Rationalizations Table section"
# Count table rows under Rationalizations Table — pipes per row, but be loose
run_test assert_count "$SKILL_MD" '^| "' "ge" 10 "≥10 rationalization rows"

echo ""
echo "--- SKILL.md: Red Flags + Exit discipline ---"
run_test assert_contains "$SKILL_MD" "Red Flags" "Red Flags section"
run_test assert_contains "$SKILL_MD" "Exit" "Exit discipline section"
run_test assert_contains "$SKILL_MD" "do not monitor\|Do NOT monitor\|stop participating" "explicit no-monitor rule"

echo ""
echo "--- SKILL.md: Triage table ---"
run_test assert_contains "$SKILL_MD" "## Step 1.*Triage\|## Triage" "Triage section"
run_test assert_contains "$SKILL_MD" "subjective" "triage covers subjective tasks"
run_test assert_contains "$SKILL_MD" "Multiple independent\|compound" "triage covers compound"

echo ""
echo "--- samples.md ---"
run_test assert_contains "$SAMPLES_MD" "samples" "samples file readable"
# Each sample has a code block with /goal
run_test assert_count "$SAMPLES_MD" "^/goal\|^claude -p" "ge" 6 "≥6 verbatim /goal samples"
# Each sample cites a source URL
run_test assert_count "$SAMPLES_MD" "Source.*http" "ge" 6 "≥6 source URLs"
# Sample mechanism diversity
run_test assert_contains "$SAMPLES_MD" "grep" "samples include grep mechanism"
run_test assert_contains "$SAMPLES_MD" "exit" "samples include exit-code mechanism"
# Anti-sample-as-decision-tree warning present
run_test assert_contains "$SAMPLES_MD" "NOT decision trees\|inspiration only\|Reference only" "anti-overfit warning"

echo ""
echo "=== Summary ==="
echo "Passed: $PASS"
echo "Failed: $FAIL"
echo "Total:  $((PASS + FAIL))"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
