from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uuid
import asyncio
from typing import Dict, List, Optional
import json
from simulation import (
    RaceConfig, RaceSimulator, ThresholdStrategy, MonteCarloStrategy,
    baseline_strategy, SCENARIO_PRESETS
)
from engine.evaluate import run_batch
from models import CarState, LapRecord, Decision, WeatherCondition, DriveMode
from engine.evaluate import evaluate_strategies
from engine.stats import calculate_metrics
import numpy as np

app = FastAPI(title="RaceCore API", description="Race Strategy Simulator and Mission Control")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session manager for live races
class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, dict] = {}

    def create_session(self, config: RaceConfig, strategy_name: str = "Baseline", seed: int = None) -> str:
        session_id = str(uuid.uuid4())
        if seed is None:
            seed = np.random.randint(0, 2**31 - 1)  # Use int32 max positive value

        # Get strategy callable
        strategy_map = {
            "Baseline": baseline_strategy,
            "Threshold": lambda cs: ThresholdStrategy(config)(cs),
            "MonteCarlo": lambda cs: MonteCarloStrategy(config, num_rollouts=200)(cs)
        }
        strategy_func = strategy_map.get(strategy_name, baseline_strategy)

        simulator = RaceSimulator(config, seed)
        self.sessions[session_id] = {
            "config": config,
            "strategy_name": strategy_name,
            "strategy_func": strategy_func,
            "simulator": simulator,
            "seed": seed,
            "task": None,
            "lap_records": [],
            "is_running": False,
            "current_lap": 0,
            "websocket": None
        }
        return session_id

    def get_session(self, session_id: str) -> Optional[dict]:
        return self.sessions.get(session_id)

    def end_session(self, session_id: str):
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if session["task"] and not session["task"].done():
                session["task"].cancel()
            del self.sessions[session_id]

session_manager = SessionManager()


