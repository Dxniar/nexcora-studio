# Nexcora Studio Mini App

React/TypeScript client for the same-origin Python API at `/api/v1`.

The interface supports English, Russian and Kazakh, with a saved account language shared with the bot. It includes separate client and owner navigation, responsive layouts, light/dark themes and Telegram safe-area handling. User-written project content is preserved in its original language.

Use Node.js 24 and the locked dependencies. From this directory:

```sh
npm ci
npm run typecheck
npm run build
npx playwright install chromium
npm run test:e2e
```

`npm run dev` serves Vite on loopback and proxies `/api` to `127.0.0.1:8765`.
The production build is `dist/`, served by the Python app.

Run the backend and migrations using the [development guide](../docs/development.md). A frontend development server alone does not provide authentication, project data or storage.

Authentication uses the official Telegram Web App script and the backend HMAC verification. The opaque bearer token is stored in session storage. There is no demo login or production identity bypass. Outside Telegram, the app explains how to reopen it through the bot.

Browser tests start `e2e/server.py` with the real application, isolated temporary SQLite, a synthetic signed Telegram identity, and temporary local storage. They do not use real users, messages, credentials, or cloud resources. The SDK UI bridge is injected only by the tests. Test storage exists only in this fixture. On Windows, an installed Edge can run headlessly with fresh contexts; Linux uses Playwright Chromium. `PYTHON` can override the test interpreter. Browser screenshots are written to `artifacts/`.

These browser checks verify the interface against the real service layer on disposable SQLite. They complement the repository's PostgreSQL integration checks; they do not prove a real Telegram launch, live object storage, or production delivery.

See the [main overview](../README.md) for the product workflow and [deployment guide](../docs/deployment.md) for runtime configuration. Never put bot tokens, storage keys or other secrets in `VITE_*` variables; those values become part of the public frontend bundle.
