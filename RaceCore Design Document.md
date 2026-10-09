# RaceCore: Design Document

**Companion to:** RaceCore PRD **Version:** 1.0 **Date:** October 2026

## 1. Purpose

This document describes how RaceCore is designed: the simulation model, the strategy algorithms, the evaluation method, the data model and the user interface. It is the reference for implementation.

## 2. System architecture

RaceCore has a Python backend and a display-only frontend. The backend (FastAPI) owns all simulation, strategy and evaluation logic and holds the live race state. The React frontend renders what the backend sends and issues commands. The engine package imports no web code, so it runs in tests and scripts.

| Layer | Responsibility |
| --- | --- |
| Frontend (React) | Dashboard, Simulation Lab, Compare and Settings screens; renders streamed state and sends commands |
| Frontend state (Zustand) | Latest lap state, history for replay, playback and UI settings |
| API layer (FastAPI) | REST routes for config, race control and evaluation; one WebSocket per live race |
| Session manager | One live race per session: runs the lap loop, applies injected events and manual overrides |
| Engine (Python package) | Physics, events, rivals, strategies, planner, statistics |
| Batch pool | ProcessPoolExecutor running seeded races for evaluation |
| Config and data | JSON presets, calibration outputs from Ergast and FastF1 |

Data flow: the user presses play and the frontend sends a play command over the WebSocket. Each lap the session manager runs the strategy decision and the physics step, then streams the lap state, decision and any events back, and the store updates every card. Evaluation runs start with a REST call, execute in the process pool, and are polled for progress and results.

## 3. Simulation model

### 3.1 Lap time

```
lapTime = baseLapTime
        + compound.paceOffset
        + degradationPenalty(compound, tyreAge)
        + fuelPenaltyPerKg * fuel
        + weatherPenalty(compound, weather, rainIntensity)
        + temperaturePenalty(compound, trackTemp)
        + driveModeDelta(mode)
        + safetyCarOverride
        + noise
```

- **Degradation** grows nonlinearly with tyre age and adds a steep penalty after a compound-specific cliff age.
- **Fuel** makes the car lighter and faster as it burns off (about 0.03 s per kg). This effect must be modelled explicitly, otherwise it hides tyre wear.
- **Weather fit** penalises slick tyres in rain heavily and wet tyres on a dry track moderately.
- **Drive modes:** Push is faster but wears tyres and burns fuel faster. Save does the opposite.
- **Safety car:** lap time is overridden to a slow multiple of base pace.

### 3.2 Tyres

Each compound has a pace offset, degradation rate and exponent, cliff age and penalty, optimal temperature window and weather suitability. Tyre temperature follows a first-order model that relaxes toward a target set by track temperature and drive mode, and it feeds the hotspot cards in the UI. Wear above the safe limit raises puncture probability.

### 3.3 Fuel

Fuel burns per lap by drive mode. The default is a fixed starting load with no refuelling, and refuelling can be switched on in configuration. Running dry triggers a heavy penalty or retirement.

### 3.4 Pit stops

```
pitCost = pitLaneLoss + max(0, Normal(stationaryMean, stationarySigma))
```

Under a safety car or VSC the pit-lane loss is multiplied by a factor below one, because the field is slow. A stop resets tyre age and selects a new compound. Rules enforce a pit window and a mandatory number of distinct dry compounds.

### 3.5 Random events

- **Weather:** a Markov chain over dry, damp and wet with per-lap transition probabilities. The planner sees a noisy forecast, not the truth.
- **Safety car and VSC:** per-lap hazard, with a duration of several laps.
- **Slow stop:** the tail of the stationary-time distribution.
- **Puncture:** rare hazard scaled by tyre wear.
- **Track temperature:** slow drift.

### 3.6 Rivals

Three to seven AI cars follow fixed strategies under the same physics. Position and gaps come from cumulative race time. Detailed traffic is out of scope.

### 3.7 Determinism

All randomness uses a seeded generator. The event timeline is generated from the seed alone, so every strategy faces identical conditions (common random numbers). This makes comparisons paired and far less noisy.

## 4. Strategy design

Every strategy implements the same interface and is called once per lap before the lap runs. It receives an observation (own state, weather and forecast, rivals) and returns a decision (pit or not, compound, drive mode).

| Strategy | Idea | Role |
| --- | --- | --- |
| Baseline | Fixed pit laps and compound sequence, naive reaction to weather | Comparison benchmark |
| Threshold adaptive | Pit when predicted degradation loss exceeds amortised pit cost, or weather crosses a threshold | Explainable heuristic |
| Dynamic programming | Minimum remaining time over state (lap, tyre age, compound, compounds used) for the dry deterministic case | Initial plan and rollout policy |
| Monte Carlo lookahead (primary) | Simulate many futures for each candidate action and pick the best risk-adjusted one | Main strategy |
| Online degradation estimator (stretch) | Recursive least squares on lap-time residuals | Optional learned component |

### 4.1 Monte Carlo lookahead planner

The planner re-plans every lap and immediately on any trigger event (weather change, safety car, wear threshold, forecast change, puncture, manual request).

