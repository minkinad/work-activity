# Frontend agent guidance

## Design rules

- Keep the dashboard dependency-free unless a task clearly justifies a framework or
  package.
- Put orchestration in `src/app.js`, HTTP in `src/api-client.js`, pure state/formatting in
  focused modules, and DOM construction in `src/renderers.js` or `src/dom.js`.
- Do not embed API data with `innerHTML`, `outerHTML`, `insertAdjacentHTML`, inline event
  handlers, `document.write`, or `eval`.
- Keep dashboard credentials in `sessionStorage`, never persistent local storage, URLs,
  logs, or markup.
- Do not auto-fetch screenshot bytes. Require an explicit operator action, revoke object
  URLs when finished, and preserve the capture confirmation dialog.
- Preserve keyboard access, visible focus, semantic controls, live status messages, and
  reduced-motion behavior.

## Validation

From `frontend/` run:

```bash
npm ci --ignore-scripts
npm audit --omit=dev
npm run ci
```

Add unit tests for pure logic and extend `scripts/check.mjs` when introducing a new static
security invariant. Do not edit `dist/`; regenerate it with `npm run build`.
