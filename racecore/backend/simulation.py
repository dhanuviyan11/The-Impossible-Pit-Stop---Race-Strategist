import numpy as np
from typing import List, Tuple, Optional, Dict, Any
from models import (
    RaceConfig, CarState, LapRecord, Decision,
    WeatherCondition, DriveMode, SeededRNG, CompoundSpec
)
import time
from enum import Enum

class RaceSimulator:
    def __init__(self, config: RaceConfig, seed: int = None):
        self.config = config
        self.seed = seed if seed is not None else np.random.randint(0, 2**32 - 1)
        self.rng = SeededRNG(self.seed)
        self.lap_records: List[LapRecord] = []
        self.event_timeline: List[dict] = []  # For storing events like SC, weather changes, etc.
        self.weather_forecast: List[WeatherCondition] = []  # Noisy forecast for future weather
        self._generate_weather_forecast()  # Generate forecast for entire race

    def _get_compound_spec(self, compound_name: str) -> CompoundSpec:
        """Get compound specification by name"""
        for compound in self.config.compounds:
            if compound.name == compound_name:
                return compound
        # Default to medium if not found
        return self.config.compounds[1]

    def _calculate_lap_time(self, car_state: CarState, decision: Decision) -> float:
        """Calculate lap time based on car state and driver decisions"""
        compound_spec = self._get_compound_spec(car_state.compound)
        base_lap_time = self.config.base_lap_time

        # Base pace adjustments
        lap_time = base_lap_time

        # Fuel weight effect (more fuel = slower)
        fuel_effect = (car_state.fuel_remaining / self.config.fuel_capacity) * 0.02  # 2% max effect
        lap_time += base_lap_time * fuel_effect

        # Tyre wear effect (more wear = slower)
        wear_effect = car_state.tyre_wear * 0.03  # 3% max effect from wear
        lap_time += base_lap_time * wear_effect

        # Temperature effect on grip
        compound_spec = self._get_compound_spec(car_state.compound)
        temp_diff = abs(car_state.tyre_temp - compound_spec.optimal_temp)
        temp_penalty = min(temp_diff * 0.005, 0.05)  # Max 5% penalty
        lap_time += base_lap_time * temp_penalty

        # Weather effect
        weather_multipliers = {
            WeatherCondition.DRY: 1.0,
            WeatherCondition.DAMP: 1.03,  # 3% slower in damp
            WeatherCondition.WET: 1.15   # 15% slower in wet
        }
        lap_time *= weather_multipliers[car_state.weather]

        # Drive mode effect
        drive_mode_multipliers = {
            DriveMode.NORMAL: 1.0,
            DriveMode.PUSH: 0.98,   # 2% faster but more wear/fuel
            DriveMode.CONSERVE: 1.02  # 2% slower but less wear/fuel
        }
        lap_time *= drive_mode_multipliers[decision.drive_mode]

        # Safety car / VSC effect
        if car_state.safety_car:
            lap_time *= 1.4  # 40% slower under safety car
        elif car_state.vsc:
            lap_time *= 1.1  # 10% slower under VSC

        # Add random noise
        noise = self.rng.normal(0, base_lap_time * 0.01)  # 1% noise
        lap_time += noise

        # Ensure lap time is positive
        return max(lap_time, base_lap_time * 0.8)  # Never faster than 80% of base time

    def _update_fuel(self, car_state: CarState, decision: Decision) -> float:
        """Update fuel remaining based on consumption"""
        base_consumption = self.config.fuel_consumption_rate

        # Drive mode multipliers
        fuel_mode_multipliers = {
            "normal": 1.0,
            "push": 1.2,      # 20% more fuel used
            "conserve": 0.8   # 20% less fuel used
        }
        fuel_used = base_consumption * fuel_mode_multipliers[decision.fuel_mode]

        # Safety car reduces fuel consumption
        if car_state.safety_car or car_state.vsc:
            fuel_used *= 0.7

        new_fuel = max(0, car_state.fuel_remaining - fuel_used)
        return new_fuel

    def _update_tyre_wear(self, car_state: CarState, decision: Decision) -> float:
        """Update tyre wear based on usage"""
        compound_spec = self._get_compound_spec(car_state.compound)
        base_wear = compound_spec.wear_rate

        # Drive mode effect on wear
        drive_mode_wear_multipliers = {
            DriveMode.NORMAL: 1.0,
            DriveMode.PUSH: 1.3,      # 30% more wear
            DriveMode.CONSERVE: 0.7   # 30% less wear
        }
        wear_increment = base_wear * drive_mode_wear_multipliers[decision.drive_mode]

        # Weather effect (more wear in wet conditions)
        weather_wear_multipliers = {
            WeatherCondition.DRY: 1.0,
            WeatherCondition.DAMP: 1.2,
            WeatherCondition.WET: 1.5
        }
        wear_increment *= weather_wear_multipliers[car_state.weather]

        # Safety car reduces wear
        if car_state.safety_car or car_state.vsc:
            wear_increment *= 0.5

        new_wear = min(1.0, car_state.tyre_wear + wear_increment)  # Cap at 100%
        return new_wear

    def _update_tyre_temp(self, car_state: CarState, decision: Decision) -> float:
        """Update tyre temperature"""
        compound_spec = self._get_compound_spec(car_state.compound)
        optimal_temp = compound_spec.optimal_temp

        # Base temperature tends toward optimal
        temp_change = (optimal_temp - car_state.tyre_temp) * 0.1

        # Driving heats up tyres
        driving_heat = 5.0  # Base heating from driving

        # Drive mode affects heating
        drive_mode_heat_multipliers = {
            DriveMode.NORMAL: 1.0,
            DriveMode.PUSH: 1.5,      # 50% more heat
            DriveMode.CONSERVE: 0.6   # 40% less heat
        }
        driving_heat *= drive_mode_heat_multipliers[decision.drive_mode]

        # Weather affects cooling
        weather_cool_multipliers = {
            WeatherCondition.DRY: 1.0,
            WeatherCondition.DAMP: 1.2,   # More cooling
            WeatherCondition.WET: 1.5     # Much more cooling
        }
        driving_heat /= weather_cool_multipliers[car_state.weather]

        # Safety car/VSC reduces tyre temperature
        if car_state.safety_car or car_state.vsc:
            driving_heat *= 0.3

        new_temp = car_state.tyre_temp + temp_change + driving_heat
        return max(0, new_temp)  # Temperature can't be negative

    def _generate_weather_forecast(self):
        """Generate a noisy weather forecast for the entire race using the seed"""
        # Start with initial weather (dry)
        current_weather = WeatherCondition.DRY
        self.weather_forecast = [current_weather]  # Day 0 weather

        # Generate forecast for each lap using the Markov chain
        for _ in range(self.config.total_laps):
            # Get transition probabilities for current weather
            probs = self.config.weather_transition_prob[current_weather.value]
            weather_list = list(probs.keys())
            weights = list(probs.values())

            # Choose next weather state
            chosen_weather_str = self.rng.choice(weather_list, p=weights)
            current_weather = WeatherCondition(chosen_weather_str)
            self.weather_forecast.append(current_weather)

    def _get_weather_forecast(self, lap: int) -> WeatherCondition:
        """Get the forecasted weather for a specific lap"""
        if lap < len(self.weather_forecast):
            return self.weather_forecast[lap]
        return WeatherCondition.DRY  # Default fallback

    def _update_weather(self, current_weather: WeatherCondition, lap: int) -> WeatherCondition:
        """Update weather based on Markov chain (returns actual weather, which may differ from forecast due to noise)"""
        # Get transition probabilities for current weather
        probs = self.config.weather_transition_prob[current_weather.value]
        weather_list = list(probs.keys())
        weights = list(probs.values())

        # Choose next weather state
        chosen_weather_str = str(self.rng.choice(weather_list, p=weights))
        actual_weather = WeatherCondition(chosen_weather_str)

        # Add some noise to make actual weather sometimes differ from forecast
        # 10% chance of weather being different from forecast (representing forecast error)
        if self.rng.random() < 0.1 and lap < len(self.weather_forecast) - 1:
            # Choose a different weather state randomly
            weather_options = [WeatherCondition.DRY, WeatherCondition.DAMP, WeatherCondition.WET]
            # Remove current actual_weather from options
            weather_options = [w for w in weather_options if w != actual_weather]
            if weather_options:
                # Choose random index and get the weather condition
                random_index = self.rng.randint(0, len(weather_options))
                chosen_weather = weather_options[random_index]
                return chosen_weather

        return actual_weather

    def _check_safety_car_events(self, lap: int) -> Tuple[bool, bool]:
        """Check if safety car or VSC should be deployed this lap"""
        sc_deployed = self.rng.random() < self.config.sc_probability_per_lap
        vsc_deployed = self.rng.random() < self.config.vsc_probability_per_lap

        # Ensure VSC doesn't happen with SC (simplified)
        if sc_deployed:
            vsc_deployed = False

        return sc_deployed, vsc_deployed

    def _update_safety_car_state(self, car_state: CarState, sc_deployed: bool, vsc_deployed: bool, laps_in_sc: int, laps_in_vsc: int) -> Tuple[bool, bool, int, int]:
        """Update safety car/VSC state"""
        new_sc = car_state.safety_car
        new_vsc = car_state.vsc
        new_laps_in_sc = laps_in_sc
        new_laps_in_vsc = laps_in_vsc

        # Handle SC deployment
        if sc_deployed and not car_state.safety_car:
            new_sc = True
            new_laps_in_sc = 0
        elif car_state.safety_car:
            new_laps_in_sc += 1
            # End SC after random duration (avg 3 laps)
            if new_laps_in_sc >= self.config.sc_duration_laps and self.rng.random() < 0.3:
                new_sc = False

        # Handle VSC deployment
        if vsc_deployed and not car_state.vsc and not car_state.safety_car:
            new_vsc = True
            new_laps_in_vsc = 0
        elif car_state.vsc:
            new_laps_in_vsc += 1
            # End VSC after random duration (avg 2 laps)
            if new_laps_in_vsc >= self.config.vsc_duration_laps and self.rng.random() < 0.4:
                new_vsc = False

        return new_sc, new_vsc, new_laps_in_sc, new_laps_in_vsc

    def _check_slow_stop(self, lap: int) -> float:
        """Check for random slow stops (not related to SC/VSC)
        Returns a multiplicative factor for lap time (1.0 = normal, >1.0 = slower)
        """
        # 0.5% chance per lap of a slow stop (like debris, minor incident)
        if self.rng.random() < 0.005:
            # Slow down by 20-50% for 1-3 laps
            slow_factor = self.rng.uniform(1.2, 1.5)
            duration = self.rng.randint(1, 3)
            # Store that we're in a slow stop period
            if not hasattr(self, '_slow_stop_remaining'):
                self._slow_stop_remaining = 0
            if self._slow_stop_remaining <= 0:
                self._slow_stop_remaining = duration
                return slow_factor

        # If we're in a slow stop period, continue the effect
        if hasattr(self, '_slow_stop_remaining') and self._slow_stop_remaining > 0:
            self._slow_stop_remaining -= 1
            return self.rng.uniform(1.2, 1.5)  # Continue slowdown

        return 1.0  # Normal conditions

    def _check_puncture_hazard(self, tyre_wear: float) -> float:
        """Check for puncture hazard based on tyre wear
        Returns a multiplicative factor for lap time (1.0 = normal, >>1.0 = puncture)
        """
        # Base puncture probability increases with tyre wear
        # At 0% wear: 0.01% chance per lap
        # At 100% wear: 5% chance per lap
        base_puncture_prob = 0.0001 + (tyre_wear * 0.0499)

        if self.rng.random() < base_puncture_prob:
            # Puncture! Extreme slowdown
            return self.rng.uniform(3.0, 5.0)  # 200-400% slower

        return 1.0  # Normal conditions

    def simulate_race(self, strategy_callable) -> List[LapRecord]:
        """
        Simulate a full race using the provided strategy function

        Args:
            strategy_callable: Function that takes CarState and returns Decision

        Returns:
            List of LapRecord objects for each lap
        """
        # Initialize car state
        car_state = CarState(
            lap=0,
            fuel_remaining=self.config.fuel_capacity,
            tyre_wear=0.0,
            tyre_temp=self.config.compounds[1].optimal_temp,  # Start with medium compound optimal temp
            compound=self.config.compounds[1].name,  # Start with medium
            weather=WeatherCondition.DRY,
            drive_mode=DriveMode.NORMAL,
            safety_car=False,
            vsc=False,
            lap_time=0.0,
            is_pitting=False
        )

        self.lap_records = []
        laps_in_sc = 0
        laps_in_vsc = 0

        # Simulate each lap
        for lap in range(1, self.config.total_laps + 1):
            # Check for safety car/VSC events
            sc_deployed, vsc_deployed = self._check_safety_car_events(lap)
            car_state.safety_car, car_state.vsc, laps_in_sc, laps_in_vsc = self._update_safety_car_state(
                car_state, sc_deployed, vsc_deployed, laps_in_sc, laps_in_vsc
            )

            # Check for slow stops (random slowdowns not related to SC/VSC)
            slow_stop_factor = self._check_slow_stop(lap)

            # Check for puncture hazards (more likely with high tyre wear)
            puncture_factor = self._check_puncture_hazard(car_state.tyre_wear)

            # Get driver decision
            decision = strategy_callable(car_state)

            # Handle pit stop
            if decision.pit_stop and decision.compound_choice:
                car_state.is_pitting = True
                # Apply pit stop time penalty (will be added to lap time)
                pit_time = self.config.pit_loss_time
                car_state.tyre_wear = 0.0  # Fresh tyres
                car_state.compound = decision.compound_choice
                # Reset tyre temp to optimal for new compound
                new_compound_spec = self._get_compound_spec(decision.compound_choice)
                car_state.tyre_temp = new_compound_spec.optimal_temp
            else:
                car_state.is_pitting = False

            # Calculate lap time
            lap_time = self._calculate_lap_time(car_state, decision)

            # Apply slow stop and puncture effects
            lap_time *= slow_stop_factor * puncture_factor

            # Add pit stop time if pitting
            if decision.pit_stop:
                lap_time += self.config.pit_loss_time

            # Update car state
            car_state.lap = lap
            car_state.fuel_remaining = self._update_fuel(car_state, decision)
            car_state.tyre_wear = self._update_tyre_wear(car_state, decision)
            car_state.tyre_temp = self._update_tyre_temp(car_state, decision)
            car_state.lap_time = lap_time

            # Update weather (Markov chain) - now passing lap for forecast comparison
            car_state.weather = self._update_weather(car_state.weather, lap)

            # Create lap record
            lap_record = LapRecord(
                lap=lap,
                lap_time=lap_time,
                fuel_remaining=car_state.fuel_remaining,
                tyre_wear=car_state.tyre_wear,
                tyre_temp=car_state.tyre_temp,
                compound=car_state.compound,
                weather=car_state.weather,
                drive_mode=decision.drive_mode,
                safety_car=car_state.safety_car,
                vsc=car_state.vsc,
                timestamp=float(lap)  # Simple timestamp based on lap number
            )

            self.lap_records.append(lap_record)
            car_state.lap_time = lap_time  # For next lap reference

        return self.lap_records

