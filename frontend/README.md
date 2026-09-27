# TwinMarket frontend

The product UI is a standalone React + TypeScript + Vite application using Tailwind CSS and shadcn/ui-style local primitives. The former `studio/` UI is migration reference only.

```bash
npm install
npm run dev
npm run test
npm run build
```

Vite proxies `/api` to `http://127.0.0.1:8766` by default. Production Web builds use `VITE_API_BASE_URL`. Electron must load this same build and may inject the local backend before the bundle runs:

```js
window.__TWINMARKET_CONFIG__ = { apiBaseUrl: "http://127.0.0.1:8766" };
```

No Electron-specific renderer exists: Web and Electron share `src/main.tsx`. Run `npm run api:types` while the FastAPI backend is listening to refresh `src/lib/openapi.generated.ts`; handwritten response DTOs live in `src/lib/api-types.ts` because the current Python routes do not yet declare response models.
