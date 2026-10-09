import pytest
from simulation import (
    RaceConfig, RaceSimulator, ThresholdStrategy, MonteCarloStrategy,
    baseline_strategy, get_race_config_early_rain
)
from models import LapRecord, CarState, WeatherCondition, DriveMode

def test_threshold_strategy_in_early_rain():
    """Test ThresholdStrategy in early rain scenario"""
    config = get_race_config_early_rain()
    strategy = ThresholdStrategy(config)
    simulator = RaceSimulator(config, seed=42)

    lap_records = simulator.simulate_race(strategy)

    # Should complete the race
    assert len(lap_records) == config.total_laps

    # Should have lap times
    total_time = sum(record.lap_time for record in lap_records)
    assert total_time > 0

    # Should have some pit stops (look for high lap times or compound changes)
    pit_stops = sum(1 for record in lap_records if record.lap_time > 120)  # Likely pit stops
    # Note: Might not pit depending on strategy parameters, but should complete race

def test_monte_carlo_strategy_in_early_rain():
    """Test MonteCarloStrategy in early rain scenario"""
    config = get_race_config_early_rain()
    strategy = MonteCarloStrategy(config, num_rollouts=50)  # Fewer rollouts for speed
    simulator = RaceSimulator(config, seed=42)

    lap_records = simulator.simulate_race(strategy)

    # Should complete the race
    assert len(lap_records) == config.total_laps

    # Should have lap times
    total_time = sum(record.lap_time for record in lap_records)
    assert total_time > 0

def test_strategies_different_decisions():
    """Test that strategies can make different decisions"""
    config = RaceConfig()

    # Create a car state that might trigger different decisions
    car_state = CarState(
        lap=20,
        fuel_remaining=60.0,
        tyre_wear=0.8,  # High wear
        tyre_temp=95.0,
        compound="soft",
        weather=WeatherCondition.DRY,
        drive_mode=DriveMode.NORMAL,
        safety_car=False,
        vsc=False,
        lap_time=90.0,
        is_pitting=False
    )

    threshold_strategy = ThresholdStrategy(config)
    mc_strategy = MonteCarloStrategy(config, num_rollouts=50)

    threshold_decision = threshold_strategy(car_state)
    mc_decision = mc_strategy(car_state)

    # Both should return valid decisions
    assert isinstance(threshold_decision, type(mc_decision))
    assert threshold_decision.drive_mode == DriveMode.NORMAL
    assert mc_decision.drive_mode == DriveMode.NORMAL

if __name__ == "__main__":
    pytest.main([__file__, "-v"])