def default_strategy(car_state: CarState) -> Decision:
    """Default strategy: no pit stops, normal drive mode"""
    return Decision(
        pit_stop=False,
        drive_mode=DriveMode.NORMAL,
        fuel_mode="normal"
    )

# Example usage and testing functions
def run_example_race(seed: int = 42) -> List[LapRecord]:
    """Run an example race with default strategy"""
    config = RaceConfig()
    simulator = RaceSimulator(config, seed)
    return simulator.simulate_race(default_strategy)

def baseline_strategy(car_state: CarState) -> Decision:
    """
    Baseline strategy: fixed pit laps/compounds, reacting only to heavy rain
    - Pit on laps 15, 30, 45, 60 (fixed intervals)
    - Use medium compound unless it's raining heavily (wet weather)
    - In wet weather, switch to intermediate/wet compounds
    """
    # Fixed pit strategy: every 15 laps
    if car_state.lap > 0 and car_state.lap % 15 == 0:
        # Choose compound based on weather
        if car_state.weather == WeatherCondition.WET:
            # In heavy rain, use wet or intermediate compound
            compound_choice = "wet" if car_state.tyre_wear > 0.5 else "intermediate"
        else:
            # In dry/damp conditions, use medium compound
            compound_choice = "medium"

        return Decision(
            pit_stop=True,
            compound_choice=compound_choice,
            drive_mode=DriveMode.NORMAL,
            fuel_mode="normal"
        )

    # No pit stop
    return Decision(
        pit_stop=False,
        drive_mode=DriveMode.NORMAL,
        fuel_mode="normal"
    )


