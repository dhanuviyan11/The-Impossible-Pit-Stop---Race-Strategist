import pytest
from simulation import RaceSimulator, default_strategy, RaceConfig
from models import CarState, Decision, WeatherCondition, DriveMode

def test_simulator_initialization():
    """Test that the simulator initializes correctly"""
    config = RaceConfig()
    simulator = RaceSimulator(config, seed=42)
    assert simulator.config == config
    assert simulator.seed == 42
    assert len(simulator.lap_records) == 0

def test_default_strategy():
    """Test the default strategy function"""
    car_state = CarState()
    decision = default_strategy(car_state)
    assert decision.pit_stop == False
    assert decision.drive_mode == DriveMode.NORMAL
    assert decision.fuel_mode == "normal"

def test_compound_spec_lookup():
    """Test looking up compound specifications"""
    from simulation import RaceSimulator
    config = RaceConfig()
    simulator = RaceSimulator(config, seed=42)

    soft_compound = simulator._get_compound_spec("soft")
    assert soft_compound.name == "soft"
    assert soft_compound.base_grip == 1.2

    medium_compound = simulator._get_compound_spec("medium")
    assert medium_compound.name == "medium"
    assert medium_compound.base_grip == 1.1

def test_lap_time_calculation():
    """Test lap time calculation"""
    from simulation import RaceSimulator
    config = RaceConfig()
    simulator = RaceSimulator(config, seed=42)

    car_state = CarState(
        lap=1,
        fuel_remaining=100.0,
        tyre_wear=0.0,
        tyre_temp=90.0,
        compound="medium",
        weather=WeatherCondition.DRY,
        drive_mode=DriveMode.NORMAL,
        safety_car=False,
        vsc=False,
        lap_time=90.0,
        is_pitting=False
    )

    decision = Decision(pit_stop=False, drive_mode=DriveMode.NORMAL, fuel_mode="normal")
    lap_time = simulator._calculate_lap_time(car_state, decision)

    # Should be close to base lap time (90s) with small variations
    assert 80 <= lap_time <= 110

def test_fuel_update():
    """Test fuel consumption calculation"""
    from simulation import RaceSimulator
    config = RaceConfig()
    simulator = RaceSimulator(config, seed=42)

    car_state = CarState(fuel_remaining=50.0)
    decision = Decision(pit_stop=False, drive_mode=DriveMode.NORMAL, fuel_mode="normal")

    new_fuel = simulator._update_fuel(car_state, decision)
    # Should consume some fuel but not all
    assert 0 <= new_fuel < 50.0

def test_tyre_wear_update():
    """Test tyre wear calculation"""
    from simulation import RaceSimulator
    config = RaceConfig()
    simulator = RaceSimulator(config, seed=42)

    car_state = CarState(tyre_wear=0.0)
    decision = Decision(pit_stop=False, drive_mode=DriveMode.NORMAL, fuel_mode="normal")

    new_wear = simulator._update_tyre_wear(car_state, decision)
    # Should have some wear but not exceed 100%
    assert 0 <= new_wear <= 1.0

def test_deterministic_simulation():
    """Test that the same seed produces the same results"""
    from simulation import RaceSimulator, default_strategy

    config = RaceConfig()
    simulator1 = RaceSimulator(config, seed=123)
    laps1 = simulator1.simulate_race(default_strategy)

    simulator2 = RaceSimulator(config, seed=123)
    laps2 = simulator2.simulate_race(default_strategy)

    # Should be identical
    assert len(laps1) == len(laps2)
    for i in range(len(laps1)):
        assert laps1[i].lap_time == laps2[i].lap_time
        assert laps1[i].fuel_remaining == laps2[i].fuel_remaining
        assert laps1[i].tyre_wear == laps2[i].tyre_wear

def test_weather_transitions():
    """Test weather Markov chain"""
    from simulation import RaceSimulator
    config = RaceConfig()
    simulator = RaceSimulator(config, seed=456)

    # Start with dry weather
    weather = WeatherCondition.DRY
    new_weather = simulator._update_weather(weather)

    # Should be one of the three weather conditions
    assert new_weather in [WeatherCondition.DRY, WeatherCondition.DAMP, WeatherCondition.WET]

def test_safety_car_logic():
    """Test safety car deployment logic"""
    from simulation import RaceSimulator
    config = RaceConfig()
    simulator = RaceSimulator(config, seed=789)

    car_state = CarState(safety_car=False, vsc=False)
    sc_deployed, vsc_deployed = simulator._check_safety_car_events(1)

    # Should return boolean values
    assert isinstance(sc_deployed, bool)
    assert isinstance(vsc_deployed, bool)

def test_full_race_simulation():
    """Test that a full race simulation completes successfully"""
    from simulation import RaceSimulator, default_strategy

    config = RaceConfig()
    simulator = RaceSimulator(config, seed=999)
    lap_records = simulator.simulate_race(default_strategy)

    # Should have records for all laps
    assert len(lap_records) == config.total_laps

    # Lap numbers should be sequential
    for i, record in enumerate(lap_records):
        assert record.lap == i + 1

    # Lap times should be reasonable
    for record in lap_records:
        assert 40 <= record.lap_time <= 180  # Between 40s and 3min per lap

    # Fuel should decrease over time
    fuel_levels = [record.fuel_remaining for record in lap_records]
    assert fuel_levels[0] >= fuel_levels[-1]  # Should start with more or equal fuel

    # Tyre wear should generally increase (with pit stops resetting it)
    # Just check that values are in valid range
    for record in lap_records:
        assert 0 <= record.tyre_wear <= 1.0
        assert record.tyre_temp >= 0

def test_pit_stop_logic():
    """Test pit stop functionality"""
    def pit_strategy(car_state: CarState) -> Decision:
        # Pit every 10 laps
        if car_state.lap > 0 and car_state.lap % 10 == 0:
            return Decision(
                pit_stop=True,
                compound_choice="soft" if car_state.compound != "soft" else "medium",
                drive_mode=DriveMode.NORMAL,
                fuel_mode="normal"
            )
        return Decision(pit_stop=False, drive_mode=DriveMode.NORMAL, fuel_mode="normal")

    config = RaceConfig()
    simulator = RaceSimulator(config, seed=111)
    lap_records = simulator.simulate_race(pit_strategy)

    # Check that pit stops occurred (look for compound changes or high lap times)
    pit_stops = 0
    for record in lap_records:
        if record.lap_time > 120:  # Likely a pit stop lap (very slow)
            pit_stops += 1

    # Should have several pit stops in a 78-lap race
    assert pit_stops >= 5

if __name__ == "__main__":
    pytest.main([__file__, "-v"])