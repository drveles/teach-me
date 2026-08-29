# Always Learning

An Agent Skill that turns relevant everyday work into spaced, evidence-based learning.

It maintains explicit missions, trusted sources, dependency-aware plans, retrieval items, review history, and deterministic spacing. Teaching activates only when the current session is semantically relevant to an enabled subject.

## Install

```sh
npx skills add drveles/teach-me@always-learning
```

Start with a concrete outcome:

> I am learning distributed systems for backend interviews. Keep teaching me in relevant future sessions.

## Automatic activation

Implicit invocation is host-dependent. For strict activation, add this to the host's persistent instructions:

> Before every response, invoke `$always-learning`. It must remain silent unless an enabled subject is semantically relevant or its registry cannot be read.

## State

Set `ALWAYS_LEARNING_HOME` to choose the state directory. The fallback is `$XDG_DATA_HOME/always-learning`, then `~/.local/share/always-learning`.

The skill never stores learning state inside its installation directory.

## Verify

```sh
python3 -m unittest discover -s tests -v
python3 skills/always-learning/scripts/state.py --help
npx skills add . --list
```

Forward-test behavior with fresh agents against `tests/scenarios/*.md`.