# Scenario presets
def get_race_config_always_dry() -> RaceConfig:
    """Scenario: Always dry weather"""
    config = RaceConfig()
    # Override weather transitions to always stay dry
    config.weather_transition_prob = {
        "dry": {"dry": 1.0, "damp": 0.0, "wet": 0.0},
        "damp": {"dry": 0.0, "damp": 1.0, "wet": 0.0},  # If somehow damp, stay damp
        "wet": {"dry": 0.0, "damp": 0.0, "wet": 1.0}    # If somehow wet, stay wet
    }
    return config


def get_race_config_early_rain() -> RaceConfig:
    """Scenario: Early rain (laps 10-20)"""
    config = RaceConfig()
    # Note: For simplicity in this implementation, we'll use the standard weather model
    # In a more complex version, we'd modify the RNG or transition probabilities based on lap
    return config


def get_race_config_late_rain() -> RaceConfig:
    """Scenario: Late rain (laps 60-70)"""
    config = RaceConfig()
    # Note: For simplicity in this implementation, we'll use the standard weather model
    return config


def get_race_config_early_sc() -> RaceConfig:
    """Scenario: Early safety car (lap 5)"""
    config = RaceConfig()
    # Increase SC probability early in race
    config.sc_probability_per_lap = 0.1  # Much higher chance of SC
    return config


