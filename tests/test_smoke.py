from __future__ import annotations

import numpy as np

from energy_dispatch.config import RunConfig, build_default_model
from energy_dispatch.intraday import run_intraday
from energy_dispatch.optimization import build_decision_bounds, run_day_ahead
from energy_dispatch.simulation import decode_dispatch, objective_values, simulate_dispatch


def test_decode_dispatch_respects_bounds() -> None:
    model = build_default_model(seed=42)
    xl, xu = build_decision_bounds(model)
    individual = xu + 100.0
    schedule = decode_dispatch(individual, model)

    assert schedule.P_thermal.shape == (model.N_thermal, model.T)
    assert np.all(schedule.P_thermal >= model.P_thermal_min[:, None])
    assert np.all(schedule.P_thermal <= model.P_thermal_max[:, None])
    assert np.all(schedule.P_charge >= 0.0)
    assert np.all(schedule.P_discharge >= 0.0)
    assert np.all(schedule.P_wind_curt <= model.P_wind_forecast + 1e-9)
    assert np.all(schedule.P_solar_curt <= model.P_solar_forecast + 1e-9)
    assert np.all(schedule.P_P2G >= model.P2G_min)
    assert np.all(schedule.P_P2G <= model.P2G_max)
    assert np.all(schedule.P_P2A >= model.P2A_min)
    assert np.all(schedule.P_P2A <= model.P2A_max)


def test_simulation_returns_finite_objectives() -> None:
    model = build_default_model(seed=42)
    xl, xu = build_decision_bounds(model)
    individual = (xl + xu) / 2.0

    metrics = simulate_dispatch(individual, model)
    objectives = objective_values(individual, model)

    assert np.isfinite(metrics.total_cost)
    assert np.isfinite(metrics.total_carbon)
    assert 0.0 <= metrics.curtailment_ratio <= 1.0
    assert objectives.shape == (3,)
    assert np.all(np.isfinite(objectives))


def test_small_pipeline_smoke() -> None:
    config = RunConfig(seed=42, pop_size=12, max_gen=3, verbose=False)
    model = build_default_model(seed=config.seed)
    day_ahead = run_day_ahead(model, config)
    intraday = run_intraday(model, day_ahead["best_metrics"], sigma=config.intraday_error_sigma, seed=config.seed)

    assert day_ahead["pareto_population"].shape[0] >= 1
    assert day_ahead["pareto_objectives"].shape[1] == 3
    assert day_ahead["best_individual"].shape == (model.n_vars,)
    assert len(day_ahead["pareto_history"]) == config.max_gen
    assert intraday["P_ch_intraday"].shape == (96,)
    assert intraday["SOC_intraday"].shape == (97,)
    assert np.isfinite(intraday["net_rms_intraday"])
