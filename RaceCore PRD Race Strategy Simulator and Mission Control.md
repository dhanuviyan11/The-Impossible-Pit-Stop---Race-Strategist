# RaceCore: Product Requirements Document

**Product:** RaceCore, an endurance race simulation and pit-strategy system with a mission-control dashboard **Version:** 1.0 (MVP) **Date:** October 2026 **Status:** Draft for build

## 1. Overview

In an endurance race a team must balance fuel consumption, tyre wear, pit-stop time, weather and changing race conditions. A strategy that is right at the start can become wrong as conditions change. RaceCore simulates races, recommends when to pit and which tyres to fit, re-plans when conditions change, and proves its value by beating a simple baseline across many simulated races.

The product has three parts:

1. **Simulation engine** that models fuel, tyres, pit stops and random events.
2. **Strategy system** that recommends or selects pit decisions and re-plans live.
3. **Mission-control UI** and an evaluation lab that show the race live and compare strategies over many races.

**Architecture:** all simulation, strategy and evaluation logic runs in a Python backend (FastAPI) that streams race state to the browser over a WebSocket. The React frontend is display-only: it renders state and sends commands such as play, pause, inject rain and override pit.

## 2. Problem statement

Develop a race simulation and strategy system that determines when a car should pit and which strategy it should follow under changing race conditions. It must:

- Simulate fuel consumption and tyre performance over time.
- Account for pit-stop duration and available tyre options.
- Introduce changing or unpredictable race conditions.
- Recommend or select an appropriate strategy during the race.
- Reconsider the strategy when conditions change.
- Compare the proposed strategy against a simple baseline.
- Evaluate performance across multiple simulated races.

## 3. Goals and non-goals

### Goals

- G1. A realistic, tunable race simulator that is deterministic for a given seed.
- G2. An adaptive strategy that visibly changes its recommendation when rain, a safety car or a tyre problem occurs.
- G3. A statistically sound comparison against a baseline over hundreds to thousands of seeded races.
- G4. A polished dashboard that makes decisions explainable (what, why, how confident).
- G5. Calibration from real data (Ergast pit stops and lap times, optional FastF1 tyre data).

### Non-goals (MVP)

- Full multi-car traffic and overtaking physics.
- Real-time connection to live F1 timing.
- Driver-in-the-loop controls beyond manual pit override.
- Machine learning as a core dependency (an online degradation estimator is a stretch goal).
- Use of real team or driver branding.

## 4. Users and personas

| Persona | Need | How RaceCore helps |
| --- | --- | --- |
| Race strategist | Know when to pit now and what the risk is | Strategy Engine card with recommendation, confidence and rationale |
| Performance analyst | Prove a strategy is robust, not lucky | Simulation Lab with paired statistics and scenario heatmap |
| Evaluator or reviewer | Understand the approach quickly | Live demo with event injector, plus clear documentation |
| Student or hobbyist | Experiment with parameters | Settings screen with editable compound and event models |

## 5. Key user stories

1. As a strategist, I see the recommended action each lap (stay out, or pit now to a given compound) with an expected time delta and a confidence level.
2. As a strategist, I can inject rain, a safety car, a slow stop or a puncture and see the plan change within one lap.
3. As a strategist, I can override the recommendation and see the cost of my override in the log.
4. As an analyst, I can run N races per strategy under chosen scenarios and see mean, spread, tail risk and win rate against baseline.
5. As an analyst, I can load any single simulated race into the dashboard and replay it lap by lap.
6. As a user, I can edit tyre, fuel, pit and weather parameters and save or load them as JSON.
7. As a user, I can run the same seed with two strategies side by side and see where they diverge.

## 6. Functional requirements

### 6.1 Simulation

- FR-1. Lap time is computed from base pace, compound offset, tyre degradation (nonlinear with a cliff), fuel weight, weather fit, track temperature, drive mode and noise.
- FR-2. Fuel burns per lap by drive mode. Running out of fuel is a heavy penalty or retirement.
- FR-3. Tyre wear and temperature evolve per lap. Wear above a limit raises puncture risk.
- FR-4. Pit stops cost pit-lane loss plus a stochastic stationary time and reset tyre age. Mandatory-compound and pit-window rules are enforced.
- FR-5. Available compounds: Soft, Medium, Hard, Intermediate, Wet, with limited sets per race.
- FR-6. Random events: rain (Markov chain with imperfect forecast), safety car and virtual safety car (cheaper pit stops), slow stops, punctures and track temperature drift.
- FR-7. Simulations are reproducible: the same seed and strategy give the same result, and all strategies in a comparison share the same event timeline (common random numbers).
- FR-8. Three to seven lightweight rival cars provide position and gap context.

### 6.2 Strategy