def get_race_config_high_deg() -> RaceConfig:
    """Scenario: High degradation track"""
    config = RaceConfig()
    # Increase wear rates for all compounds
    for compound in config.compounds:
        compound.wear_rate *= 2.0  # Double the wear rate
    return config


def get_race_config_random_mix() -> RaceConfig:
    """Scenario: Random mix of conditions"""
    config = RaceConfig()
    # Use standard configuration - the randomness comes from the seed
    return config


# Dictionary mapping scenario names to config functions
SCENARIO_PRESETS = {
    "always_dry": get_race_config_always_dry,
    "early_rain": get_race_config_early_rain,
    "late_rain": get_race_config_late_rain,
    "early_sc": get_race_config_early_sc,
    "high_deg": get_race_config_high_deg,
    "random_mix": get_race_config_random_mix
}


def run_example_race(seed: int = 42) -> List[LapRecord]:
    """Run an example race with default strategy"""
    config = RaceConfig()
    simulator = RaceSimulator(config, seed)
    return simulator.simulate_race(baseline_strategy)


def run_scenario_race(scenario_name: str, seed: int = 42) -> List[LapRecord]:
    """Run a race with a specific scenario preset"""
    if scenario_name not in SCENARIO_PRESETS:
        raise ValueError(f"Unknown scenario: {scenario_name}. Available: {list(SCENARIO_PRESETS.keys())}")

    config_func = SCENARIO_PRESETS[scenario_name]
    config = config_func()
    simulator = RaceSimulator(config, seed)
    return simulator.simulate_race(baseline_strategy)


class ReplanTrigger(Enum):
    """Triggers that cause a strategy to re-plan"""
    WEATHER_CHANGE = "weather_change"
    SAFETY_CAR = "safety_car"
    WEAR_THRESHOLD = "wear_threshold"
    PUNCTURE = "puncture"
    MANUAL_REQUEST = "manual_request"


