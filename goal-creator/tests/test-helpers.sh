#!/usr/bin/env bash
# Tier 1 test helpers for goal-creator skill
# Adapted from superpowers/tests/claude-code/test-helpers.sh
# Domain-specific assertions added at bottom.

# Run assertions on a file's content
# Usage: assert_contains "file_path" "pattern" "test name"
assert_contains() {
    local file="$1"
    local pattern="$2"
    local test_name="${3:-test}"

    if grep -q "$pattern" "$file" 2>/dev/null; then
        echo "  [PASS] $test_name"
        return 0
    else
        echo "  [FAIL] $test_name"
        echo "         Expected to find: $pattern"
        echo "         In file: $file"
        return 1
    fi
}

# Negative match
# Usage: assert_not_contains "file" "pattern" "test name"
assert_not_contains() {
    local file="$1"
    local pattern="$2"
    local test_name="${3:-test}"

    if grep -q "$pattern" "$file" 2>/dev/null; then
        echo "  [FAIL] $test_name"
        echo "         Did not expect: $pattern"
        echo "         In file: $file"
        return 1
    else
        echo "  [PASS] $test_name"
        return 0
    fi
}

# Count matches, assert exact / ≥ / ≤
# Usage: assert_count "file" "pattern" "operator" expected_count "test name"
#   operator: =, ge, le
assert_count() {
    local file="$1"
    local pattern="$2"
    local op="$3"
    local expected="$4"
    local test_name="${5:-test}"

    local actual
    actual=$(grep -c "$pattern" "$file" 2>/dev/null || echo "0")

    local pass=false
    case "$op" in
        "=")  [ "$actual" -eq "$expected" ] && pass=true ;;
        "ge") [ "$actual" -ge "$expected" ] && pass=true ;;
        "le") [ "$actual" -le "$expected" ] && pass=true ;;
        *)    echo "  [FAIL] $test_name: unknown operator $op"; return 1 ;;
    esac

    if $pass; then
        echo "  [PASS] $test_name (found $actual, want $op $expected)"
        return 0
    else
        echo "  [FAIL] $test_name"
        echo "         Pattern: $pattern"
        echo "         Found: $actual, expected $op $expected"
        return 1
    fi
}

# Pattern A appears before pattern B
assert_order() {
    local file="$1"
    local pattern_a="$2"
    local pattern_b="$3"
    local test_name="${4:-test}"

    local line_a line_b
    line_a=$(grep -n "$pattern_a" "$file" 2>/dev/null | head -1 | cut -d: -f1)
    line_b=$(grep -n "$pattern_b" "$file" 2>/dev/null | head -1 | cut -d: -f1)

    if [ -z "$line_a" ] || [ -z "$line_b" ]; then
        echo "  [FAIL] $test_name: one pattern missing (a:$line_a b:$line_b)"
        return 1
    fi

    if [ "$line_a" -lt "$line_b" ]; then
        echo "  [PASS] $test_name (A@$line_a < B@$line_b)"
        return 0
    else
        echo "  [FAIL] $test_name: A@$line_a not before B@$line_b"
        return 1
    fi
}

# Domain-specific: assert frontmatter description is well-formed
# Per writing-skills: must start with "Use when", must NOT summarize workflow
# Usage: assert_skill_description "SKILL.md"
assert_skill_description() {
    local file="$1"
    local test_name="frontmatter description format"

    # Extract description line from YAML frontmatter
    local desc
    desc=$(awk '/^---$/{f++;next} f==1 && /^description:/{print; exit}' "$file")

    if [ -z "$desc" ]; then
        echo "  [FAIL] $test_name: no description field in frontmatter"
        return 1
    fi

    # Check starts with "Use when"
    if ! echo "$desc" | grep -q "Use when"; then
        echo "  [FAIL] $test_name: description must start with 'Use when'"
        echo "         Got: $desc"
        return 1
    fi

    # Check does NOT contain workflow-summary words (writing-skills critical rule)
    # These are bad — they cause Claude to skip reading skill body
    local bad_phrases=("dispatches" "between tasks" "write a test first" "step 1" "phase 1" "first.*then.*finally")
    for bad in "${bad_phrases[@]}"; do
        if echo "$desc" | grep -qiE "$bad"; then
            echo "  [FAIL] $test_name: description summarizes workflow (forbidden per writing-skills)"
            echo "         Bad phrase: $bad"
            return 1
        fi
    done

    echo "  [PASS] $test_name"
    return 0
}

# Domain-specific: assert SKILL.md doesn't use forbidden vocab in its OWN body
# (would be hypocritical to ban these for /goal output but use them in SKILL prose)
# But: the Forbidden Vocabulary section itself MUST list these. So we exclude that section.
assert_no_subjective_words_in_advice() {
    local file="$1"
    local test_name="${2:-no subjective words in skill advice}"

    # Words to scan for in skill prose (excluding the Forbidden Vocabulary section)
    # Check advisory sentences only - the words ARE allowed in the forbidden vocab list
    local bad_words=("看起来很好" "比较合理" "应该够了" "通常没问题")

    local fails=0
    for word in "${bad_words[@]}"; do
        if grep -q "$word" "$file" 2>/dev/null; then
            echo "  [FAIL] $test_name: found vague advice word: $word"
            fails=$((fails + 1))
        fi
    done

    if [ $fails -eq 0 ]; then
        echo "  [PASS] $test_name"
        return 0
    else
        return 1
    fi
}

export -f assert_contains
export -f assert_not_contains
export -f assert_count
export -f assert_order
export -f assert_skill_description
export -f assert_no_subjective_words_in_advice