async def race_simulation_task(session_id: str):
    """Background task to simulate a race and send updates via WebSocket"""
    session = session_manager.get_session(session_id)
    if not session:
        return

    try:
        simulator = session["simulator"]
        strategy_func = session["strategy_func"]

        # Initialize car state
        from models import CarState
        car_state = CarState(
            lap=0,
            fuel_remaining=session["config"].fuel_capacity,
            tyre_wear=0.0,
            tyre_temp=session["config"].compounds[1].optimal_temp,
            compound=session["config"].compounds[1].name,
            weather=session["config"].weather_transition_prob.keys().__iter__().__next__() if hasattr(session["config"].weather_transition_prob.keys(), '__iter__') else list(session["config"].weather_transition_prob.keys())[0],
            drive_mode=session["config"].DriveMode.NORMAL if hasattr(session["config"], 'DriveMode') else session["config"].drive_mode.__class__.NORMAL,
            safety_car=False,
            vsc=False,
            lap_time=0.0,
            is_pitting=False
        )

        # Set initial weather to dry
        car_state.weather = session["config"].WeatherCondition.DRY if hasattr(session["config"], 'WeatherCondition') else list(session["config"].weather_transition_prob.keys())[0]

        session["is_running"] = True
        session["current_lap"] = 0
        session["lap_records"] = []

        # Simulate each lap
        for lap in range(1, session["config"].total_laps + 1):
            # Check if session was ended
            if session_id not in session_manager.sessions:
                break

            session = session_manager.get_session(session_id)
            if not session or not session["is_running"]:
                break

            # Get strategy decision
            decision = strategy_func(car_state)

            # Handle pit stop
            if decision.pit_stop and decision.compound_choice:
                car_state.is_pitting = True
                car_state.tyre_wear = 0.0
                car_state.compound = decision.compound_choice
                # Reset tyre temp to optimal for new compound
                for compound in session["config"].compounds:
                    if compound.name == decision.compound_choice:
                        car_state.tyre_temp = compound.optimal_temp
                        break
            else:
                car_state.is_pitting = False

            # Calculate lap time (simplified - would use simulator._calculate_lap_time in full implementation)
            # For now, use a simple calculation
            base_time = session["config"].base_lap_time

            # Simple lap time calculation
            lap_time = base_time

            # Fuel effect
            fuel_effect = (car_state.fuel_remaining / session["config"].fuel_capacity) * 0.02
            lap_time += base_time * fuel_effect

            # Wear effect
            wear_effect = car_state.tyre_wear * 0.03
            lap_time += base_time * wear_effect

            # Weather effect
            weather_multipliers = {
                session["config"].WeatherCondition.DRY: 1.0,
                session["config"].WeatherCondition.DAMP: 1.03,
                session["config"].WeatherCondition.WET: 1.15
            } if hasattr(session["config"], 'WeatherCondition') else {"dry": 1.0, "damp": 1.03, "wet": 1.15}

            weather_key = car_state.weather.value if hasattr(car_state.weather, 'value') else str(car_state.weather)
            lap_time *= weather_multipliers.get(weather_key, 1.0)

            # Drive mode effect
            drive_mode_multipliers = {
                session["config"].DriveMode.NORMAL: 1.0,
                session["config"].DriveMode.PUSH: 0.98,
                session["config"].DriveMode.CONSERVE: 1.02
            } if hasattr(session["config"], 'DriveMode') else {"normal": 1.0, "push": 0.98, "conserve": 1.02}

            drive_mode_key = car_state.drive_mode.value if hasattr(car_state.drive_mode, 'value') else str(car_state.drive_mode)
            lap_time *= drive_mode_multipliers.get(drive_mode_key, 1.0)

            # Safety car / VSC effect
            if car_state.safety_car:
                lap_time *= 1.4
            elif car_state.vsc:
                lap_time *= 1.1

            # Add some noise
            import random
            noise = random.uniform(-base_time * 0.01, base_time * 0.01)
            lap_time += noise

            # Ensure lap time is positive
            lap_time = max(lap_time, base_time * 0.8)

            # Update car state
            car_state.lap = lap
            car_state.fuel_remaining = max(0, car_state.fuel_remaining - 2.0)  # Simplified fuel consumption
            car_state.tyre_wear = min(1.0, car_state.tyre_wear + 0.01)  # Simplified wear increase
            car_state.lap_time = lap_time

            # Create lap record
            from models import LapRecord
            import time
            lap_record = LapRecord(
                lap=lap,
                lap_time=lap_time,
                fuel_remaining=car_state.fuel_remaining,
                tyre_wear=car_state.tyre_wear,
                tyre_temp=car_state.tyre_temp,
                compound=car_state.compound,
                weather=car_state.weather,
                drive_mode=car_state.drive_mode,
                safety_car=car_state.safety_car,
                vsc=car_state.vsc,
                timestamp=time.time()
            )

            session["lap_records"].append(lap_record)
            session["current_lap"] = lap

            # Send update via WebSocket if connected
            if session["websocket"]:
                try:
                    await session["websocket"].send_json({
                        "type": "lap_update",
                        "lap": lap_record.dict(),
                        "decision": decision.dict() if hasattr(decision, 'dict') else {
                            "pit_stop": decision.pit_stop,
                            "compound_choice": decision.compound_choice,
                            "drive_mode": decision.drive_mode.value if hasattr(decision.drive_mode, 'value') else str(decision.drive_mode),
                            "fuel_mode": decision.fuel_mode
                        }
                    })
                except:
                    # WebSocket disconnected
                    break

            # Small delay to make it observable
            await asyncio.sleep(0.1)

        # Race finished
        session["is_running"] = False
        if session["websocket"]:
            try:
                await session["websocket"].send_json({
                    "type": "race_finished",
                    "lap_records": [record.dict() for record in session["lap_records"]]
                })
            except:
                pass

    except Exception as e:
        print(f"Error in race simulation: {e}")
        session["is_running"] = False
    finally:
        # Clean up
        if session_id in session_manager.sessions:
            session = session_manager.get_session(session_id)
            if session:
                session["is_running"] = False


@app.get("/health")
async def health_check():
    return {"status": "OK", "message": "RaceCore API is running"}

@app.get("/")
async def root():
    return {"message": "Welcome to RaceCore API"}


@app.post("/race")
async def create_race(
    scenario: str = "always_dry",
    strategy: str = "Baseline",
    seed: Optional[int] = None
):
    """Create a new race session"""
    # Get scenario config
    if scenario not in SCENARIO_PRESETS:
        raise HTTPException(status_code=400, detail=f"Unknown scenario: {scenario}")

    config_func = SCENARIO_PRESETS[scenario]
    config = config_func()

    # Create session
    session_id = session_manager.create_session(config, strategy, seed)

    return {
        "session_id": session_id,
        "scenario": scenario,
        "strategy": strategy,
        "message": "Race session created successfully"
    }