class AdaptiveStrategy:
    """Base class for adaptive strategies with re-plan capabilities"""

    def __init__(self, config: RaceConfig, replan_triggers: List[ReplanTrigger] = None, time_budget_ms: int = 200):
        self.config = config
        self.replan_triggers = replan_triggers or [
            ReplanTrigger.WEATHER_CHANGE,
            ReplanTrigger.SAFETY_CAR,
            ReplanTrigger.WEAR_THRESHOLD,
            ReplanTrigger.PUNCTURE
        ]
        self.time_budget_ms = time_budget_ms
        self.last_decision_lap = -1
        self.last_weather = None
        self.last_safety_car_state = (False, False)  # (safety_car, vsc)
        self.last_tyre_wear = 0.0
        self.last_decision_reason = ""
        self.last_candidates = []

    def should_replan(self, car_state: CarState, last_decision_lap: int) -> bool:
        """Determine if we should re-plan based on triggers"""
        if last_decision_lap < 0:
            return True

        laps_since_last_decision = car_state.lap - last_decision_lap

        # Always replan if we pitted last time (fresh tyres)
        if laps_since_last_decision == 0:
            return True

        # Check weather change trigger
        if ReplanTrigger.WEATHER_CHANGE in self.replan_triggers:
            if self.last_weather is not None and self.last_weather != car_state.weather:
                return True

        # Check safety car/VSC trigger
        if ReplanTrigger.SAFETY_CAR in self.replan_triggers:
            sc_active = car_state.safety_car or car_state.vsc
            last_sc_active = self.last_safety_car_state[0] or self.last_safety_car_state[1]
            if sc_active != last_sc_active:
                return True

        # Check wear threshold trigger
        if ReplanTrigger.WEAR_THRESHOLD in self.replan_triggers:
            if self.last_tyre_wear > 0 and abs(car_state.tyre_wear - self.last_tyre_wear) > 0.15:  # 15% wear change
                return True

        # Note: Puncture trigger would be handled separately as it causes immediate re-plan

        # Time-based replan (every 5 laps max)
        if laps_since_last_decision >= 5:
            return True

        return False

    def get_weather_prediction_loss(self, car_state: CarState, laps_ahead: int, compound: str) -> float:
        """Predict expected lap time loss due to weather for given compound"""
        # Simple heuristic: softer compounds suffer more in wet weather
        # Use current weather as a simplified forecast (in practice would use actual forecast)
        compound_spec = None
        for c in self.config.compounds:
            if c.name == compound:
                compound_spec = c
                break

        if compound_spec is None:
            compound_spec = self.config.compounds[1]  # Default to medium

        # Simple prediction based on current weather only
        # In a full implementation, this would use a proper weather forecast
        weather_penalty = 0.0
        if car_state.weather == WeatherCondition.WET:
            if compound in ["intermediate", "wet"]:
                weather_penalty = 0.0  # No penalty for wet-appropriate tires
            else:
                weather_penalty = 0.15  # 15% slower for slicks in wet
        elif car_state.weather == WeatherCondition.DAMP:
            if compound in ["intermediate", "wet"]:
                weather_penalty = 0.05  # Small penalty
            else:
                weather_penalty = 0.03  # 3% slower for slicks in damp
        # Dry conditions: no penalty

        return weather_penalty  # Simple penalty (not averaged over laps ahead for simplicity)

    def calculate_degradation_loss(self, current_wear: float, laps_ahead: int, compound: str) -> float:
        """Predict expected lap time loss due to tyre degradation"""
        compound_spec = None
        for c in self.config.compounds:
            if c.name == compound:
                compound_spec = c
                break

        if compound_spec is None:
            compound_spec = self.config.compounds[1]  # Default to medium

        # Linear wear projection (simplified)
        projected_wear = min(1.0, current_wear + (compound_spec.wear_rate * laps_ahead))
        wear_penalty = projected_wear * 0.03  # 3% max effect from wear

        return wear_penalty

    def estimate_lap_time(self, car_state: CarState, decision: Decision, laps_ahead: int = 0) -> float:
        """Estimate lap time for a given decision, looking ahead laps_ahead laps"""
        # This is a simplified estimation - in practice would use the full physics model
        base_time = self.config.base_lap_time

        # Compound effect
        compound_spec = self._get_compound_spec(decision.compound_choice or car_state.compound)

        # Fuel effect (lighter is faster)
        fuel_effect = (car_state.fuel_remaining / self.config.fuel_capacity) * 0.02

        # Wear effect
        wear_effect = car_state.tyre_wear * 0.03

        # Weather effect
        weather_multipliers = {
            WeatherCondition.DRY: 1.0,
            WeatherCondition.DAMP: 1.03,
            WeatherCondition.WET: 1.15
        }
        weather_effect = weather_multipliers[car_state.weather]

        # Combine effects
        estimated_time = base_time * (1 + fuel_effect + wear_effect) * weather_effect

        # Apply future predictions (negative = time loss)
        if laps_ahead > 0:
            degradation_loss = self.calculate_degradation_loss(car_state.tyre_wear, laps_ahead,
                                                             decision.compound_choice or car_state.compound)
            weather_loss = self.get_weather_prediction_loss(car_state, 0,  # laps_ahead not used in simplified version
                                                          decision.compound_choice or car_state.compound)
            estimated_time *= (1 + degradation_loss + weather_loss)

        return estimated_time

    def _get_compound_spec(self, compound_name: str) -> CompoundSpec:
        """Get compound specification by name"""
        for compound in self.config.compounds:
            if compound.name == compound_name:
                return compound
        # Default to medium if not found
        return self.config.compounds[1]


