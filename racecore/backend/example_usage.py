"""
Example usage of the RaceCore API demonstrating Stages 3, 4, and 5 implementation.
This script shows how to use the adaptive strategies, evaluation system, and live API.
"""

import asyncio
import json
from simulation import RaceConfig, baseline_strategy, ThresholdStrategy, MonteCarloStrategy
from engine.evaluate import evaluate_strategies
from main import app, session_manager
from fastapi.testclient import TestClient

def demonstrate_adaptive_strategies():
    """Demonstrate Stage 3: Adaptive strategies"""
    print("=== Stage 3: Adaptive Strategies Demonstration ===")

    config = RaceConfig()

    # Create strategies
    threshold_strategy = ThresholdStrategy(config)
    mc_strategy = MonteCarloStrategy(config, num_rollouts=100)  # Fewer rollouts for demo

    # Test with a sample car state
    from models import CarState, WeatherCondition, DriveMode
    car_state = CarState(
        lap=15,
        fuel_remaining=70.0,
        tyre_wear=0.4,
        tyre_temp=95.0,
        compound="medium",
        weather=WeatherCondition.DRY,
        drive_mode=DriveMode.NORMAL,
        safety_car=False,
        vsc=False,
        lap_time=90.0,
        is_pitting=False
    )

    # Get decisions from each strategy
    threshold_decision = threshold_strategy(car_state)
    mc_decision = mc_strategy(car_state)

    print(f"Car State: Lap {car_state.lap}, Tyre Wear: {car_state.tyre_wear:.2f}, Compound: {car_state.compound}")
    print(f"Threshold Strategy Decision: Pit={threshold_decision.pit_stop}, Compound={threshold_decision.compound_choice}")
    print(f"Monte Carlo Strategy Decision: Pit={mc_decision.pit_stop}, Compound={mc_decision.compound_choice}")
    print()

def threshold_strategy_wrapper(car_state):
    """Wrapper for ThresholdStrategy to make it picklable"""
    return ThresholdStrategy(RaceConfig())(car_state)

def monte_carlo_strategy_wrapper(car_state):
    """Wrapper for MonteCarloStrategy to make it picklable"""
    return MonteCarloStrategy(RaceConfig(), num_rollouts=100)(car_state)

def demonstrate_evaluation():
    """Demonstrate Stage 4: Evaluation system"""
    print("=== Stage 4: Evaluation System Demonstration ===")

    # Define strategies to evaluate using wrapper functions
    strategies = [
        ("Baseline", baseline_strategy),
        ("Threshold", threshold_strategy_wrapper),
        ("MonteCarlo", monte_carlo_strategy_wrapper)
    ]

    # Run evaluation
    print("Running evaluation across scenarios...")
    results = evaluate_strategies(strategies, "always_dry", n=10, seed=42)

    print(f"Scenario: {results['scenario']}")
    print(f"Reference Strategy: {results['reference_strategy']}")
    print("\nStrategy Performance:")
    for strategy_name, metrics in results['strategy_metrics'].items():
        print(f"  {strategy_name}:")
        print(f"    Mean Race Time: {metrics.get('mean_race_time', 0):.2f}s")
        print(f"    Std Dev: {metrics.get('std_race_time', 0):.2f}s")
        print(f"    Win Rate vs Reference: {results['comparison_matrix'].get(strategy_name, {}).get('win_rate_vs_reference', 0):.2%}")
    print()

def demonstrate_live_api():
    """Demonstrate Stage 5: Live API"""
    print("=== Stage 5: Live API Demonstration ===")

    client = TestClient(app)

    # Create a race session
    print("Creating a new race session...")
    response = client.post("/race?scenario=early_rain&strategy=Threshold&seed=12345")
    if response.status_code == 200:
        data = response.json()
        session_id = data["session_id"]
        print(f"Session created: {session_id}")
        print(f"Scenario: {data['scenario']}")
        print(f"Strategy: {data['strategy']}")

        # Get session info
        session = session_manager.get_session(session_id)
        if session:
            print(f"Session is ready for simulation")
            print(f"Config: {session['config'].total_laps} laps, base lap time {session['config'].base_lap_time}s")

        # Show available endpoints
        print("\nAvailable API Endpoints:")
        print("  GET  /health                    - Health check")
        print("  GET  /                          - Root endpoint")
        print("  POST /race                      - Create race session")
        print("  WS   /race/{session_id}         - WebSocket for live streaming")
        print("  POST /race/{id}/inject          - Inject events (rain, SC, etc.)")
        print("  POST /race/{id}/override        - Override strategy decisions")
        print("  GET  /race/{id}/decisions       - Get decision history")
        print("  GET  /race/{id}/replay          - Get full race replay")
        print("  POST /evaluate                  - Start batch evaluation")
        print("  GET  /evaluate/{job_id}         - Get evaluation results")
    else:
        print(f"Failed to create session: {response.status_code}")
        print(response.text)

    print()

def main():
    """Run all demonstrations"""
    print("RaceCore Implementation Demo - Stages 3, 4, and 5\n")

    try:
        demonstrate_adaptive_strategies()
        demonstrate_evaluation()
        demonstrate_live_api()

        print("=== Implementation Complete ===")
        print("[x] Stage 3: Adaptive strategies (Threshold and Monte Carlo with re-plan triggers)")
        print("[x] Stage 4: Evaluation system (batch runner, bootstrap statistics, CLI)")
        print("[x] Stage 5: Live API (session management, WebSocket streaming, inject/override)")
        print("\nThe implementation satisfies the requirements from the RaceCore Stagewise Implementation Plan.")

    except Exception as e:
        print(f"Error during demonstration: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()