# ExecPlans

Use an ExecPlan for complex features, significant refactors, cross-platform changes, security-sensitive work, or multi-step implementation. Plans are living documents and must be updated as work progresses.

Active plans live in `docs/plans/active/`. Completed plans move to `docs/plans/completed/`.

An ExecPlan must be self-contained enough that a new Codex session can continue from it without chat history.

## Required Format

```markdown
# <Short Task Name>

## Purpose / User Outcome

What user-visible outcome this work enables.

## Scope

What this plan includes.

## Out of Scope

What this plan explicitly does not include.

## Current System Context

Relevant repository state, implemented behavior, docs, and constraints.

## Assumptions

Assumptions that affect implementation or architecture.

## Architecture / Approach

Design approach, boundaries, data flow, and alternatives rejected during planning.

## Milestones

- [ ] Concrete milestone
- [ ] Concrete milestone

## Files / Modules Expected to Change

Expected files and directories.

## Testing and Validation

Tests, linting, type checks, builds, manual validation, and known gaps.

## Security Considerations

Threats, validation rules, secrets handling, and failure modes.

## Risks / Unknowns

Known risks, unresolved questions, and dependencies.

## Progress

Timestamped or session-scoped progress notes.

## Discoveries

Facts learned while implementing that future sessions need.

## Decision Log

Important decisions made during execution and their reasons.

## Completion Criteria

Specific conditions required before moving the plan to completed.

## Final Results

Summary filled in when complete, including validation performed.
```

Keep plans concise but complete. Update the plan before handing off unfinished work and after materially changing direction.
