# Subject Management

Create a subject only after the user expresses long-term learning intent. A one-off explanation is not enrollment.

Run every command below from this skill directory.

## Start

1. Capture the practical outcome. Ask one question only if it is missing.
2. Run `python3 scripts/state.py init-subject`; use `--help` for the exact interface. If it fails, do not claim persistence.
3. Complete the `Outcome`, `Success Criteria`, `Constraints`, and `Out of Scope` sections in `MISSION.md`.
4. In `RESOURCES.md` → `Sources`, define each `### \`source-id\`` with `Link`, `Purpose`, and `Verified: YYYY-MM-DD`. Put unresolved gaps only in `Gaps`. Never invent a citation.
5. In `PLAN.md` → `Objectives`, define each `### \`objective-id\`` with `Outcome`, comma-separated `Concepts`, and `Depends on` objective IDs or `none`.
6. Run `python3 scripts/state.py add-item` for initial retrieval items. Each needs a planned objective ID, effortful prompt, answer criteria, concepts, and source IDs.
7. Run `python3 scripts/state.py validate --subject <id> --activate`. Promise continuity only after it succeeds.
8. Begin a short diagnostic, one question at a time. Diagnostic answers are evidence; generated explanations are not.

Use the smallest source set that covers the current plan. If source access is unavailable, mark the gap and keep affected objectives in draft form.

## Control

- Pause or resume one subject with `python3 scripts/state.py set-enabled --subject <id> --disabled|--enabled`.
- Pause or resume all subjects by omitting `--subject`.
- Show progress from `python3 scripts/state.py status`, separating due reviews from demonstrated evidence.
- Ask for confirmation before deleting learning state. The helper intentionally has no delete command.
