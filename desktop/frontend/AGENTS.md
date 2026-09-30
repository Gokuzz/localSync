# Desktop Frontend Agent Instructions

This directory is for the future React + TypeScript desktop UI.

## Expectations

- Use React and TypeScript.
- Keep backup business logic in backend/domain services, not frontend components.
- Treat the backend API as the boundary for device, transfer, and backup state.
- Organize components by workflow and shared UI only when reuse is real.
- Prefer explicit loading, empty, and error states.
- Maintain type safety at API boundaries.
- Build accessible controls with labels, keyboard support, focus states, and sufficient contrast.
- Ensure layouts are responsive and do not hide important backup status.

The UI may display and initiate actions, but must not redefine backup semantics or deletion behavior.
