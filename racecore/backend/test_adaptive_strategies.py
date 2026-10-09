import pytest
import numpy as np
from simulation import (
    RaceConfig, RaceSimulator, ThresholdStrategy, MonteCarloStrategy,
    ReplanTrigger
)
from models import CarState, Decision, WeatherCondition, DriveMode


def test_threshold_strategy_initialization():
    """Test that ThresholdStrategy initializes correctly"""
    config = RaceConfig()
    strategy = ThresholdStrategy(config)

    assert strategy.config == config
    assert strategy.look_ahead_laps == 3
    assert strategy.weather_threshold == 0.1
    assert strategy.time_budget_ms == 50


def test_monte_carlo_strategy_initialization():
    """Test that MonteCarloStrategy initializes correctly"""
    config = RaceConfig()
    strategy = MonteCarloStrategy(config)

    assert strategy.config == config
    assert strategy.num_rollouts == 1000
    assert strategy.look_ahead_laps == 5
    assert strategy.lambda_risk_aversion == 0.5
    assert strategy.time_budget_ms == 200


def test_threshold_strategy_decision():
    """Test that ThresholdStrategy returns a valid Decision"""
    config = RaceConfig()
    strategy = ThresholdStrategy(config)

    # Create a car state
    car_state = CarState(
        lap=10,
        fuel_remaining=50.0,
        tyre_wear=0.3,
        tyre_temp=90.0,
        compound="medium",
        weather=WeatherCondition.DRY,
        drive_mode=DriveMode.NORMAL,
        safety_car=False,
        vsc=False,
        lap_time=90.0,
        is_pitting=False
    )

    # Get decision
    decision = strategy(car_state)

    # Check that it's a valid Decision
    assert isinstance(decision, Decision)
    assert decision.drive_mode == DriveMode.NORMAL
    assert decision.fuel_mode == "normal"
    # pit_stop and compound_choice may vary based on conditions


def test_monte_carlo_strategy_decision():
    """Test that MonteCarloStrategy returns a valid Decision"""
    config = RaceConfig()
    strategy = MonteCarloStrategy(config, num_rollouts=100)  # Use fewer rollouts for testing

    # Create a car state
    car_state = CarState(
        lap=10,
        fuel_remaining=50.0,
        tyre_wear=0.3,
        tyre_temp=90.0,
        compound="medium",
        weather=WeatherCondition.DRY,
        drive_mode=DriveMode.NORMAL,
        safety_car=False,
        vsc=False,
        lap_time=90.0,
        is_pitting=False
    )

    # Get decision
    decision = strategy(car_state)

    # Check that it's a valid Decision
    assert isinstance(decision, Decision)
    assert decision.drive_mode == DriveMode.NORMAL
    assert decision.fuel_mode == "normal"
    # pit_stop and compound_choice may vary based on conditions


def test_should_replan():
    """Test the should_replan logic"""
    config = RaceConfig()
    strategy = ThresholdStrategy(config)

    # Create a car state
    car_state = CarState(
        lap=10,
        fuel_remaining=50.0,
        tyre_wear=0.3,
        tyre_temp=90.0,
        compound="medium",
        weather=WeatherCondition.DRY,
        drive_mode=DriveMode.NORMAL,
        safety_car=False,
        vsc=False,
        lap_time=90.0,
        is_pitting=False
    )

    # Should replan on first lap (last_decision_lap = -1)
    assert strategy.should_replan(car_state, -1) == True

    # Should not replan if just decided last lap
    assert strategy.should_replan(car_state, 9) == False

    # Should replan after 5 laps
    assert strategy.should_replan(car_state, 4) == True


def test_weather_trigger_replan():
    """Test that weather change triggers replan"""
    config = RaceConfig()
    strategy = ThresholdStrategy(config)

    # Create car states with different weather
    car_state_dry = CarState(
        lap=10,
        fuel_remaining=50.0,
        tyre_wear=0.3,
        tyre_temp=90.0,
        compound="medium",
        weather=WeatherCondition.DRY,
        drive_mode=DriveMode.NORMAL,
        safety_car=False,
        vsc=False,
        lap_time=90.0,
        is_pitting=False
    )

    car_state_wet = CarState(
        lap=11,
        fuel_remaining=48.0,
        tyre_wear=0.35,
        tyre_temp=85.0,
        compound="medium",
        weather=WeatherCondition.WET,  # Different weather
        drive_mode=DriveMode.NORMAL,
        safety_car=False,
        vsc=False,
        lap_time=100.0,
        is_pitting=False
    )

    # Set last decision lap to 10
    strategy.last_decision_lap = 10
    strategy.last_weather = WeatherCondition.DRY

    # Should replan due to weather change
    assert strategy.should_replan(car_state_wet, 10) == True


def test_run_strategies_in_simulation():
    """Test that strategies work in a full simulation"""
    config = RaceConfig()

    # Test ThresholdStrategy
    threshold_strategy = ThresholdStrategy(config)
    simulator = RaceSimulator(config, seed=42)
    lap_records = simulator.simulate_race(threshold_strategy)

    assert len(lap_records) == config.total_laps

    # Test MonteCarloStrategy with fewer rollouts for speed
    mc_strategy = MonteCarloStrategy(config, num_rollouts=50)
    simulator2 = RaceSimulator(config, seed=42)
    lap_records2 = simulator2.simulate_race(mc_strategy)

    assert len(lap_records2) == config.total_laps


def test_replan_trigger_enum():
    """Test that ReplanTrigger enum works correctly"""
    assert ReplanTrigger.WEATHER_CHANGE.value == "weather_change"
    assert ReplanTrigger.SAFETY_CAR.value == "safety_car"
    assert ReplanTrigger.WEAR_THRESHOLD.value == "wear_threshold"
    assert ReplanTrigger.PUNCTURE.value == "puncture"
    assert ReplanTrigger.MANUAL_REQUEST.value == "manual_request"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])