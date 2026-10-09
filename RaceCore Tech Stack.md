# RaceCore: Tech Stack

**Companion to:** RaceCore PRD and Design Document **Version:** 1.0 **Date:** October 2026

## 1. Summary

RaceCore has a Python backend and a display-only web frontend. FastAPI runs the whole simulation, strategy and evaluation engine and streams race state over a WebSocket. The React dashboard only renders that state and sends commands such as play, pause and inject rain. Calibration scripts live in the same Python codebase. Machine learning is not required for the core system.

## 2. Decision principles

- **Backend owns the logic:** simulation, strategies and statistics live in Python; the frontend holds no race logic.
- **Engine is independent of the web layer:** the engine package imports no FastAPI code, so it is testable and runnable from a script.
- **Deterministic by default:** all randomness is seeded so results are reproducible.
- **Never block the event loop:** long computations run in a thread or process pool.
- **Explainable over opaque:** search and optimisation before learned models.
- **Typed contract:** Pydantic models define the API and generate TypeScript types for the frontend.

## 3. Stack at a glance

| Concern | Choice | Why |
| --- | --- | --- |
| Backend language | Python 3.11 or later | One language for engine, statistics and calibration |
| API | FastAPI with Uvicorn | Async REST and WebSocket, automatic OpenAPI schema |
| Live streaming | WebSocket per race | Low-latency lap-by-lap updates |
| Data models | Pydantic v2 | Validation and a typed API contract |
| Simulation | NumPy | Fast arrays, seeded generator |
| Planner | Vectorised NumPy rollouts (Numba optional) | Runs K futures at once to meet the time budget |
| Batch evaluation | ProcessPoolExecutor | Uses all CPU cores for thousands of races |
| Statistics | NumPy and SciPy | Bootstrap intervals and paired tests |
| Calibration | pandas and FastF1 | Fit parameters from Ergast and FastF1 data |
| Backend tests and lint | pytest, ruff | Fast feedback |
| Frontend language | TypeScript (strict) | Type safety in the display layer |
| Build tool and UI | Vite and React 18 | Component model suits dashboard cards |
| Styling | Tailwind CSS with CSS variables, shadcn/ui | Design tokens in one place, accessible primitives |
| State | Zustand | Small store for streamed race state |
| Charts | Recharts or visx | Telemetry, histograms, heatmap |
| Gauges and car | Custom SVG | Full control of the mission-control look |
| Animation | Framer Motion | Card transitions and number tweening |
| Type sharing | openapi-typescript | Frontend types generated from the backend schema |
| Run and deploy | Docker Compose, two services | One command to start backend and frontend |

## 4. Frontend

### 4.1 Framework and build

Vite with React 18 and strict TypeScript. The frontend talks to the backend through a typed REST client and one WebSocket per live race. TypeScript types are generated from FastAPI's OpenAPI schema with openapi-typescript, so the two sides cannot drift.

### 4.2 Styling and components

Tailwind with design tokens defined as CSS variables (background, surface, accent, status colours, radius). shadcn/ui supplies accessible primitives; cards, gauges, the car and the timeline are custom components. Fonts are Inter for UI and JetBrains Mono for telemetry labels and numbers, with tabular numerals.

### 4.3 State management

Two Zustand stores:

- **raceStore:** current lap state, history for replay, decisions, events, playback status.
- **settingsStore:** configuration (compounds, pit model, weather, events, strategy parameters) with JSON import and export.

### 4.4 Visualisation

- **Custom SVG:** top-down car with tyre and fuel hotspots, semicircle gauges, timeline strip.
- **visx or Recharts:** lap-time and wear telemetry, histograms and violins for the lab, bootstrap interval charts, scenario heatmap.
- **Framer Motion:** eased value changes and the pulsing pit-window chip.
- **Stretch:** react-three-fiber for a 3D car.

## 5. Backend: simulation and strategy engine (Python)

- **Language:** Python 3.11 or later, with type hints and Pydantic v2 models for configs, lap state, decisions and results.
- **Packages:** `engine` (physics, events, rivals, simulate, strategies, evaluate, stats) with no web imports, and `app` (FastAPI routes, WebSocket and session manager).
- **Determinism:** a NumPy generator seeded per race creates the event timeline from the seed alone, giving common random numbers across strategies.
- **Planner speed:** the K rollouts of a candidate action run as one vectorised NumPy operation instead of a Python loop. Numba is added only if profiling shows it is needed.
- **Performance targets:** a headless race under 100 ms, a planner decision within 150 to 300 ms, and 1000 races per strategy in under about 30 seconds on a process pool.
- **Numerics:** NumPy arrays in hot paths; avoid creating objects per lap.

## 6. API and concurrency