- FR-9. **Baseline strategy:** fixed pit laps and compound sequence, with a naive weather reaction.
- FR-10. **Threshold adaptive strategy:** pit when the predicted degradation loss exceeds the pit cost or the weather crosses a threshold.
- FR-11. **Dynamic-programming planner** for the dry deterministic case, used for the initial plan and as a rollout policy.
- FR-12. **Monte Carlo lookahead planner (primary):** each lap or on a trigger, evaluate candidate actions with simulated futures and select by expected time plus a tail-risk term. The risk weight is user-adjustable.
- FR-13. Re-plan triggers: weather change, safety car or VSC, wear threshold, forecast change, puncture, manual request.
- FR-14. Every decision outputs a recommendation, a confidence value, a candidate comparison table and a plain-English reason.

### 6.3 Evaluation

- FR-15. Batch runner executes N races per strategy and scenario in a Python process pool on the server, with progress streamed to the UI.
- FR-16. Scenario presets: always dry, early rain, late rain, flickering damp, early safety car, high-degradation track, random mix.
- FR-17. Metrics: mean, median, standard deviation, 5th and 95th percentile race time, mean finishing position, win rate against baseline, average stops and retirement rate.
- FR-18. Paired comparison with a bootstrap 95% confidence interval and a significance badge.
- FR-19. Scenario-by-strategy heatmap of improvement over baseline, so inconsistent performance is visible.

### 6.4 User interface

- FR-20. Mission-control dashboard: left icon rail, top bar (conditions, lap, position, gap, strategy selector, playback), top-down car with clickable tyre and fuel hotspots, and a card grid.
- FR-21. Cards: Strategy Engine, three gauges (tyre wear, fuel, pace delta), tyre set, telemetry chart with tabs, race control log, race timeline strip with scrubber, and weather forecast.
- FR-22. Playback controls: play, pause, 1x, 4x, 16x, step lap, reset, new seed.
- FR-23. Event injector drawer for rain, safety car, slow stop and puncture.
- FR-24. Manual override: force a pit or compound; the log records it.
- FR-25. Simulation Lab, Strategy Compare and Settings screens as described in the design document.
- FR-26. Keyboard shortcuts: Space (play/pause), Right arrow (next lap), P (request pit), R (reset).

### 6.5 Data and calibration

- FR-27. Configuration is stored as JSON and can be imported and exported.
- FR-28. A preprocessing script derives pit-stop distributions, lap-time baselines, stop counts and safety-car frequency from the Ergast dataset (lap times, pit stops, races, results, status).
- FR-29. A second script derives per-compound pace offsets and degradation curves from FastF1 laps after fuel correction. Wet-tyre parameters stay hand-tuned.

## 7. Data requirements

The supplied Ergast archive provides lap times (1982 to 2026), pit stops with durations, race and circuit metadata, results and retirement status. It does **not** contain tyre compound, tyre age, fuel, weather or safety-car flags. Those are covered by configurable assumptions and, optionally, FastF1 data (2018 onward). The full attribute list is defined in the design document.

## 8. Success metrics

| Metric | Target |
| --- | --- |
| Adaptive strategy vs baseline, mean race time | Better in most preset scenarios, with the bootstrap interval shown |
| Honest reporting | Scenarios where the adaptive strategy ties or loses are shown, not hidden |
| Re-plan latency after an injected event | Recommendation changes within one lap |
| Planner decision time | 300 ms or less per decision on the server |
| Headless race run | Under 100 ms per race |
| Batch of 1000 races per strategy | About 30 seconds or less on a process pool, UI stays responsive |
| Reproducibility | Same seed gives an identical result |
| Code quality | Type-check, tests and build all pass |

## 9. Release plan

| Stage | Deliverable |
| --- | --- |
| 1 | Backend and frontend scaffold: FastAPI health route, pytest, React shell with the dark mission-control look |
| 2 | Deterministic Python engine with tests |
| 3 | Random events, scenario presets and the baseline strategy |
| 4 | Threshold strategy and the vectorised Monte Carlo planner with re-plan triggers |
| 5 | Evaluation: process pool, common random numbers, bootstrap statistics |
| 6 | Live API: sessions, WebSocket streaming, inject and override endpoints |
| 7 | Dashboard wired to the live stream |
| 8 | Simulation Lab, polish and README with results (see the Implementation Plan for hour budgets) |

## 10. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Missing tyre, fuel and weather data in the Ergast archive | Configurable assumptions, optional FastF1 calibration |
| Fuel burn-off masks tyre wear in raw lap times | Fuel-correct before fitting degradation |
| Planner too slow for live use | Time budget, vectorised NumPy rollouts, fewer rollouts when needed |
| Adaptive strategy does not beat baseline everywhere | Report per-scenario results honestly; tune the risk weight |
| Overfitting to a single scenario | Evaluate across presets with common random numbers |
| Visual reference is copyrighted | Take inspiration only; use original assets and placeholder names |

## 11. Open questions

- Is refuelling allowed in the target format, or is fuel fixed at the start?
- Should the race be lap-based or time-based?
- Is a 3D car required or is the SVG car sufficient for the MVP?
- Which real circuit presets should ship first?
