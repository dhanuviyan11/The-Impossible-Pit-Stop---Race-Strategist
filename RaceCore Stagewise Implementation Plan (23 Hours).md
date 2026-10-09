# RaceCore: Stagewise Implementation Plan (23 hours)

**Companion to:** RaceCore PRD, Design Document and Tech Stack **Version:** 1.0 **Date:** October 2026

## 1. How to use this plan

The prototype is built in nine stages over 23 hours with a Python backend and a display-only React frontend. Work one stage at a time with Claude Code: paste the stage prompt, run what it builds, check the "done when" line, then move on. If a stage overruns its budget by more than 30 minutes, apply the cut list in section 4 instead of finishing every detail.

The visual reference is the mission-control screenshot (left icon rail, top bar with conditions, lap, position and gap, red wireframe car with a tyre popover, and a grid of dark glass cards). Keep the image in the repo at `docs/reference.png` so Claude Code can see it.

## 2. Stage overview

| Stage | Hours | Goal | Done when |
| --- | --- | --- | --- |
| 0. Setup | 0 to 1.5 | FastAPI and React scaffolds, tooling, reference docs in the repo | Backend health route and dark frontend shell both run |
| 1. Engine core | 1.5 to 5.5 | Python physics, pit stops, seeded race simulation | One headless race runs; same seed gives the same result; tests pass |
| 2. Events and baseline | 5.5 to 8 | Rain, safety car, slow stop, baseline strategy, scenario presets | Events appear in the lap log; baseline finishes every preset |
| 3. Adaptive strategies | 8 to 12 | Threshold strategy and vectorised Monte Carlo planner with re-plan triggers | Injected rain makes the adaptive car switch tyres and the baseline does not |
| 4. Evaluation | 12 to 14.5 | Batch runner, common random numbers, bootstrap statistics | A script prints the adaptive improvement with a 95% interval |
| 5. Live API | 14.5 to 16.5 | Sessions, WebSocket stream, inject and override endpoints | A WebSocket client receives lap-by-lap state and reacts to injected events |
| 6. Dashboard | 16.5 to 20.5 | Mission-control UI wired to the stream | You can watch a live race and see recommendations change |
| 7. Lab and polish | 20.5 to 22 | Simulation Lab screen, charts, README | Lab runs 500 races and shows the comparison |
| 8. Buffer | 22 to 23 | Bug fixes, demo rehearsal, backup recording, submit | Submitted |

## 3. Stages in detail

### Stage 0: Setup (0 to 1.5 h)

**Tasks**

- Create `racecore/backend` (FastAPI, Uvicorn, Pydantic v2, NumPy, SciPy, pytest, ruff) and `racecore/frontend` (Vite, React, TypeScript, Tailwind, Zustand, Recharts).
- Add a `/health` route, CORS for the frontend origin, and a `docker-compose.yml` (optional).
- Put the PRD, Design Document, Tech Stack, this plan and the reference screenshot under `docs/`.
- Add the design tokens (near-black background, crimson accent, mono labels) to the frontend and render an empty dark shell with the left rail and top bar.

**Done when:** `uvicorn app.main:app --reload` returns health OK, `npm run dev` shows the dark shell, and `pytest` runs with one placeholder test.

**Claude Code prompt**

> Read docs/PRD, docs/Design Document and docs/Tech Stack. Scaffold the repo as racecore/backend (FastAPI, Pydantic v2, NumPy, SciPy, pytest, ruff) and racecore/frontend (Vite, React, TypeScript, Tailwind, Zustand, Recharts). Add a /health route and CORS. In the frontend render only a dark app shell with a left icon rail and a top bar matching docs/reference.png. Do not build any race logic yet. Tell me the exact commands to run both.

### Stage 1: Engine core (1.5 to 5.5 h)

**Tasks**

- Pydantic models: `RaceConfig`, `CompoundSpec`, `CarState`, `LapRecord`, `Decision`.
- Seeded RNG helper using `numpy.random.default_rng(seed)`.
- Lap-time physics: base pace, compound offset, nonlinear degradation with a cliff, fuel weight effect (about 0.03 s per kg), weather penalty, drive mode, noise.
- Pit stops: pit-lane loss plus a random stationary time; reset tyre age; choose compound; enforce the mandatory-compound rule.
- `simulate_race(config, strategy, seed)` returning final time, lap log and pit log.
- One hard-coded track preset with plausible numbers (about 78 laps, base lap near 90 s).
- Tests: determinism, fuel never negative, tyre age resets after a stop, pit cost applied.

**Done when:** a script runs one race in under 100 ms and prints the lap log summary; tests pass.

**Claude Code prompt**

> Implement the Python engine in backend/engine following Design Document section 3 (lap time model, tyres, fuel, pit stops, determinism). Use Pydantic models and a seeded NumPy generator. Provide simulate\_race(config, strategy, seed) and a trivial strategy that never pits. Add a default track preset and pytest tests for determinism, fuel never negative, tyre age reset on a stop, and pit cost. Stop and show me how to run a race from the command line.