| Component | Job |
| --- | --- |
| FastAPI (async) | REST routes for config, race control and evaluation jobs |
| WebSocket per race | Streams lap state, decisions and events; receives play, pause, speed, step and reset |
| Session manager | Holds one live race per session and runs its lap loop as an async task |
| ProcessPoolExecutor | Runs batch evaluations across CPU cores |

Evaluation jobs return a job id; the UI polls it or listens for progress on a WebSocket. The pool size defaults to the number of CPU cores minus one, and the planner runs in a thread so the event loop stays responsive.

## 7. Data and calibration toolkit

This part lives in the backend's calibration package, runs offline and produces JSON that the engine loads.

| Source | Content | Used for |
| --- | --- | --- |
| Ergast archive (supplied zip) | Lap times, pit stops, races, circuits, results, status | Pit-stop duration distributions, base lap times per circuit, stop counts, stint lengths, safety-car frequency, historical benchmarks |
| FastF1 (optional) | Compound, tyre life, stints, track status, weather per lap (2018 onward) | Pace offsets and degradation curves per compound after fuel correction, rain frequency and temperature |

- **Libraries:** Python 3, pandas, numpy, fastf1.
- **Scripts:** an Ergast preprocessing script and a FastF1 pipeline with two commands, export and fit. Export downloads laps and weather to a CSV; fit fuel-corrects dry green-flag laps and writes a compound specification JSON.
- **Caveats:** the Ergast data has no tyre, fuel or weather columns; fuel load and the fuel penalty are assumptions; wet-tyre parameters stay hand-tuned; FastF1 needs internet access to the live-timing API and caches downloads locally.

## 8. Machine learning position

| Question | Answer |
| --- | --- |
| Is ML needed for the core? | No. The simulator is known, so search, dynamic programming and Monte Carlo planning solve it directly and stay explainable |
| Optional ML 1 | Online degradation estimator using recursive least squares on lap-time residuals |
| Optional ML 2 | Reinforcement-learning policy (PPO or DQN) trained on the simulator as a comparison, using Gymnasium and Stable-Baselines3 in Python |

Both are stretch goals and are kept outside the critical path.

## 9. Testing and quality

- **pytest** for determinism, physics invariants, event frequencies, strategy reactions and bootstrap statistics.
- **API tests** with the FastAPI test client for REST routes and the WebSocket stream.
- **Performance checks** for headless race time and batch throughput.
- **Frontend:** type-check and build must pass before any stage is considered done.
- **Reproducibility:** results are documented with seeds, so any chart can be regenerated.

## 10. Build, deploy and tooling

- **Backend commands:** uvicorn for the server, pytest for tests, ruff for lint and format.
- **Frontend commands:** dev, build, preview, typecheck.
- **Local run:** two terminals (backend and frontend), or `docker compose up` with two services.
- **Hosting:** the backend on any container or Python host (Render, Fly.io, Railway), the frontend on any static host, with CORS set for the frontend origin.
- **Configuration:** presets stored as JSON in the repo; the API reads and writes them.
- **Development workflow:** the project is built stage by stage with an AI coding assistant using the PRD, Design Document and Implementation Plan as the specification, stopping after each stage for review.

## 11. Optional extensions (later)

If shared results, user accounts or heavier batch jobs are needed later, extend the backend.

| Concern | Option |
| --- | --- |
| Persistence | SQLite or Postgres for saved configurations and run results |
| Job queue | Celery or RQ with Redis for long evaluation jobs |
| Speed | Numba or Cython for hot loops in the engine |
| Auth | Simple token or OAuth if multiple users are needed |

This is out of scope for the MVP.

## 12. Alternatives considered

| Choice | Alternative | Reason not chosen |
| --- | --- | --- |
| Python backend for all logic | TypeScript engine in the browser | Python suits simulation and statistics and keeps one language for engine and calibration |
| WebSocket streaming | Polling | Higher latency and more requests for live playback |
| Zustand | Redux Toolkit | More boilerplate than needed |
| Custom SVG car | 3D model | Higher effort; kept as a stretch goal |
| Monte Carlo planning | Reinforcement learning only | Needs training, less explainable, harder to tune |
| Streamlit | React dashboard | Less control over the mission-control visual style |

## 13. Risks

| Risk | Mitigation |
| --- | --- |
| Python planner too slow for live use | Vectorise rollouts in NumPy, set a time budget, lower K when needed, run in a thread |
| Event loop blocked by heavy compute | Use thread and process pools; keep handlers async |
| WebSocket drops mid-race | Client reconnects and requests the current lap; server keeps session state |
| Frontend and backend types drift | Generate TypeScript types from the OpenAPI schema |
| FastF1 data gaps or API changes | Cache locally, skip failed races, keep assumptions configurable |
| Visual reference copyright | Inspiration only; original assets and placeholder names |
