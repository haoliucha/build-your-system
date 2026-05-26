# goal-creator tests

Test-driven development per `superpowers:writing-skills` IRON LAW.

## Layout

```
tests/
  prompts/                  # Baseline pressure scenarios (RED phase inputs)
  baseline-results/         # Captured output WITHOUT skill (RED phase evidence)
  with-skill-results/       # Captured output WITH skill (GREEN phase evidence)
  test-helpers.sh           # Forked from superpowers, plus domain assertions
  run-content-tests.sh      # Tier 1: grep SKILL.md for required sections
  run-behavior-tests.sh     # Tier 2/3: spawn subagent with/without skill, assert behavior
```

## TDD Phases

- **RED**: Run prompts WITHOUT skill (fresh Claude),capture verbatim rationalizations
- **GREEN**: Write SKILL.md addressing those rationalizations,re-run,verify compliance
- **REFACTOR**: Find new rationalizations,close loopholes,re-test