class ThresholdStrategy(AdaptiveStrategy):
    """Threshold strategy: pit when predicted degradation loss exceeds pit cost"""

    def __init__(self, config: RaceConfig, look_ahead_laps: int = 3,
                 weather_threshold: float = 0.1, time_budget_ms: int = 50):
        super().__init__(config, time_budget_ms=time_budget_ms)
        self.look_ahead_laps = look_ahead_laps
        self.weather_threshold = weather_threshold

    def __call__(self, car_state: CarState) -> Decision:
        start_time = time.time()

        # Check if we should re-plan
        if not self.should_replan(car_state, self.last_decision_lap):
            # Return a conservative decision (no pit) if we shouldn't re-plan yet
            # In a full implementation, we'd cache and return the last decision
            return Decision(
                pit_stop=False,
                drive_mode=DriveMode.NORMAL,
                fuel_mode="normal"
            )

        # Calculate pit stop cost (time lost in pits)
        pit_cost = self.config.pit_loss_time / self.config.base_lap_time  # As fraction of lap time

        # Calculate expected loss if we stay out
        degradation_loss = self.calculate_degradation_loss(
            car_state.tyre_wear, self.look_ahead_laps, car_state.compound
        )
        weather_loss = self.get_weather_prediction_loss(
            car_state, self.look_ahead_laps, car_state.compound
        )
        expected_loss_if_stay_out = degradation_loss + weather_loss

        # Decision logic
        pit_stop = False
        compound_choice = car_state.compound
        reason = ""

        # Pit if expected loss exceeds pit cost
        if expected_loss_if_stay_out > pit_cost:
            pit_stop = True
            # Choose best compound for current and forecasted weather
            compound_choice = self._select_best_compound(car_state)
            reason = f"Pit: expected loss ({expected_loss_if_stay_out:.3f}) > pit cost ({pit_cost:.3f})"
        else:
            # Check weather thresholds for immediate pit
            if car_state.weather == WeatherCondition.WET and car_state.compound not in ["intermediate", "wet"]:
                pit_stop = True
                compound_choice = "wet" if car_state.tyre_wear > 0.3 else "intermediate"
                reason = "Pit for wet weather"
            elif (self.last_weather == WeatherCondition.WET and
                  car_state.weather != WeatherCondition.WET and
                  car_state.compound in ["wet", "intermediate"]):
                # Drying track - switch to slicks
                pit_stop = True
                compound_choice = "medium"
                reason = "Pit for drying track"
            else:
                reason = f"Stay out: expected loss ({expected_loss_if_stay_out:.3f}) <= pit cost ({pit_cost:.3f})"

        # Update tracking variables
        self.last_decision_lap = car_state.lap
        self.last_weather = car_state.weather
        self.last_safety_car_state = (car_state.safety_car, car_state.vsc)
        self.last_tyre_wear = car_state.tyre_wear
        self.last_decision_reason = reason

        # Enforce time budget (simplified)
        elapsed_ms = (time.time() - start_time) * 1000
        if elapsed_ms > self.time_budget_ms:
            # In a real implementation, we might simplify calculations
            pass

        return Decision(
            pit_stop=pit_stop,
            compound_choice=compound_choice if pit_stop else None,
            drive_mode=DriveMode.NORMAL,
            fuel_mode="normal"
        )

    def _select_best_compound(self, car_state: CarState) -> str:
        """Select the best compound based on current and forecasted conditions"""
        # Simple heuristic based on weather
        if car_state.weather == WeatherCondition.WET:
            return "wet" if car_state.tyre_wear > 0.5 else "intermediate"
        elif car_state.weather == WeatherCondition.DAMP:
            return "intermediate" if car_state.tyre_wear > 0.3 else "medium"
        else:
            # Dry conditions - choose based on wear
            if car_state.tyre_wear > 0.7:
                return "hard"
            elif car_state.tyre_wear > 0.3:
                return "medium"
            else:
                return "soft"


