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

For English, it offers brief corrections during everyday tasks and optional dedicated practice. It revisits patterns through retrieval and new situations, records only demonstrated attempts, and respects pause, skip, and just-answer requests. See [English coaching](skills/always-learning/references/english.md).

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

Run the six English behavior evals with an authenticated Codex CLI using `python3 tests/evaluate.py --model gpt-6-luna --output eval-results/english-1`. Each run requires a new output directory, uses disposable learner state, and checks both responses and persisted progress. The model is configurable; `--timeout` limits each solver or judge invocation in seconds. Reports and traces stay in the ignored output directory. No Yandex tools are required.

Cases are in [english_cases.json](tests/english_cases.json). These are small synthetic regression checks, not evidence of learner improvement or comprehensive language coverage. Passing requires all six cases. The runner uses an isolated Codex profile with the existing login, while the judge sees only the prompt, rubric, response, and state evidence.
