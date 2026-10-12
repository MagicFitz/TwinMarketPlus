# Prototype Instructions

Confirmed product architecture (2026-09-12): the four primary spaces are Experiment, Agent, Market, Setting. Experiment owns experiment composition, runs, monitoring and analysis. Agent owns reusable Agent Groups and reserves behavioral-finance tests. Market owns mechanisms, asset packs, data synchronization and environment snapshots. Setting owns model/data-source credentials and extensible global defaults. Run controls and the Tushare settings, market synchronization, immutable snapshots and snapshot selection workflows are active. Other resource-management write workflows remain planned. Preserve existing simulations and the research landing page.

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

Build app UI in `src/`. Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact so the same local prototype can be handed to Sites. Before a Sites handoff, run `npm run build` and `npm run test:sites`; the build must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.