1. Enumerate candidates: stay out, pit now to each available compound, or pit in 1 to 5 laps.
2. For each candidate run K rollouts (64 to 200) of the rest of the race, vectorised as NumPy arrays so all K run together. Weather comes from the forecast belief and safety cars from the hazard model. After the first action the rollout follows the DP or threshold policy.
3. Score each candidate as mean time plus lambda times the tail-risk measure (average of the worst 5 percent of outcomes). Lambda is a user slider.
4. Pick the lowest score. Confidence is the margin over the second-best option relative to its standard error.
5. Produce a plain-English reason, for example: safety car deployed, pitting now saves about 9 seconds over staying out.
6. Run inside a time budget of about 150 to 300 ms per decision on the server.

This is a receding-horizon method: it weighs the immediate pit cost against future consequences, then repeats with fresh information.

### 4.2 Why no machine learning is required

The simulator is known and controllable, so search and optimisation answer the question directly, are explainable and need no training data. Learning is optional, either to estimate degradation online or to train a reinforcement-learning policy as a comparison.

## 5. Evaluation design

- Run N races per strategy and scenario (100, 500 or 2000) using common random numbers, executed in a Python process pool with progress reported to the UI.
- **Scenarios:** always dry, early rain, late rain, flickering damp, early safety car, high-degradation track, random mix.
- **Metrics:** mean, median, standard deviation, 5th and 95th percentile race time, mean position, win rate against baseline, average stops, retirement rate.
- **Statistics:** paired differences with a bootstrap 95 percent confidence interval and a significance badge.
- **Consistency view:** a strategy by scenario heatmap showing mean improvement over baseline, so a strategy that wins on average but fails in one scenario is visible.
- Results that tie or lose are reported, not hidden.

## 6. Data design

### 6.1 Input tables

| Table | Key attributes |
| --- | --- |
| race\_config | total laps, base lap time, fuel start and per-lap burn, fuel penalty per kg, pit-lane loss, stationary mean and sigma, pit window, mandatory compounds, safety-car pit multiplier, noise sigma |
| compound\_spec | compound, pace offset, degradation rate and exponent, cliff age and penalty, safe age, wear rate, optimal temperature and window, weather penalties, sets available |
| weather\_model | scenario, Markov transition probabilities, rain intensity, forecast noise and horizon, air and track temperature, humidity, wind |
| event\_model | safety-car and VSC hazard and duration, puncture hazard, slow-stop probability and extra time |
| driver\_car\_profile | tyre-management skill, fuel efficiency, pace factor, consistency, mode deltas and multipliers |
| rivals | pace factor, strategy type, planned pit laps, compound sequence, grid position |
| strategy\_config | baseline pit laps and compounds, threshold margin, rollouts, horizon, risk lambda, time budget, triggers |

### 6.2 Output tables

| Table | Content |
| --- | --- |
| lap\_log | per car per lap: lap time, cumulative time, position, gaps, compound, tyre age and wear, four tyre temperatures, fuel, drive mode, weather, safety-car state, pit flag |
| pit\_stop\_log | lap, reason, compounds in and out, pit-lane and stationary time, under safety car, decided by strategy or manual |
| event\_log | lap, event type, severity, duration, message for the race control log |
| decision\_log | per decision and candidate: expected time, spread, tail risk, delta versus best, chosen flag, confidence, rationale, compute time |
| race\_result | final time and position, stops, total pit time, retirement, fuel left, maximum wear, compounds used, rule violations, re-plans |
| batch\_summary | per strategy and scenario: mean, median, std, percentiles, win rate, paired delta with interval, significance, stops, retirement rate |

### 6.3 Calibration sources

**Ergast archive (supplied).** Contains lap times, pit stops, races, circuits, results and status. It has no tyre, fuel, weather or safety-car columns. Use it for pit-stop duration distributions (for 2018 onward the median is about 24 seconds with a spread of about 20 to 36 seconds), lap-time baselines per circuit, stop counts (about 1.85 per driver per race), stint lengths, safety-car frequency inferred from field-wide slow laps, and historical benchmarks.

**FastF1 (optional, 2018 onward).** Provides compound, tyre life, stints, track status and per-lap weather. A pipeline script exports laps and fits per-compound pace offset and degradation after fuel correction. A quick check on raw Ergast laps showed laps getting faster with age because fuel burn-off dominated, which is why fuel correction is required.

**Assumptions.** Fuel load (110 kg start) and fuel penalty (0.03 s per kg) are assumptions. Wet and intermediate parameters are hand-tuned.

## 7. User interface design

### 7.1 Visual language

Inspired by a mission-control dashboard reference: near-black background, crimson accents with soft glow, glass cards with thin borders, monospaced uppercase telemetry labels, tabular numerals so values do not jitter. Original assets only; placeholder driver and team names.

