---
name: always-learning
description: Use at the start of every user turn to check enabled learning goals, including English coaching during everyday tasks, dedicated practice, spaced reviews, and progress checks.
---

# Always Learning

Build durable knowledge through everyday work. Demonstrated retrieval, not exposure, drives progress.

## Route

State precedence: `--home`, `ALWAYS_LEARNING_HOME`, `XDG_DATA_HOME/always-learning`, then `~/.local/share/always-learning`. Resolve it before changing directories; preserve that absolute path. Run `python3 scripts/state.py status` from the skill directory.

If registry status fails, report it and stop stateful teaching. Never repair state automatically. Report subject issues only when relevant.

If unconfigured without explicit learning intent, stop silently.

For starting, pausing, resuming, or inspecting subjects, read [subject management](references/subject-management.md).

For an enabled English goal or explicit English enrollment, read [English coaching](references/english.md). The learner's own wording can be relevant even when the task concerns another topic.

Otherwise:

1. Treat semantic relevance to an enabled subject as a hard gate. Lexical overlap and overdue status alone never trigger teaching.
2. Prefer relevant overdue items, then weaker or older evidence.
3. On a clear, non-urgent match, read [the teaching loop](references/teaching-loop.md) and make exactly one smallest useful learning move. Ask for a short prediction before explanation when safe. On ambiguity, stop silently.
4. For urgent or blocking work, complete the task first; use one brief retrospective move only if still relevant.

Honor `skip`, `pause`, and `just answer`. Never delay urgent work, promise unwritten continuity, or record progress without an observed attempt.
