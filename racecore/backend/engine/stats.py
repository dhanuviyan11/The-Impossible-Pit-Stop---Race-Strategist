"""
Statistics module for RaceCore evaluation.
Contains functions for calculating metrics and bootstrap confidence intervals.
"""

import numpy as np
from typing import List, Tuple, Dict, Any
from simulation import LapRecord


def calculate_metrics(lap_records_list: List[List[LapRecord]]) -> Dict[str, float]:
    """
    Calculate metrics for a list of race results.

    Args:
        lap_records_list: List of lists of LapRecord objects (each inner list is a race)

    Returns:
        Dictionary containing various metrics
    """
    if not lap_records_list or not lap_records_list[0]:
        return {}

    # Flatten all lap records to get race times
    race_times = []
    positions = []  # Would need to be calculated from lap records in a full implementation
    stop_counts = []  # Would need to be calculated from pit stops
    retirement_rates = []  # Would need to be calculated from DNFs

    for lap_records in lap_records_list:
        if not lap_records:
            continue

        # Calculate total race time
        total_time = sum(record.lap_time for record in lap_records)
        race_times.append(total_time)

        # For now, use placeholder values for other metrics
        # In a full implementation, these would be calculated from the lap records
        positions.append(1.0)  # Placeholder
        stop_counts.append(sum(1 for r in lap_records if r.lap_time > 120))  # Rough pit stop estimate
        retirement_rates.append(0.0)  # Placeholder (no retirements in current implementation)

    if not race_times:
        return {}

    race_times = np.array(race_times)
    positions = np.array(positions)
    stop_counts = np.array(stop_counts)
    retirement_rates = np.array(retirement_rates)

    return {
        'mean_race_time': np.mean(race_times),
        'median_race_time': np.median(race_times),
        'std_race_time': np.std(race_times),
        'p5_race_time': np.percentile(race_times, 5),
        'p95_race_time': np.percentile(race_times, 95),
        'min_race_time': np.min(race_times),
        'max_race_time': np.max(race_times),
        'mean_position': np.mean(positions),
        'mean_stops': np.mean(stop_counts),
        'retirement_rate': np.mean(retirement_rates)
    }


def bootstrap_difference(sample1: List[float], sample2: List[float],
                        n_bootstrap: int = 1000) -> Tuple[float, Tuple[float, float], bool]:
    """
    Calculate bootstrap 95% confidence interval for difference of means.

    Args:
        sample1: First sample (e.g., race times for strategy A)
        sample2: Second sample (e.g., race times for strategy B)
        n_bootstrap: Number of bootstrap samples

    Returns:
        Tuple of (mean_difference, (ci_lower, ci_upper), significant)
        where significant is True if the confidence interval does not include 0
    """
    if not sample1 or not sample2:
        return 0.0, (0.0, 0.0), False

    sample1 = np.array(sample1)
    sample2 = np.array(sample2)

    # Observed difference
    obs_diff = np.mean(sample1) - np.mean(sample2)

    # Bootstrap differences
    bootstrap_diffs = []
    n1, n2 = len(sample1), len(sample2)

    for _ in range(n_bootstrap):
        # Resample with replacement
        boot_sample1 = np.random.choice(sample1, size=n1, replace=True)
        boot_sample2 = np.random.choice(sample2, size=n2, replace=True)
        boot_diff = np.mean(boot_sample1) - np.mean(boot_sample2)
        bootstrap_diffs.append(boot_diff)

    # Calculate confidence interval
    ci_lower = np.percentile(bootstrap_diffs, 2.5)
    ci_upper = np.percentile(bootstrap_diffs, 97.5)

    # Check if significant (does CI exclude 0?)
    significant = not (ci_lower <= 0 <= ci_upper)

    return obs_diff, (ci_lower, ci_upper), significant


def calculate_win_rate(strategy_times: List[float], baseline_times: List[float]) -> float:
    """
    Calculate win rate of strategy against baseline.

    Args:
        strategy_times: List of race times for the strategy
        baseline_times: List of race times for the baseline

    Returns:
        Win rate as a fraction (0.0 to 1.0)
    """
    if not strategy_times or not baseline_times:
        return 0.0

    wins = sum(1 for s_time, b_time in zip(strategy_times, baseline_times) if s_time < b_time)
    return wins / len(strategy_times)