| Token | Value |
| --- | --- |
| Background | #07070A |
| Card surface | #0E0E12 with a 1 px border at 6 percent white |
| Accent | #E0103A, soft #FF4D6D |
| Status colours | ok #3DDC97, warn #FFB020, danger #FF3B4E, info #4DA3FF |
| Text | #F2F2F5, muted #8A8A99 |
| Radius | 20 px cards, 14 px chips |
| Fonts | Inter for UI, JetBrains Mono for telemetry |

### 7.2 Dashboard layout

- **Left rail:** round icon buttons for Dashboard, Strategy, Tyres, Weather, Simulation Lab and Settings; active item filled crimson; a LIVE indicator under the logo.
- **Top bar:** conditions strip (air, track, humidity or rain, wind), lap counter, position, gap to leader, strategy selector, playback controls and settings.
- **Main area (left):** large top-down SVG car with four tyre hotspots and a fuel hotspot. Clicking a hotspot opens a card with a connector line showing status, surface and inner temperature, wear, compound and age.
- **Card grid (right):**

| Reference element | RaceCore card |
| --- | --- |
| Powertrain card | Strategy Engine: recommended action, confidence ring, rationale, candidate table, risk slider, accept or override |
| Three semicircle gauges | Tyre wear, fuel (kilograms and laps left), pace delta |
| Brake system schematic | Tyre set: four corner temperatures and wear with compound and age |
| Engine load bar chart | Telemetry chart with tabs for lap time, tyre wear, fuel and gap; pit laps flagged and weather bands behind the bars |
| System logs table | Race control log: weather, safety car, tyres, strategy and pit events, newest at top |
| Car health strip | Race timeline: coloured by tyre stint, pit markers, rain and safety-car bands, draggable replay scrubber |

### 7.3 Other screens

- **Simulation Lab:** choose strategies, scenario, number of races, seed and risk lambda; progress bar; overlaid histograms of race time; summary table; paired-delta chart with confidence interval; scenario heatmap; click a race to replay it on the dashboard.
- **Strategy Compare:** same seed, two strategies, side-by-side timelines, lap-by-lap cumulative delta, and markers where decisions diverged.
- **Settings:** sliders and tables for degradation, pit loss, rain probability and safety-car hazard; compound editor; JSON import and export.

### 7.4 Key interactions

- Playback: play, pause, speed 1x, 4x, 16x, step lap, reset, new seed.
- Event injector: rain now, deploy safety car, slow next stop, puncture. The Strategy Engine card must change its recommendation within one lap and add a log row.
- PIT WINDOW OPEN chip pulses in the top bar and on the timeline when a stop is recommended.
- Manual override is allowed and logged as MANUAL OVERRIDE.
- Keyboard shortcuts: Space, Right arrow, P, R.
- Loading states while the server computes; the UI never freezes.

## 8. Module structure

```
racecore/
  backend/
    app/         main.py routes.py ws.py sessions.py schemas.py
    engine/      config.py rng.py physics.py events.py simulate.py rivals.py
                 evaluate.py stats.py
      strategies/  baseline.py threshold.py dp.py mpc.py
    calibration/ ergast_prep.py fastf1_pipeline.py
    data/        config presets, calibration JSON
    tests/
  frontend/      (display only)
    src/         api, store, components, pages, styles
  docker-compose.yml
```

### 8.1 API surface

| Endpoint | Purpose |
| --- | --- |
| GET and PUT /config | Read and edit race, compound, weather and event settings |
| POST /race | Create a live race (seed, scenario, strategy); returns a race id |
| WS /race/{id} | Server streams lap state, decisions and events; client sends play, pause, speed, step, reset |
| POST /race/{id}/inject | Inject rain, safety car, slow stop or puncture |
| POST /race/{id}/override | Manual pit or compound |
| GET /race/{id}/decisions | Candidate table and rationale per lap |
| GET /race/{id}/replay | Full lap log for replay on the dashboard |
| POST /evaluate | Start a batch (strategies, scenario, N, seed); returns a job id |
| GET /evaluate/{job} | Progress and results: histogram data, summary, bootstrap interval, heatmap |

## 9. Testing strategy

- **Tooling:** pytest for the backend; type-check and build for the frontend.
- **Determinism:** same seed and strategy give identical output.
- **Physics invariants:** fuel never negative, tyre age resets on a stop, mandatory compound rule enforced, pit cost is lower under safety car.
- **Event tests:** weather chain transition frequencies match configuration over many races.
- **Strategy tests:** adaptive strategy changes its decision after an injected rain or safety car; baseline does not.
- **Statistics tests:** bootstrap interval covers a known synthetic difference.
- **API tests:** REST routes and the WebSocket stream work through the FastAPI test client.
- **Performance:** a headless race under 100 ms; 1000 races in about 30 seconds on a process pool.

## 10. Acceptance criteria

1. The dashboard is visually faithful to the reference and the car hotspots are clickable.
2. Injecting rain or a safety car mid-race changes the adaptive recommendation within one lap, with a logged reason.
3. The lab runs 1000 races per strategy without freezing the UI.
4. Across preset scenarios the adaptive planner beats the baseline on mean race time with the confidence interval shown, and cases where it does not are reported.
5. Results are reproducible by seed and the build and tests pass cleanly.
