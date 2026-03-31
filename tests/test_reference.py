from __future__ import annotations

import numpy as np

from energy_dispatch.config import build_default_model
from energy_dispatch.optimization import build_decision_bounds
from energy_dispatch.simulation import decode_dispatch, simulate_dispatch


def test_reference_shapes_and_ranges() -> None:
    model = build_default_model(seed=42)
    xl, xu = build_decision_bounds(model)
    individual = (0.25 * xl) + (0.75 * xu)

    schedule = decode_dispatch(individual, model)
    metrics = simulate_dispatch(individual, model)

    assert schedule.P_thermal.shape == (3, 24)
    assert metrics.power_balance.shape == (24,)
    assert metrics.SOC.shape == (25,)
    assert metrics.H2_tank.shape == (25,)
    assert metrics.NH3_tank.shape == (25,)
    assert np.all(metrics.SOC >= model.SOC_min_abs - 1e-9)
    assert np.all(metrics.SOC <= model.SOC_max_abs + 1e-9)
    assert np.all(metrics.H2_tank >= model.H2_tank_min - 1e-9)
    assert np.all(metrics.H2_tank <= model.H2_tank_max + 1e-9)
    assert np.all(metrics.NH3_tank >= model.NH3_tank_min - 1e-9)
    assert np.all(metrics.NH3_tank <= model.NH3_tank_max + 1e-9)
    assert metrics.total_cost >= 0.0
    assert metrics.total_carbon >= 0.0
