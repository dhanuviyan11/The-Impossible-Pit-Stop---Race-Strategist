import random
import numpy as np

class RaceEnvironment:
    def __init__(self, total_laps=50, base_lap_time=90.0):
        self.total_laps = total_laps
        self.base_lap_time = base_lap_time  # in seconds
        
        # Pit stop time penalty (seconds)
        self.pit_stop_loss = 22.0
        
        # Tyre specifications: (wear_rate_per_lap, grip_performance_multiplier)
        self.tyre_compounds = {
            "Soft": {"wear_rate": 0.04, "speed_advantage": -1.5},   # Faster, wears quickly
            "Medium": {"wear_rate": 0.02, "speed_advantage": 0.0},  # Balanced
            "Hard": {"wear_rate": 0.01, "speed_advantage": 1.0},   # Slower, highly durable
            "Wet": {"wear_rate": 0.03, "speed_advantage": 2.0}     # Essential in heavy rain
        }
        
        self.reset()

    def reset(self):
        """Resets the race state to lap 1."""
        self.current_lap = 1
        self.fuel_level = 100.0        # Percentage (100% full = max weight penalty)
        self.tyre_wear = 0.0          # 0.0 (new) to 1.0 (completely worn out)
        self.current_compound = "Medium"
        self.weather = "Dry"           # Options: "Dry", "Light Rain", "Heavy Rain"
        self.race_history = []
        return self._get_state()

    def _get_state(self):
        """Returns current dynamic environment variables."""
        return {
            "lap": self.current_lap,
            "fuel": self.fuel_level,
            "tyre_wear": self.tyre_wear,
            "compound": self.current_compound,
            "weather": self.weather
        }

    def _update_weather(self):
        """Markov-style probabilistic weather transitions."""
        rand = random.random()
        if self.weather == "Dry":
            if rand < 0.05:
                self.weather = "Light Rain"
        elif self.weather == "Light Rain":
            if rand < 0.10:
                self.weather = "Heavy Rain"
            elif rand < 0.20:
                self.weather = "Dry"
        elif self.weather == "Heavy Rain":
            if rand < 0.15:
                self.weather = "Light Rain"

    def step(self, pit_action=None):
        """
        Executes one lap.
        pit_action: None or a dict like {"new_compound": "Hard", "refuel": True}
        """
        if self.current_lap > self.total_laps:
            raise Exception("Race already completed!")

        pit_time_spent = 0.0
        
        # 1. Handle Pit Stop Action
        if pit_action is not None:
            pit_time_spent += self.pit_stop_loss
            if "new_compound" in pit_action:
                self.current_compound = pit_action["new_compound"]
                self.tyre_wear = 0.0
            if pit_action.get("refuel", False):
                self.fuel_level = 100.0

        # 2. Calculate Lap Time
        compound_info = self.tyre_compounds[self.current_compound]
        
        # Weight penalty: lighter car (less fuel) runs faster (~0.03s per 1% fuel)
        fuel_penalty = (self.fuel_level / 100.0) * 1.5
        
        # Tyre degradation penalty: non-linear drop as tyres wear out
        tyre_penalty = (self.tyre_wear ** 2) * 4.0
        
        # Weather mismatch penalty
        weather_penalty = 0.0
        if self.weather in ["Light Rain", "Heavy Rain"] and self.current_compound != "Wet":
            weather_penalty = 8.0 if self.weather == "Light Rain" else 20.0
        elif self.weather == "Dry" and self.current_compound == "Wet":
            weather_penalty = 5.0  # Wets overheat quickly on dry track

        lap_time = (
            self.base_lap_time 
            + compound_info["speed_advantage"] 
            + fuel_penalty 
            + tyre_penalty 
            + weather_penalty 
            + pit_time_spent 
            + random.normalvariate(0, 0.2) # Small random noise
        )

        # 3. Update Mechanics State
        self.fuel_level = max(0.0, self.fuel_level - 2.0) # Burn 2% fuel per lap
        self.tyre_wear = min(1.0, self.tyre_wear + compound_info["wear_rate"])
        
        # 4. Advance Race State
        self._update_weather()
        
        log_entry = {
            "lap": self.current_lap,
            "lap_time": round(lap_time, 2),
            "compound": self.current_compound,
            "tyre_wear": round(self.tyre_wear * 100, 1),
            "fuel": round(self.fuel_level, 1),
            "weather": self.weather,
            "pitted": pit_action is not None
        }
        self.race_history.append(log_entry)
        
        self.current_lap += 1
        done = self.current_lap > self.total_laps
        
        return self._get_state(), lap_time, done, log_entry


# --- Example Usage / Verification ---
if __name__ == "__main__":
    env = RaceEnvironment(total_laps=10)
    state = env.reset()
    print("Starting simulation test...")
    
    done = False
    while not done:
        # Example dummy decision: pit on lap 5 for Wet tyres
        action = {"new_compound": "Wet", "refuel": True} if state["lap"] == 5 else None
        state, lap_time, done, log = env.step(pit_action=action)
        print(f"Lap {log['lap']}: Time={log['lap_time']}s | Tyre Wear={log['tyre_wear']}% | Weather={log['weather']} | Pitted={log['pitted']}")