class MonteCarloStrategy(AdaptiveStrategy):
    """Monte Carlo planner with vectorised NumPy rollouts"""

    def __init__(self, config: RaceConfig, num_rollouts: int = 1000,
                 look_ahead_laps: int = 5, lambda_risk_aversion: float = 0.5,
                 time_budget_ms: int = 200):
        super().__init__(config, time_budget_ms=time_budget_ms)
        self.num_rollouts = num_rollouts
        self.look_ahead_laps = look_ahead_laps
        self.lambda_risk_aversion = lambda_risk_aversion  # Weight for tail risk (CVaR)

    def __call__(self, car_state: CarState) -> Decision:
        start_time = time.time()

        # Check if we should re-plan
        if not self.should_replan(car_state, self.last_decision_lap):
            # Would return cached decision in full implementation
            pass

        # Define candidate actions
        candidates = self._generate_candidates(car_state)

        # Evaluate each candidate using vectorised rollouts
        best_candidate = None
        best_score = float('inf')

        for candidate in candidates:
            score, expected_time, tail_risk, reason = self._evaluate_candidate(car_state, candidate)

            if score < best_score:
                best_score = score
                best_candidate = candidate

        # Extract decision from best candidate
        decision = self._candidate_to_decision(best_candidate, car_state)

        # Store info for debugging/telemetry
        self.last_candidates = candidates
        self.last_decision_reason = getattr(best_candidate, 'reason', 'No reason') if best_candidate else "Error"

        # Update tracking variables
        self.last_decision_lap = car_state.lap
        self.last_weather = car_state.weather
        self.last_safety_car_state = (car_state.safety_car, car_state.vsc)
        self.last_tyre_wear = car_state.tyre_wear

        # Enforce time budget
        elapsed_ms = (time.time() - start_time) * 1000
        if elapsed_ms > self.time_budget_ms:
            # Reduce rollouts if over budget
            self.num_rollouts = max(100, int(self.num_rollouts * (self.time_budget_ms / elapsed_ms)))

        return decision

    def _generate_candidates(self, car_state: CarState) -> List[Dict[str, Any]]:
        """Generate candidate actions to evaluate"""
        candidates = []

        # Candidate 1: Stay out
        candidates.append({
            'action': 'stay_out',
            'pit_stop': False,
            'compound_choice': None,
            'drive_mode': DriveMode.NORMAL,
            'fuel_mode': 'normal',
            'reason': 'Stay out on current tyres'
        })

        # Candidate 2-5: Pit now for each compound
        for compound in [c.name for c in self.config.compounds]:
            if compound != car_state.compound:  # Don't suggest pitting for same compound
                candidates.append({
                    'action': 'pit_now',
                    'pit_stop': True,
                    'compound_choice': compound,
                    'drive_mode': DriveMode.NORMAL,
                    'fuel_mode': 'normal',
                    'reason': f'Pit now for {compound} compound'
                })

        # Candidate 6-10: Pit in 1-5 laps (if we have enough fuel and tyres)
        for laps_ahead in range(1, 6):
            if car_state.lap + laps_ahead < self.config.total_laps:
                # Only consider if we have enough fuel to last that long
                fuel_needed = self.config.fuel_consumption_rate * laps_ahead
                if car_state.fuel_remaining > fuel_needed * 1.2:  # 20% buffer
                    candidates.append({
                        'action': 'pit_later',
                        'pit_stop': False,  # Will pit later
                        'pit_lap': car_state.lap + laps_ahead,
                        'compound_choice': self._select_best_compound_for_future(car_state, laps_ahead),
                        'drive_mode': DriveMode.NORMAL,
                        'fuel_mode': 'normal',
                        'reason': f'Plan to pit in {laps_ahead} laps'
                    })

        return candidates

    def _select_best_compound_for_future(self, car_state: CarState, laps_ahead: int) -> str:
        """Select best compound for a future lap based on forecast"""
        # Simple approach: use current weather, could be enhanced with forecast
        if car_state.weather == WeatherCondition.WET:
            return "wet" if car_state.tyre_wear > 0.5 else "intermediate"
        elif car_state.weather == WeatherCondition.DAMP:
            return "intermediate"
        else:
            # Dry - moderate compound
            return "medium"

    def _evaluate_candidate(self, car_state: CarState, candidate: Dict[str, Any]) -> Tuple[float, float, float, str]:
        """Evaluate a candidate using vectorised rollouts"""
        # Run vectorised Monte Carlo simulation
        lap_times = self._vectorised_rollout(car_state, candidate)

        # Calculate metrics
        expected_time = np.mean(lap_times)

        # Calculate tail risk (Conditional Value at Risk at 5%)
        sorted_times = np.sort(lap_times)
        tail_index = max(1, int(len(sorted_times) * 0.05))
        tail_risk = np.mean(sorted_times[:tail_index]) if tail_index > 0 else expected_time

        # Score = expected time + lambda * tail_risk
        score = expected_time + self.lambda_risk_aversion * tail_risk

        reason = f"ET: {expected_time:.2f}s, TR: {tail_risk:.2f}s, Score: {score:.2f}s"

        return score, expected_time, tail_risk, reason

    def _vectorised_rollout(self, car_state: CarState, candidate: Dict[str, Any]) -> np.ndarray:
        """Run vectorised Monte Carlo rollout for a candidate"""
        lap_times = np.zeros(self.num_rollouts)

        # Initialize arrays for vectorised computation
        fuel_remaining = np.full(self.num_rollouts, car_state.fuel_remaining)
        tyre_wear = np.full(self.num_rollouts, car_state.tyre_wear)
        tyre_temp = np.full(self.num_rollouts, car_state.tyre_temp)
        compound = np.full(self.num_rollouts,
                          car_state.compound if candidate['compound_choice'] is None
                          else candidate['compound_choice'], dtype='<U20')

        # Simulate look_ahead_laps laps
        for lap_offset in range(self.look_ahead_laps):
            current_lap = car_state.lap + lap_offset

            # Use current weather as a simplified forecast
            # In a full implementation, this would use a proper weather forecast
            weather = car_state.weather

            # Determine if we pit this lap for this candidate
            pit_this_lap = np.zeros(self.num_rollouts, dtype=bool)
            compound_choice_this_lap = compound.copy()

            if candidate['action'] == 'pit_now' and lap_offset == 0:
                pit_this_lap[:] = True
                compound_choice_this_lap = np.full(self.num_rollouts, candidate['compound_choice'], dtype='<U20')
            elif candidate['action'] == 'pit_later' and lap_offset == candidate.get('pit_lap', 999) - car_state.lap:
                pit_this_lap[:] = True
                compound_choice_this_lap = np.full(self.num_rollouts, candidate['compound_choice'], dtype='<U20')
            elif candidate['action'] == 'stay_out':
                pit_this_lap[:] = False

            # Calculate lap times for all rollouts vectorised
            lap_times += self._calculate_vectorised_lap_time(
                fuel_remaining, tyre_wear, tyre_temp, compound_choice_this_lap,
                weather, candidate['drive_mode'], candidate['fuel_mode'], pit_this_lap,
                car_state.safety_car, car_state.vsc
            )

            # Update state for next lap (vectorised)
            if np.any(pit_this_lap):
                # Pit stop: reset wear, change compound
                tyre_wear = np.where(pit_this_lap, 0.0, tyre_wear)
                # Get optimal temp for new compound
                for i in range(self.num_rollouts):
                    if pit_this_lap[i]:
                        compound_spec = self._get_compound_spec(compound_choice_this_lap[i])
                        tyre_temp[i] = compound_spec.optimal_temp
            else:
                # Normal lap: update wear, fuel, temperature
                # Wear update
                wear_rates = np.array([self._get_compound_spec(c).wear_rate for c in compound_choice_this_lap])
                drive_mode_multipliers = np.where(candidate['drive_mode'] == DriveMode.PUSH, 1.3,
                                                np.where(candidate['drive_mode'] == DriveMode.CONSERVE, 0.7, 1.0))
                weather_wear_multipliers = np.where(weather == WeatherCondition.WET, 1.5,
                                                  np.where(weather == WeatherCondition.DAMP, 1.2, 1.0))
                sc_vsc_factor = np.where((car_state.safety_car == True) | (car_state.vsc == True), 0.5, 1.0)

                wear_increment = wear_rates * drive_mode_multipliers * weather_wear_multipliers * sc_vsc_factor
                tyre_wear = np.minimum(1.0, tyre_wear + wear_increment)

                # Fuel update
                base_consumption = self.config.fuel_consumption_rate
                fuel_mode_multipliers = np.where(candidate['fuel_mode'] == 'push', 1.2,
                                               np.where(candidate['fuel_mode'] == 'conserve', 0.8, 1.0))
                sc_vsc_fuel_factor = np.where((car_state.safety_car == True) | (car_state.vsc == True), 0.7, 1.0)

                fuel_used = base_consumption * fuel_mode_multipliers * sc_vsc_fuel_factor
                fuel_remaining = np.maximum(0, fuel_remaining - fuel_used)

                # Temperature update (simplified)
                optimal_temps = np.array([self._get_compound_spec(c).optimal_temp for c in compound_choice_this_lap])
                temp_change = (optimal_temps - tyre_temp) * 0.1
                driving_heat = np.where(candidate['drive_mode'] == DriveMode.PUSH, 7.5,
                                      np.where(candidate['drive_mode'] == DriveMode.CONSERVE, 3.0, 5.0))
                weather_cool = np.where(weather == WeatherCondition.WET, 1.5,
                                      np.where(weather == WeatherCondition.DAMP, 1.2, 1.0))
                sc_vsc_temp_factor = np.where((car_state.safety_car == True) | (car_state.vsc == True), 0.3, 1.0)

                tyre_temp = tyre_temp + temp_change + (driving_heat / weather_cool) * sc_vsc_temp_factor
                tyre_temp = np.maximum(0, tyre_temp)  # No negative temperatures

                # Update compound if we pitted
                compound = np.where(pit_this_lap, compound_choice_this_lap, compound)

        return lap_times

    def _calculate_vectorised_lap_time(self, fuel_remaining: np.ndarray, tyre_wear: np.ndarray,
                                     tyre_temp: np.ndarray, compound: np.ndarray,
                                     weather: WeatherCondition, drive_mode: DriveMode,
                                     fuel_mode: str, is_pitting: np.ndarray,
                                     safety_car: bool, vsc: bool) -> np.ndarray:
        """Calculate lap time for multiple rollouts vectorised"""
        # Base lap time
        lap_times = np.full(len(fuel_remaining), self.config.base_lap_time, dtype=np.float64)

        # Fuel weight effect (more fuel = slower)
        fuel_effect = (fuel_remaining / self.config.fuel_capacity) * 0.02
        lap_times += lap_times * fuel_effect

        # Tyre wear effect
        wear_effect = tyre_wear * 0.03
        lap_times += lap_times * wear_effect

        # Temperature effect (get optimal temp for each compound)
        temp_penalty = np.zeros(len(fuel_remaining))
        for i, comp in enumerate(compound):
            compound_spec = self._get_compound_spec(comp)
            temp_diff = abs(tyre_temp[i] - compound_spec.optimal_temp)
            temp_penalty[i] = min(temp_diff * 0.005, 0.05)  # Max 5% penalty
        lap_times += lap_times * temp_penalty

        # Weather effect
        weather_multipliers = {
            WeatherCondition.DRY: 1.0,
            WeatherCondition.DAMP: 1.03,
            WeatherCondition.WET: 1.15
        }
        lap_times *= weather_multipliers[weather]

        # Drive mode effect
        drive_mode_multipliers = {
            DriveMode.NORMAL: 1.0,
            DriveMode.PUSH: 0.98,
            DriveMode.CONSERVE: 1.02
        }
        lap_times *= drive_mode_multipliers[drive_mode]

        # Safety car / VSC effect
        sc_factor = np.where(is_pitting, 1.4,
                           np.where(safety_car, 1.4,
                                  np.where(vsc, 1.1, 1.0)))
        lap_times *= sc_factor

        # Add random noise
        noise = np.random.normal(0, self.config.base_lap_time * 0.01, len(lap_times))
        lap_times += noise

        # Ensure lap time is positive and reasonable
        lap_times = np.maximum(lap_times, self.config.base_lap_time * 0.8)
        lap_times = np.minimum(lap_times, self.config.base_lap_time * 3.0)  # Cap at 3x base time

        # Add pit stop time if pitting
        pit_time = np.where(is_pitting, self.config.pit_loss_time, 0.0)
        lap_times += pit_time

        return lap_times

    def _candidate_to_decision(self, candidate: Dict[str, Any], car_state: CarState) -> Decision:
        """Convert a candidate to a Decision object"""
        if candidate is None:
            # Fallback to safe decision
            return Decision(
                pit_stop=False,
                drive_mode=DriveMode.NORMAL,
                fuel_mode="normal"
            )

        return Decision(
            pit_stop=candidate.get('pit_stop', False),
            compound_choice=candidate.get('compound_choice'),
            drive_mode=candidate.get('drive_mode', DriveMode.NORMAL),
            fuel_mode=candidate.get('fuel_mode', 'normal')
        )




if __name__ == "__main__":
    # Quick test
    records = run_example_race(42)
    print(f"Simulated {len(records)} laps")
    if records:
        print(f"First lap time: {records[0].lap_time:.2f}s")
        print(f"Last lap time: {records[-1].lap_time:.2f}s")
        print(f"Total race time: {sum(r.lap_time for r in records):.2f}s")