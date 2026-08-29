# Teach Me

A collection of Agent Skills for durable, practical learning.

## Current foundation

Teach Me currently draws on ideas from *Make It Stick* by Peter C. Brown, Henry L. Roediger III, and Mark A. McDaniel:

- retrieval practice
- spaced practice
- interleaving
- desirable difficulties
- corrective feedback
- transfer to real problems

The goal is recall and application, not familiarity.

## Skills

### [`always-learning`](skills/always-learning/SKILL.md)

Uses semantically relevant everyday work for cross-session learning. It maintains explicit goals, trusted sources, dependency-aware objectives, retrieval items, and review history.

```sh
npx skills add drveles/teach-me@always-learning
```

## Verify

```sh
python3 -m unittest discover -s tests -v
python3 skills/always-learning/scripts/state.py --help
npx skills add . --list
```

Behavior scenarios are in [`tests/scenarios`](tests/scenarios).
