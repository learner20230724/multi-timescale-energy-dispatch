from __future__ import annotations

from typing import Any

import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.core.problem import Problem
from pymoo.optimize import minimize
from pymoo.operators.crossover.sbx import SBX
from pymoo.operators.mutation.pm import PM
from pymoo.operators.sampling.rnd import FloatRandomSampling

from .config import RunConfig, SystemModel
from .simulation import DispatchMetrics, objective_values, simulate_dispatch


class DispatchProblem(Problem):
    def __init__(self, model: SystemModel):
        xl, xu = build_decision_bounds(model)
        super().__init__(n_var=model.n_vars, n_obj=3, n_ieq_constr=0, xl=xl, xu=xu)
        self.model = model

    def _evaluate(self, X: np.ndarray, out: dict[str, Any], *args: Any, **kwargs: Any) -> None:
        X = np.atleast_2d(np.asarray(X, dtype=float))
        out["F"] = np.vstack([objective_values(individual, self.model) for individual in X])


def build_decision_bounds(model: SystemModel) -> tuple[np.ndarray, np.ndarray]:
    lower_parts: list[np.ndarray] = []
    upper_parts: list[np.ndarray] = []

    for i in range(model.N_thermal):
        lower_parts.append(np.full(model.T, model.P_thermal_min[i], dtype=float))
        upper_parts.append(np.full(model.T, model.P_thermal_max[i], dtype=float))

    lower_parts.extend(
        [
            np.zeros(model.T, dtype=float),
            np.zeros(model.T, dtype=float),
            np.zeros(model.T, dtype=float),
            np.zeros(model.T, dtype=float),
            np.full(model.T, model.P2G_min, dtype=float),
            np.full(model.T, model.P2A_min, dtype=float),
        ]
    )
    upper_parts.extend(
        [
            np.full(model.T, model.P_charge_max, dtype=float),
            np.full(model.T, model.P_discharge_max, dtype=float),
            model.P_wind_forecast.astype(float),
            model.P_solar_forecast.astype(float),
            np.full(model.T, model.P2G_max, dtype=float),
            np.full(model.T, model.P2A_max, dtype=float),
        ]
    )

    return np.concatenate(lower_parts), np.concatenate(upper_parts)


def _ensure_2d(values: np.ndarray, columns: int) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.size == 0:
        return np.empty((0, columns), dtype=float)
    if array.ndim == 1:
        return array.reshape(1, -1)
    return array


def select_compromise_solution(
    pareto_population: np.ndarray,
    pareto_objectives: np.ndarray,
    model: SystemModel,
) -> tuple[int, DispatchMetrics, dict[str, Any]]:
    pareto_population = _ensure_2d(pareto_population, model.n_vars)
    pareto_objectives = _ensure_2d(pareto_objectives, 3)
    if pareto_population.shape[0] == 0:
        raise ValueError("No Pareto solutions were produced")

    metrics_list: list[DispatchMetrics] = []
    feasibility_score = np.zeros(pareto_population.shape[0], dtype=float)
    feasible_mask = np.zeros(pareto_population.shape[0], dtype=bool)

    for i in range(pareto_population.shape[0]):
        metrics = simulate_dispatch(pareto_population[i], model)
        metrics_list.append(metrics)
        max_balance = np.max(np.abs(metrics.power_balance))
        total_h2_shortage = np.sum(metrics.H2_shortage)
        total_nh3_shortage = np.sum(metrics.NH3_shortage)
        final_soc_dev = abs(metrics.SOC[-1] - model.SOC_target_final)
        feasibility_score[i] = (
            max_balance
            + 2.0 * np.mean(np.abs(metrics.power_balance))
            + 0.20 * final_soc_dev
            + 20.0 * total_h2_shortage
            + 10.0 * total_nh3_shortage
        )
        feasible_mask[i] = (
            max_balance < 1.0
            and total_h2_shortage < 1e-6
            and total_nh3_shortage < 1e-6
            and final_soc_dev < 10.0
        )

    if pareto_population.shape[0] == 1:
        best_index = 0
    else:
        candidate_idx = np.flatnonzero(feasible_mask)
        if candidate_idx.size == 0:
            candidate_idx = np.array([int(np.argmin(feasibility_score))], dtype=int)

        if candidate_idx.size == 1:
            best_index = int(candidate_idx[0])
        else:
            obj_min = pareto_objectives[candidate_idx].min(axis=0)
            obj_max = pareto_objectives[candidate_idx].max(axis=0)
            obj_range = obj_max - obj_min
            candidate_obj = np.where(
                obj_range > np.finfo(float).eps,
                (pareto_objectives[candidate_idx] - obj_min) / obj_range,
                0.5,
            )

            weights = np.array([0.40, 0.35, 0.25], dtype=float)
            weighted_norm = candidate_obj * weights
            ideal_best = np.min(weighted_norm, axis=0)
            ideal_worst = np.max(weighted_norm, axis=0)
            d_plus = np.sqrt(np.sum((weighted_norm - ideal_best) ** 2, axis=1))
            d_minus = np.sqrt(np.sum((weighted_norm - ideal_worst) ** 2, axis=1))
            closeness = d_minus / (d_plus + d_minus + np.finfo(float).eps)
            best_index = int(candidate_idx[int(np.argmax(closeness))])

    selection_details = {
        "feasible_mask": feasible_mask,
        "feasibility_score": feasibility_score,
        "best_pareto_index": best_index,
    }
    return best_index, metrics_list[best_index], selection_details


def run_day_ahead(model: SystemModel, config: RunConfig) -> dict[str, Any]:
    problem = DispatchProblem(model)
    algorithm = NSGA2(
        pop_size=config.pop_size,
        sampling=FloatRandomSampling(),
        crossover=SBX(prob=config.crossover_prob, eta=15),
        mutation=PM(prob=config.mutation_prob, eta=20),
        eliminate_duplicates=True,
    )
    result = minimize(
        problem,
        algorithm,
        termination=("n_gen", config.max_gen),
        seed=config.seed,
        save_history=True,
        verbose=config.verbose,
    )

    final_population = _ensure_2d(result.pop.get("X"), model.n_vars)
    final_objectives = _ensure_2d(result.pop.get("F"), 3)
    pareto_population = _ensure_2d(result.X, model.n_vars)
    pareto_objectives = _ensure_2d(result.F, 3)

    pareto_history: list[np.ndarray] = []
    for history_entry in result.history:
        opt = history_entry.opt
        if opt is None or len(opt) == 0:
            pareto_history.append(np.empty((0, 3), dtype=float))
        else:
            pareto_history.append(_ensure_2d(opt.get("F"), 3))

    best_index, best_metrics, selection_details = select_compromise_solution(
        pareto_population,
        pareto_objectives,
        model,
    )

    return {
        "final_population": final_population,
        "final_population_objectives": final_objectives,
        "pareto_population": pareto_population,
        "pareto_objectives": pareto_objectives,
        "pareto_history": pareto_history,
        "best_individual": pareto_population[best_index],
        "best_metrics": best_metrics,
        "selection_details": selection_details,
    }
