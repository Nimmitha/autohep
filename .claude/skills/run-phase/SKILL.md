---
name: run-phase
description: Drive one phase of a study end-to-end — analyst execution, review board, arbiter verdict, gate handling, log + commit. Use when the user says to run/continue/advance a study.
---

# run-phase

Runs the current phase of `studies/<name>/` through its gate. This is the
orchestrator's main loop; launch the **orchestrator** agent to execute it, or
follow these steps directly when acting as the orchestrator.

## Steps

1. Read `studies/<name>/manifest.json` → current `phase` and `iteration`; read the
   log tail (`python tools/experiment_log.py tail studies/<name>`) to confirm
   state consistency. Mismatch → stop and reconcile before anything else.
2. Log `phase_start`. Launch the **analyst** agent with exactly: `PHYSICS_GOAL.md`,
   the phase section of `framework/methodology.md`, `framework/conventions.md`,
   `framework/scaling.md`, prior phase artifacts, and (iteration > 0) the arbiter's
   consolidated findings from the previous round. Nothing else.
3. When the analyst finishes, verify its declared artifact exists and every figure
   passes `python tools/plot_validator.py <figs> --json` (blinded mode unless
   manifest says otherwise). Missing artifact → relaunch analyst once, then ESCALATE.
4. Convene the **review-board** skill on the artifact.
5. Apply the arbiter verdict:
   - **PASS** → log `review_verdict`, freeze artifact hashes into
     `manifest.json.frozen[phase]`, bump `phase`, reset `iteration`, `git add -A &&
     git commit` in the study repo with the verdict in the message.
   - **ITERATE** → bump `iteration` (max 3), go to step 2 with findings.
   - **ESCALATE** → present the human a concise summary and stop.
6. Special gates:
   - Entering **phase4b**: do NOT launch the analyst. Assemble the unblinding
     checklist (methodology §Phase 4b) with evidence links, present to the human,
     and only on explicit approval log `human_gate`/`human_response` and let the
     analyst unblind the seeded 10% subsample.
   - Entering **phase4c**: requires a second explicit human approval referencing
     the 4b result.
7. Never run more than one phase per invocation of this skill unless the user
   explicitly asked for continuous running; even then, stop at every human gate
   and every ESCALATE.