### Stage 2: Events and baseline (5.5 to 8 h)

**Tasks**

- Weather as a Markov chain (dry, damp, wet) with rain intensity, plus a noisy forecast for the planner.
- Safety car and VSC (hazard per lap, duration, cheaper pit loss), slow stop, puncture hazard tied to wear.
- Generate the entire event timeline from the seed alone (common random numbers).
- Baseline strategy: fixed pit laps and compound sequence, naive reaction only when it is already raining hard.
- Scenario presets: `always_dry`, `early_rain`, `late_rain`, `early_sc`, `high_deg`, `random_mix`.

**Done when:** the lap log shows weather and safety-car states, the baseline completes every preset, and two strategies on the same seed see identical events.

**Claude Code prompt**

> Add events to the engine per Design Document 3.5 and 3.7: a weather Markov chain with a noisy forecast, safety car and VSC, slow stops and punctures. Generate the event timeline from the seed only, so every strategy faces identical conditions. Add the BaselineStrategy (fixed pit laps and compounds) and the six scenario presets. Add tests that the timeline is identical across strategies and that rain makes slick tyres slower.

### Stage 3: Adaptive strategies (8 to 12 h)

**Tasks**

- Observation and Decision interface shared by all strategies.
- **Threshold strategy:** pit when predicted degradation loss over the next few laps exceeds the pit cost, or when weather crosses a threshold; choose the compound from the current weather and forecast.
- **Monte Carlo planner:** each lap or on a trigger, enumerate candidates (stay out, pit now to each compound, pit in 1 to 5 laps), run K vectorised NumPy rollouts per candidate, score by mean time plus lambda times the average of the worst 5 percent, output the best action, a confidence value and a plain-English reason.
- Re-plan triggers: weather change, safety car or VSC, wear threshold, puncture, manual request.
- Time budget of 150 to 300 ms per decision; reduce K if the budget is exceeded.
- Optional if time allows: dynamic-programming plan for the dry case.

**Done when:** in the `early_rain` preset with a fixed seed the adaptive car pits for the right tyres within a lap of the rain starting and finishes ahead of the baseline; the decision log records candidates, confidence and reason.

**Claude Code prompt**

> Implement ThresholdStrategy and MonteCarloStrategy per Design Document section 4. The planner must vectorise the K rollouts with NumPy, support re-plan triggers (weather change, safety car, wear threshold, puncture), and return the chosen action, a confidence value, a candidate table with expected time and tail risk, and a plain-English reason. Enforce a per-decision time budget. Add tests that after an injected rain event the adaptive strategy changes its decision and the baseline does not.

### Stage 4: Evaluation (12 to 14.5 h)

**Tasks**

- `run_batch(strategies, scenario, n, seed)` using a `ProcessPoolExecutor`, with a progress callback.
- Common random numbers: the same seed list for every strategy.
- Metrics: mean, median, standard deviation, 5th and 95th percentile race time, mean position, win rate against baseline, average stops, retirement rate.
- Paired difference with a bootstrap 95 percent interval and a significance flag.
- Scenario by strategy matrix for the heatmap.
- A command-line script that prints the comparison table.

**Done when:** a command prints a table such as "adaptive beats baseline by X s, 95% interval \[a, b\]" for each scenario, and 1000 races per strategy finish in about 30 seconds or less.

**Claude Code prompt**

> Build backend/engine/evaluate.py and stats.py per Design Document section 5: a process-pool batch runner with common random numbers, the listed metrics, a paired bootstrap 95% interval and a significance flag, and a scenario by strategy matrix. Add a CLI script that prints a results table for all presets. Do not hide scenarios where the adaptive strategy ties or loses.

### Stage 5: Live API (14.5 to 16.5 h)

**Tasks**

- Session manager holding one live race, with a lap loop as an async task.
- `POST /race` creates a race; `WS /race/{id}` streams lap state, decisions and events and accepts play, pause, speed, step and reset.
- `POST /race/{id}/inject` for rain, safety car, slow stop and puncture; `POST /race/{id}/override` for manual pit.
- `GET /race/{id}/decisions` and `GET /race/{id}/replay`.
- `POST /evaluate` and `GET /evaluate/{job}` for batch jobs with progress.
- Generate TypeScript types from the OpenAPI schema.

**Done when:** a test client connects, plays a race, injects rain and sees the recommendation change in the stream.

**Claude Code prompt**

> Add the FastAPI layer per Design Document 8.1: a session manager, a race WebSocket that streams lap state, decisions and events, inject and override endpoints, decisions and replay endpoints, and evaluate endpoints with progress. Keep the engine free of web imports. Add API tests with the FastAPI test client. Generate TypeScript types from the OpenAPI schema into the frontend.

