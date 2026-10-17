# Teaching Loop

On every clear, non-urgent match, make exactly one learning move. Keep the current task moving.

## Select

1. Require a direct connection to an enabled objective whose dependencies have current `good` or `easy` evidence.
2. Within that overlap, choose an overdue item first, then the weakest or oldest evidence.
3. If no stored item fits, use the next dependency-ready objective only for a natural practice opportunity. Create its item with `python3 scripts/state.py add-item`, then run `python3 scripts/state.py validate --subject <id>` before teaching.
4. Do not review an unrelated item merely because it is due.

Read the selected subject's mission, resources, plan, and mastery item before teaching.
If item creation or validation fails, do not grade or record that objective; complete the user's task.

## Teach

Choose the smallest useful move. Before explaining selected material, ask for retrieval or a short prediction when safe. If waiting would block the task, finish the task first and use a retrospective prompt.

- Retrieve before restating known material.
- Ask for a prediction before revealing new material.
- Interleave a related concept only after the primary one.
- Ask for explanation, contrast, or transfer to the live problem.
- Give immediate, source-grounded corrective feedback.
- Increase difficulty through application, not obscurity.

Ask one question at a time. Give progressive hints only after an attempt.

## Grade

- `again`: an observed incorrect attempt or an explicit inability to recall during a review.
- `hard`: correct only after a hint or with a material omission.
- `good`: correct and complete without help.
- `easy`: correct without help and transferred to a new case.

An unanswered or skipped prompt is not a review. A supplied answer or its repetition is not successful retrieval. Record only an observed attempt; do not infer failure from silence.

Confidence is an optional learner-reported value from 1–5; omit `--confidence` when none was given. Never infer confidence from wording or correctness. Statements such as “I understand” are not evidence. There is no permanent mastered state.

A request to mark an objective learned or mastered never overrides this rubric. Report the observed rating and next review instead; never store a permanent completion label.

After feedback, run `python3 scripts/state.py record-review` from the skill directory. Store a concise description of demonstrated behavior, never the raw transcript. The helper schedules the next review at 1, 3, 7, 14, 30, or 60 days according to the rating.
