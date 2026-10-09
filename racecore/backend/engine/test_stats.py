import pytest
import numpy as np
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from engine.stats import calculate_metrics, bootstrap_difference, calculate_win_rate
from simulation import LapRecord
from models import CarState, WeatherCondition, DriveMode


def test_calculate_metrics_empty():
    """Test calculate_metrics with empty input"""
    result = calculate_metrics([])
    assert result == {}

    result = calculate_metrics([[]])
    assert result == {}


def test_calculate_metrics_with_data():
    """Test calculate_metrics with sample data"""
    # Create some mock lap records
    lap_records1 = [
        LapRecord(lap=1, lap_time=90.0, fuel_remaining=98.0, tyre_wear=0.01, tyre_temp=90.0,
                  compound="medium", weather=WeatherCondition.DRY, drive_mode=DriveMode.NORMAL,
                  safety_car=False, vsc=False, timestamp=1.0),
        LapRecord(lap=2, lap_time=91.0, fuel_remaining=96.0, tyre_wear=0.02, tyre_temp=91.0,
                  compound="medium", weather=WeatherCondition.DRY, drive_mode=DriveMode.NORMAL,
                  safety_car=False, vsc=False, timestamp=2.0)
    ]

    lap_records2 = [
        LapRecord(lap=1, lap_time=89.0, fuel_remaining=98.5, tyre_wear=0.01, tyre_temp=89.0,
                  compound="medium", weather=WeatherCondition.DRY, drive_mode=DriveMode.NORMAL,
                  safety_car=False, vsc=False, timestamp=1.0),
        LapRecord(lap=2, lap_time=90.0, fuel_remaining=97.0, tyre_wear=0.02, tyre_temp=90.0,
                  compound="medium", weather=WeatherCondition.DRY, drive_mode=DriveMode.NORMAL,
                  safety_car=False, vsc=False, timestamp=2.0)
    ]

    lap_records_list = [lap_records1, lap_records2]

    metrics = calculate_metrics(lap_records_list)

    # Should have calculated metrics
    assert 'mean_race_time' in metrics
    assert 'median_race_time' in metrics
    assert 'std_race_time' in metrics
    assert metrics['mean_race_time'] > 0
    assert metrics['median_race_time'] > 0


def test_bootstrap_difference():
    """Test bootstrap_difference function"""
    sample1 = [10.0, 10.5, 11.0, 9.5, 10.0]  # Mean = 10.2
    sample2 = [12.0, 12.5, 11.5, 12.0, 11.0]  # Mean = 11.8

    diff, ci, significant = bootstrap_difference(sample1, sample2, n_bootstrap=100)

    # Difference should be negative (sample1 < sample2)
    assert diff < 0

    # Confidence interval should be reasonable
    assert ci[0] < ci[1]

    # Should be significant (non-overlapping samples)
    assert significant == True


def test_bootstrap_difference_no_significance():
    """Test bootstrap_difference with similar samples"""
    sample1 = [10.0, 10.5, 11.0, 9.5, 10.0]  # Mean = 10.2
    sample2 = [10.2, 10.7, 10.8, 9.7, 10.3]   # Mean = 10.34

    diff, ci, significant = bootstrap_difference(sample1, sample2, n_bootstrap=100)

    # Might not be significant with overlapping samples
    # Just check that it returns valid values
    assert isinstance(diff, float)
    assert isinstance(ci, tuple)
    assert len(ci) == 2
    assert isinstance(significant, bool)


def test_calculate_win_rate():
    """Test calculate_win_rate function"""
    strategy_times = [100.0, 95.0, 105.0, 90.0, 100.0]  # 2 wins (95, 90)
    baseline_times = [100.0, 100.0, 100.0, 100.0, 100.0]  # All 100

    win_rate = calculate_win_rate(strategy_times, baseline_times)

    # Should be 0.4 (2 wins out of 5)
    assert win_rate == 0.4


def test_calculate_win_rate_edge_cases():
    """Test calculate_win_rate with edge cases"""
    # Empty lists
    assert calculate_win_rate([], []) == 0.0
    assert calculate_win_rate([100.0], []) == 0.0
    assert calculate_win_rate([], [100.0]) == 0.0

    # Perfect win/loss
    assert calculate_win_rate([90.0, 95.0], [100.0, 100.0]) == 1.0
    assert calculate_win_rate([110.0, 115.0], [100.0, 100.0]) == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])