### Stage 6: Dashboard (16.5 to 20.5 h)

**Tasks**

- Top bar: air, track, rain or humidity, wind, lap, position, gap, strategy selector, playback controls, PIT WINDOW OPEN chip.
- Top-down SVG car in the red wireframe style with four tyre hotspots and a fuel hotspot; clicking opens a card with connector line (surface and inner temperature, wear, compound, age).
- Strategy Engine card: recommended action, confidence ring, reason, candidate table, risk slider, accept and override buttons.
- Three semicircle gauges (tyre wear, fuel, pace delta), tyre set card, telemetry bar chart with tabs, race control log, race timeline strip.
- Event injector drawer (rain, safety car, slow stop, puncture).
- Everything driven by the WebSocket through a Zustand store.

**Done when:** you can press play, watch the race, inject rain and see the Strategy Engine card, log and timeline update.

**Claude Code prompt**

> Build the dashboard in the frontend to match docs/reference.png: left icon rail, top bar, top-down SVG car with clickable tyre and fuel hotspots, and the cards listed in Design Document 7.2 mapped to race strategy. Drive all of it from the backend WebSocket via Zustand; the frontend contains no race logic. Add playback controls and the event injector drawer. Use the design tokens (near-black, crimson accent, mono telemetry labels). Show me how to run it.

### Stage 7: Lab and polish (20.5 to 22 h)

**Tasks**

- Simulation Lab screen: choose scenario, strategies and number of races; progress bar; histogram of race times for both strategies; summary table; paired difference with interval.
- Scenario heatmap if time allows; button to load a race into the dashboard.
- README: architecture, how to run, evaluation results with seeds, and the "why no ML is needed" note.
- Visual pass against the reference image.

**Done when:** the lab runs 500 races and shows the comparison, and the README explains how to reproduce it.

**Claude Code prompt**

> Add the Simulation Lab screen: controls for scenario, strategies and race count, a progress bar fed by the evaluate endpoints, overlaid histograms of race time, a summary table, and the paired difference with its bootstrap interval. Then write a README covering architecture, setup, reproducing the evaluation with seeds, and why machine learning is not required.

### Stage 8: Buffer (22 to 23 h)

- Fix bugs and rough edges; run all tests; confirm the build passes.
- Rehearse the demo twice (script below) and record a screen capture as a fallback.
- Submit with the README and the three design documents.

## 4. If you fall behind: what to cut

Cut in this order, stopping as soon as you are back on schedule.

1. 3D car, Compare screen, Settings editor, keyboard shortcuts.
2. Rivals and traffic: show only your car with a fixed gap to leader.
3. Dynamic-programming planner: keep the threshold strategy and the Monte Carlo planner.
4. Scenario heatmap: keep the histogram and the summary table.
5. FastF1 and Ergast calibration: use hard-coded plausible numbers and mention the calibration scripts in the README.

Never cut: the baseline, the adaptive re-plan under rain or safety car, the multi-race comparison with a confidence interval, and the live dashboard. These are what the problem statement asks for.

## 5. Checkpoints

| Hour | Must be true |
| --- | --- |
| 5.5 | One race runs headless and is deterministic |
| 12 | Adaptive beats baseline in the early-rain scenario on a fixed seed |
| 14.5 | Evaluation script prints the comparison with an interval |
| 16.5 | WebSocket stream works with injected events |
| 20.5 | Dashboard is live and presentable |
| 22 | Lab, README and tests are done |

If a checkpoint is missed, spend the next hour only on getting back to it.

## 6. Working rules for Claude Code

- One stage per request; ask it to stop and say how to run what it built.
- Ask for tests at the end of stages 1 to 5, because the engine is where bugs hide.
- Check results are believable before polishing: if the adaptive strategy does not win in the rain scenario, tune penalties and the forecast noise rather than moving on.
- Keep one saved seed for the demo so the rain moment is reproducible.
- Commit after each stage so you can roll back.
- The engine never imports FastAPI; the frontend never contains race logic.

## 7. Demo script (3 to 4 minutes)

1. Show the dashboard and explain the cards in one sentence each.
2. Start a race on the saved seed with the Adaptive strategy selected and speed at 4x.
3. Open a tyre popover to show wear and temperature.
4. Inject rain around mid-race; point at the Strategy Engine card changing, the reason text, and the log row.
5. Switch to the Simulation Lab, run 500 races for the early-rain scenario, and show the histogram and the interval.
6. Show the scenario table, including any scenario where the adaptive strategy only ties, and say why that is honest.
7. Close with the architecture: Python backend does all the work, the frontend only displays.

## 8. Definition of done

- Backend tests pass and the frontend builds without type errors.
- Same seed gives the same race.
- Injecting rain or a safety car changes the adaptive recommendation within one lap, with a logged reason.
- The lab shows adaptive versus baseline across many races with a bootstrap interval.
- README explains how to run, reproduce results, and why no machine learning is required.
