import numpy as np
from pydantic import BaseModel, Field
from typing import Literal, Optional, List
from enum import Enum

class WeatherCondition(str, Enum):
    DRY = "dry"
    DAMP = "damp"
    WET = "wet"

class DriveMode(str, Enum):
    NORMAL = "normal"
    PUSH = "push"
    CONSERVE = "conserve"

class CompoundSpec(BaseModel):
    name: str
    base_grip: float  # Base grip coefficient
    wear_rate: float  # How fast the tire wears per lap
    heat_sensitivity: float  # How much grip changes with temperature
    optimal_temp: float  # Optimal operating temperature in Celsius
    cold_grip_penalty: float  # Grip loss when too cold
    hot_grip_penalty: float  # Grip loss when too hot

class RaceConfig(BaseModel):
    # Track characteristics
    track_length: float = Field(default=5.0, description="Track length in km")
    base_lap_time: float = Field(default=90.0, description="Base lap time in seconds")
    total_laps: int = Field(default=78, description="Total number of laps")

    # Car specifications
    fuel_capacity: float = Field(default=100.0, description="Fuel capacity in kg")
    fuel_consumption_rate: float = Field(default=2.0, description="Fuel consumption per lap in kg")

    # Environmental factors
    base_temp: float = Field(default=25.0, description="Base ambient temperature in Celsius")
    temp_variation: float = Field(default=5.0, description="Temperature variation amplitude")

    # Weather settings
    weather_transition_prob: dict = Field(
        default={
            "dry": {"dry": 0.8, "damp": 0.15, "wet": 0.05},
            "damp": {"dry": 0.2, "damp": 0.6, "wet": 0.2},
            "wet": {"dry": 0.1, "damp": 0.3, "wet": 0.6}
        },
        description="Markov chain transition probabilities for weather"
    )

    # Safety car settings
    sc_probability_per_lap: float = Field(default=0.02, description="Probability of safety car deployment per lap")
    vsc_probability_per_lap: float = Field(default=0.01, description="Probability of VSC deployment per lap")
    sc_duration_laps: int = Field(default=3, description="Average safety car duration in laps")
    vsc_duration_laps: int = Field(default=2, description="Average VSC duration in laps")

    # Pit stop settings
    pit_loss_time: float = Field(default=20.0, description="Time lost in pit stop in seconds")
    min_pit_stop_time: float = Field(default=2.0, description="Minimum pit stop time in seconds")

    # Compound options
    compounds: List[CompoundSpec] = Field(default_factory=lambda: [
        CompoundSpec(
            name="soft",
            base_grip=1.2,
            wear_rate=0.05,
            heat_sensitivity=0.01,
            optimal_temp=95.0,
            cold_grip_penalty=0.15,
            hot_grip_penalty=0.1
        ),
        CompoundSpec(
            name="medium",
            base_grip=1.1,
            wear_rate=0.03,
            heat_sensitivity=0.008,
            optimal_temp=90.0,
            cold_grip_penalty=0.1,
            hot_grip_penalty=0.08
        ),
        CompoundSpec(
            name="hard",
            base_grip=1.0,
            wear_rate=0.02,
            heat_sensitivity=0.005,
            optimal_temp=85.0,
            cold_grip_penalty=0.08,
            hot_grip_penalty=0.06
        ),
        CompoundSpec(
            name="intermediate",
            base_grip=0.9,
            wear_rate=0.04,
            heat_sensitivity=0.012,
            optimal_temp=30.0,
            cold_grip_penalty=0.2,
            hot_grip_penalty=0.15
        ),
        CompoundSpec(
            name="wet",
            base_grip=0.8,
            wear_rate=0.06,
            heat_sensitivity=0.015,
            optimal_temp=20.0,
            cold_grip_penalty=0.25,
            hot_grip_penalty=0.2
        )
    ])

class CarState(BaseModel):
    lap: int = Field(default=0, description="Current lap number")
    position: float = Field(default=0.0, description="Position on track (0-1)")
    speed: float = Field(default=0.0, description="Current speed in km/h")
    fuel_remaining: float = Field(default=100.0, description="Fuel remaining in kg")
    tyre_wear: float = Field(default=0.0, description="Tyre wear percentage (0-1)")
    tyre_temp: float = Field(default=90.0, description="Tyre temperature in Celsius")
    compound: str = Field(default="medium", description="Current tyre compound")
    weather: WeatherCondition = Field(default=WeatherCondition.DRY, description="Current weather")
    drive_mode: DriveMode = Field(default=DriveMode.NORMAL, description="Current drive mode")
    safety_car: bool = Field(default=False, description="Whether safety car is deployed")
    vsc: bool = Field(default=False, description="Whether VSC is deployed")
    lap_time: float = Field(default=0.0, description="Last lap time in seconds")
    is_pitting: bool = Field(default=False, description="Whether currently in pit stop")

class LapRecord(BaseModel):
    lap: int
    lap_time: float
    fuel_remaining: float
    tyre_wear: float
    tyre_temp: float
    compound: str
    weather: WeatherCondition
    drive_mode: DriveMode
    safety_car: bool
    vsc: bool
    timestamp: float  # Unix timestamp

class Decision(BaseModel):
    pit_stop: bool = Field(default=False, description="Whether to pit this lap")
    compound_choice: Optional[str] = Field(None, description="Tyre compound to change to if pitting")
    drive_mode: DriveMode = Field(default=DriveMode.NORMAL, description="Drive mode for this lap")
    fuel_mode: Literal["normal", "push", "conserve"] = Field(default="normal", description="Fuel usage mode")

# Seeded RNG for reproducible simulations
class SeededRNG:
    def __init__(self, seed: int):
        self.seed = seed
        self.rng = np.random.RandomState(seed)

    def random(self) -> float:
        return self.rng.random()

    def randint(self, low: int, high: int) -> int:
        return self.rng.randint(low, high)

    def choice(self, items: list, p=None):
        return self.rng.choice(items, p=p)

    def normal(self, loc: float = 0.0, scale: float = 1.0) -> float:
        return self.rng.normal(loc, scale)

    def uniform(self, low: float, high: float) -> float:
        return self.rng.uniform(low, high)