@app.websocket("/race/{session_id}")
async def race_websocket(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for streaming race state"""
    await websocket.accept()

    session = session_manager.get_session(session_id)
    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return

    # Store websocket reference
    session["websocket"] = websocket

    try:
        # Start the race simulation task if not already running
        if not session["is_running"]:
            session["task"] = asyncio.create_task(race_simulation_task(session_id))

        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for messages from client (e.g., play/pause/speed controls)
                data = await websocket.receive_text()
                # For now, we just echo back or handle simple commands
                # In a full implementation, we'd parse commands to control playback
                await websocket.send_json({"type": "echo", "message": data})
            except WebSocketDisconnect:
                break
            except Exception as e:
                print(f"WebSocket error: {e}")
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        # Clean up websocket reference
        if session_id in session_manager.sessions:
            session = session_manager.get_session(session_id)
            if session:
                session["websocket"] = None


@app.post("/race/{session_id}/inject")
async def inject_event(session_id: str, event_type: str, **kwargs):
    """Inject an event into the race (rain, safety car, etc.)"""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # For now, we'll just acknowledge the injection
    # In a full implementation, we'd modify the simulator state
    return {
        "session_id": session_id,
        "event_type": event_type,
        "message": f"Event {event_type} injected (simplified implementation)"
    }


@app.post("/race/{session_id}/override")
async def override_decision(session_id: str, decision: dict):
    """Override the strategy decision with manual input"""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # For now, we'll just acknowledge the override
    # In a full implementation, we'd use this decision instead of the strategy's
    return {
        "session_id": session_id,
        "decision": decision,
        "message": "Decision override acknowledged (simplified implementation)"
    }


@app.get("/race/{session_id}/decisions")
async def get_decisions(session_id: str):
    """Get the list of decisions made in the race"""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Return decisions from lap records
    decisions = []
    for record in session["lap_records"]:
        # In a full implementation, we'd store decisions separately
        # For now, we'll create a placeholder
        decisions.append({
            "lap": record.lap,
            "pit_stop": False,  # Placeholder
            "compound_choice": None,
            "drive_mode": str(record.drive_mode),
            "fuel_mode": "normal"
        })

    return {
        "session_id": session_id,
        "decisions": decisions
    }


@app.get("/race/{session_id}/replay")
async def get_replay(session_id: str):
    """Get the full race replay"""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session_id,
        "lap_records": [record.dict() for record in session["lap_records"]],
        "total_laps": len(session["lap_records"]),
        "is_complete": not session["is_running"] and len(session["lap_records"]) >= session["config"].total_laps
    }


@app.post("/evaluate")
async def start_evaluation(
    scenario: str = "always_dry",
    strategies: List[str] = ["Baseline", "Threshold"],
    num_races: int = 20
):
    """Start a batch evaluation job"""
    # Validate scenario
    if scenario not in SCENARIO_PRESETS:
        raise HTTPException(status_code=400, detail=f"Unknown scenario: {scenario}")

    # Map strategy names to functions
    strategy_map = {
        "Baseline": baseline_strategy,
        "Threshold": lambda cs: ThresholdStrategy(RaceConfig())(cs),
        "MonteCarlo": lambda cs: MonteCarloStrategy(RaceConfig(), num_rollouts=100)(cs)
    }

    # Validate strategies
    valid_strategies = []
    for strategy_name in strategies:
        if strategy_name in strategy_map:
            valid_strategies.append((strategy_name, strategy_map[strategy_name]))
        else:
            raise HTTPException(status_code=400, detail=f"Unknown strategy: {strategy_name}")

    if not valid_strategies:
        raise HTTPException(status_code=400, detail="No valid strategies provided")

    # Generate job ID
    job_id = str(uuid.uuid4())

    # In a full implementation, we'd run this as a background task
    # For now, we'll run it synchronously (but in practice would be async)
    try:
        results = evaluate_strategies(valid_strategies, scenario, num_races)
        return {
            "job_id": job_id,
            "status": "completed",
            "results": results
        }
    except Exception as e:
        return {
            "job_id": job_id,
            "status": "failed",
            "error": str(e)
        }


@app.get("/evaluate/{job_id}")
async def get_evaluation_result(job_id: str):
    """Get the result of an evaluation job"""
    # In a full implementation, we'd look up the job by ID
    # For now, we'll return a placeholder since we run evaluations synchronously
    return {
        "job_id": job_id,
        "status": "not_implemented",
        "message": "Evaluation job lookup not implemented in this simplified version"
    }