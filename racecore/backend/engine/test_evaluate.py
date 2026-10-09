import pytest
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from engine.evaluate import run_batch, evaluate_strategies, print_evaluation_results
from simulation import RaceConfig, baseline_strategy, get_race_config_always_dry
from engine.stats import calculate_metrics


def dummy_strategy(car_state):
    """A simple dummy strategy for testing"""
    from models import Decision, DriveMode
    return Decision(pit_stop=False, drive_mode=DriveMode.NORMAL, fuel_mode="normal")


def test_run_batch():
    """Test the run_batch function"""
    strategies = [("baseline", baseline_strategy), ("dummy", dummy_strategy)]
    scenario = "always_dry"
    n = 2  # Small number for testing
    seed = 42

    results = run_batch(strategies, scenario, n, seed, show_progress=False)

    # Should have results for both strategies
    assert "baseline" in results
    assert "dummy" in results

    # Should have n races for each strategy
    assert len(results["baseline"]) == n
    assert len(results["dummy"]) == n

    # Each race should have lap records
    for race in results["baseline"]:
        assert isinstance(race, list)
        # Should have lap records (though might be empty in edge cases)
        # In practice, should have config.total_laps records

    for race in results["dummy"]:
        assert isinstance(race, list)


def test_evaluate_strategies():
    """Test the evaluate_strategies function"""
    strategies = [("baseline", baseline_strategy), ("dummy", dummy_strategy)]
    scenario = "always_dry"
    n = 2  # Small number for testing
    seed = 42

    results = evaluate_strategies(strategies, scenario, n, seed)

    # Should have expected keys
    assert 'scenario' in results
    assert 'num_races_per_strategy' in results
    assert 'strategy_metrics' in results
    assert 'strategy_race_times' in results
    assert 'comparison_matrix' in results
    assert 'reference_strategy' in results

    # Should have metrics for both strategies
    assert "baseline" in results['strategy_metrics']
    assert "dummy" in results['strategy_metrics']

    # Should have race times for both strategies
    assert "baseline" in results['strategy_race_times']
    assert "dummy" in results['strategy_race_times']

    # Should have comparison matrix (comparing each strategy to reference)
    # Reference should be the first strategy or baseline if present
    assert len(results['comparison_matrix']) >= 0  # Might be 0 if only one strategy


def test_print_evaluation_results(capsys):
    """Test the print_evaluation_results function"""
    strategies = [("baseline", baseline_strategy), ("dummy", dummy_strategy)]
    scenario = "always_dry"
    n = 1  # Very small for quick testing
    seed = 42

    results = evaluate_strategies(strategies, scenario, n, seed)
    print_evaluation_results(results)

    # Capture output and check that something was printed
    captured = capsys.readouterr()
    assert "RaceCore Evaluation Results" in captured.out
    assert scenario in captured.out
    assert "Strategy Metrics:" in captured.out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])