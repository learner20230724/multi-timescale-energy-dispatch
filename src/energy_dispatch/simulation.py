from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import SystemModel


@dataclass(slots=True)
class DispatchSchedule:
    P_thermal: np.ndarray
    P_charge: np.ndarray
    P_discharge: np.ndarray
    P_wind_curt: np.ndarray
    P_solar_curt: np.ndarray
    P_P2G: np.ndarray
    P_P2A: np.ndarray


@dataclass(slots=True)
class DispatchMetrics:
    P_thermal: np.ndarray
    P_charge: np.ndarray
    P_discharge: np.ndarray
    P_wind_curt: np.ndarray
    P_solar_curt: np.ndarray
    P_P2G: np.ndarray
    P_P2A: np.ndarray
    P_wind_actual: np.ndarray
    P_solar_actual: np.ndarray
    P_thermal_total: np.ndarray
    power_balance: np.ndarray
    SOC: np.ndarray
    H2_tank: np.ndarray
    NH3_tank: np.ndarray
    H2_prod: np.ndarray
    H2_supply: np.ndarray
    H2_shortage: np.ndarray
    H2_to_nh3: np.ndarray
    NH3_prod: np.ndarray
    NH3_supply: np.ndarray
    NH3_shortage: np.ndarray
    total_cost: float
    total_carbon: float
    curtailment_ratio: float


def allocate_thermal(
    required_total: float,
    pmin: np.ndarray,
    pmax: np.ndarray,
    weights: np.ndarray,
) -> np.ndarray:
    p = np.asarray(pmin, dtype=float).copy()
    pmin = np.asarray(pmin, dtype=float)
    pmax = np.asarray(pmax, dtype=float)
    weights = np.maximum(np.asarray(weights, dtype=float), 0.0)

    remaining = float(required_total - pmin.sum())
    if remaining <= 0:
        return p

    active = (pmax - pmin) > 1e-8
    while remaining > 1e-8 and np.any(active):
        current_headroom = pmax - p
        weights = weights.copy()
        weights[~active] = 0.0
        if weights.sum() <= np.finfo(float).eps:
            weights = active.astype(float)

        increment = remaining * weights / weights.sum()
        increment = np.minimum(increment, current_headroom)
        p = p + increment
        remaining = float(required_total - p.sum())
        active = (pmax - p) > 1e-8

    return np.clip(p, pmin, pmax)


def decode_dispatch(individual: np.ndarray, model: SystemModel) -> DispatchSchedule:
    individual = np.asarray(individual, dtype=float)
    idx = 0

    thermal_block = individual[idx : idx + model.N_thermal * model.T]
    P_thermal = thermal_block.reshape((model.N_thermal, model.T), order="F")
    idx += model.N_thermal * model.T

    P_charge = individual[idx : idx + model.T].copy()
    idx += model.T
    P_discharge = individual[idx : idx + model.T]
    idx += model.T
    P_wind_curt = individual[idx : idx + model.T]
    idx += model.T
    P_solar_curt = individual[idx : idx + model.T]
    idx += model.T
    P_P2G = individual[idx : idx + model.T]
    idx += model.T
    P_P2A = individual[idx : idx + model.T]

    for i in range(model.N_thermal):
        P_thermal[i, :] = np.clip(P_thermal[i, :], model.P_thermal_min[i], model.P_thermal_max[i])
    P_charge = np.clip(P_charge, 0.0, model.P_charge_max)
    P_discharge = np.clip(P_discharge, 0.0, model.P_discharge_max)
    P_wind_curt = np.clip(P_wind_curt, 0.0, model.P_wind_forecast)
    P_solar_curt = np.clip(P_solar_curt, 0.0, model.P_solar_forecast)
    P_P2G = np.clip(P_P2G, model.P2G_min, model.P2G_max)
    P_P2A = np.clip(P_P2A, model.P2A_min, model.P2A_max)

    storage_net = P_discharge - P_charge
    P_charge = np.maximum(0.0, -storage_net)
    P_discharge = np.maximum(0.0, storage_net)

    thermal_min_total = float(model.P_thermal_min.sum())
    thermal_max_total = float(model.P_thermal_max.sum())

    for t in range(model.T):
        P_wind_act = model.P_wind_forecast[t] - P_wind_curt[t]
        P_solar_act = model.P_solar_forecast[t] - P_solar_curt[t]

        required_thermal = (
            model.P_load_forecast[t]
            + P_charge[t]
            + P_P2G[t]
            + P_P2A[t]
            - P_wind_act
            - P_solar_act
            - P_discharge[t]
        )
        required_thermal = float(np.clip(required_thermal, thermal_min_total, thermal_max_total))

        weights = np.maximum(P_thermal[:, t], 0.0)
        if weights.sum() <= np.finfo(float).eps:
            weights = np.ones(model.N_thermal, dtype=float)
        P_thermal[:, t] = allocate_thermal(required_thermal, model.P_thermal_min, model.P_thermal_max, weights)

        repaired_balance = (
            P_wind_act
            + P_solar_act
            + P_thermal[:, t].sum()
            + P_discharge[t]
            - P_charge[t]
            - P_P2G[t]
            - P_P2A[t]
            - model.P_load_forecast[t]
        )

        if repaired_balance > 0:
            extra_wind_curt = min(repaired_balance, P_wind_act)
            P_wind_curt[t] += extra_wind_curt
            repaired_balance -= extra_wind_curt
        if repaired_balance > 0:
            extra_solar_curt = min(repaired_balance, P_solar_act)
            P_solar_curt[t] += extra_solar_curt

    return DispatchSchedule(
        P_thermal=P_thermal,
        P_charge=P_charge,
        P_discharge=P_discharge,
        P_wind_curt=P_wind_curt,
        P_solar_curt=P_solar_curt,
        P_P2G=P_P2G,
        P_P2A=P_P2A,
    )


def simulate_dispatch(individual: np.ndarray, model: SystemModel) -> DispatchMetrics:
    schedule = decode_dispatch(individual, model)
    T = model.T

    P_wind_actual = model.P_wind_forecast - schedule.P_wind_curt
    P_solar_actual = model.P_solar_forecast - schedule.P_solar_curt
    P_thermal_total = schedule.P_thermal.sum(axis=0)

    power_balance = np.zeros(T, dtype=float)
    SOC = np.zeros(T + 1, dtype=float)
    H2_tank = np.zeros(T + 1, dtype=float)
    NH3_tank = np.zeros(T + 1, dtype=float)
    H2_prod = np.zeros(T, dtype=float)
    H2_supply = np.zeros(T, dtype=float)
    H2_shortage = np.zeros(T, dtype=float)
    H2_to_nh3 = np.zeros(T, dtype=float)
    NH3_prod = np.zeros(T, dtype=float)
    NH3_supply = np.zeros(T, dtype=float)
    NH3_shortage = np.zeros(T, dtype=float)

    SOC[0] = model.SOC_initial * model.E_storage_max
    H2_tank[0] = model.H2_tank_initial
    NH3_tank[0] = model.NH3_tank_initial

    total_cost = 0.0
    total_carbon = 0.0
    penalty_cost = 0.0
    penalty_carbon = 0.0
    P_thermal_prev = model.P_thermal_min.astype(float).copy()

    for t in range(T):
        P_wind_act = P_wind_actual[t]
        P_solar_act = P_solar_actual[t]
        P_thermal_total_t = P_thermal_total[t]

        power_balance[t] = (
            P_wind_act
            + P_solar_act
            + P_thermal_total_t
            + schedule.P_discharge[t]
            - schedule.P_charge[t]
            - schedule.P_P2G[t]
            - schedule.P_P2A[t]
            - model.P_load_forecast[t]
        )

        cost_thermal = 0.0
        carbon_thermal_total = 0.0
        for i in range(model.N_thermal):
            thermal_output = schedule.P_thermal[i, t]
            cost_thermal += (
                model.a_cost[i] * thermal_output**2
                + model.b_cost[i] * thermal_output
                + model.c_cost[i]
            )
            carbon_thermal_total += thermal_output * model.carbon_thermal[i] / 1000.0

            delta_up = thermal_output - P_thermal_prev[i] - model.ramp_up[i]
            delta_down = P_thermal_prev[i] - thermal_output - model.ramp_down[i]
            ramp_violation = max(0.0, delta_up) + max(0.0, delta_down)
            if ramp_violation > 0:
                penalty_cost += 1e4 * ramp_violation**2
                penalty_carbon += 15.0 * ramp_violation**2
        P_thermal_prev = schedule.P_thermal[:, t].copy()

        total_cost += (
            P_wind_act * model.C_wind
            + P_solar_act * model.C_solar
            + cost_thermal
            + (schedule.P_charge[t] + schedule.P_discharge[t]) * model.C_storage_op
            + schedule.P_P2G[t] * model.C_P2G_op
            + schedule.P_P2A[t] * model.C_P2A_op
        )

        soc_candidate = (
            SOC[t]
            + model.eta_charge * schedule.P_charge[t]
            - schedule.P_discharge[t] / model.eta_discharge
        )
        soc_violation = max(0.0, model.SOC_min_abs - soc_candidate) + max(0.0, soc_candidate - model.SOC_max_abs)
        if soc_violation > 0:
            penalty_cost += 1e5 * soc_violation**2
            penalty_carbon += 10.0 * soc_violation**2
        SOC[t + 1] = float(np.clip(soc_candidate, model.SOC_min_abs, model.SOC_max_abs))

        H2_prod[t] = schedule.P_P2G[t] * 1000.0 * model.H2_conversion * model.P2G_efficiency
        H2_available = H2_tank[t] * (1.0 - model.H2_loss_rate) + H2_prod[t]
        H2_for_external = min(model.H2_load_forecast[t], max(0.0, H2_available - model.H2_tank_min))
        H2_supply[t] = H2_for_external
        H2_shortage[t] = model.H2_load_forecast[t] - H2_for_external

        NH3_need = P_thermal_total_t * model.k_NH3 * model.r_NH3
        H2_need_for_nh3 = NH3_need * model.H2_to_NH3_ratio / model.P2A_efficiency
        H2_available_after_load = H2_available - H2_for_external
        H2_cap_by_power = model.P2A_H2_input_max * schedule.P_P2A[t] / max(model.P2A_max, np.finfo(float).eps)
        H2_available_for_nh3 = max(0.0, H2_available_after_load - model.H2_tank_min)
        H2_to_nh3[t] = min(H2_need_for_nh3, H2_cap_by_power, H2_available_for_nh3)

        H2_candidate = H2_available_after_load - H2_to_nh3[t]
        H2_violation = max(0.0, model.H2_tank_min - H2_candidate) + max(0.0, H2_candidate - model.H2_tank_max)
        if H2_violation > 0:
            penalty_cost += 5e4 * H2_violation**2
            penalty_carbon += 5.0 * H2_violation**2
        H2_tank[t + 1] = float(np.clip(H2_candidate, model.H2_tank_min, model.H2_tank_max))

        NH3_power_cap = model.NH3_production_max * schedule.P_P2A[t] / max(model.P2A_max, np.finfo(float).eps)
        NH3_prod[t] = min(H2_to_nh3[t] * model.P2A_efficiency / model.H2_to_NH3_ratio, NH3_power_cap)

        NH3_available = NH3_tank[t] * (1.0 - model.NH3_loss_rate) + NH3_prod[t]
        NH3_supply[t] = min(NH3_need, max(0.0, NH3_available - model.NH3_tank_min))
        NH3_shortage[t] = NH3_need - NH3_supply[t]

        NH3_candidate = NH3_available - NH3_supply[t]
        NH3_violation = max(0.0, model.NH3_tank_min - NH3_candidate) + max(0.0, NH3_candidate - model.NH3_tank_max)
        if NH3_violation > 0:
            penalty_cost += 2e4 * NH3_violation**2
            penalty_carbon += 2.0 * NH3_violation**2
        NH3_tank[t + 1] = float(np.clip(NH3_candidate, model.NH3_tank_min, model.NH3_tank_max))

        total_cost -= (NH3_supply[t] / 1000.0) * model.NH3_coal_replacement * model.coal_price
        total_carbon += (
            carbon_thermal_total
            - schedule.P_P2G[t] * model.P2G_carbon_reduction / 1000.0
            - (NH3_supply[t] / 1000.0) * model.CO2_reduction_per_combustion
        )

        if abs(power_balance[t]) > 1e-3:
            penalty_cost += 2e5 * power_balance[t] ** 2
            penalty_carbon += 100.0 * power_balance[t] ** 2

        simultaneous_power = min(schedule.P_charge[t], schedule.P_discharge[t])
        if simultaneous_power > 0:
            penalty_cost += 2e4 * simultaneous_power**2
            penalty_carbon += 20.0 * simultaneous_power**2

        if H2_shortage[t] > 0:
            penalty_cost += 8e3 * H2_shortage[t] ** 2
            penalty_carbon += 0.8 * H2_shortage[t] ** 2
        if NH3_shortage[t] > 0:
            penalty_cost += 5e3 * NH3_shortage[t] ** 2
            penalty_carbon += 0.5 * NH3_shortage[t] ** 2

    final_soc_dev = SOC[-1] - model.SOC_target_final
    if abs(final_soc_dev) > 1e-6:
        penalty_cost += 3e3 * final_soc_dev**2
        penalty_carbon += 3.0 * final_soc_dev**2

    renewable_total = model.P_wind_forecast.sum() + model.P_solar_forecast.sum()
    curtailment_ratio = (schedule.P_wind_curt.sum() + schedule.P_solar_curt.sum()) / max(renewable_total, np.finfo(float).eps)

    return DispatchMetrics(
        P_thermal=schedule.P_thermal,
        P_charge=schedule.P_charge,
        P_discharge=schedule.P_discharge,
        P_wind_curt=schedule.P_wind_curt,
        P_solar_curt=schedule.P_solar_curt,
        P_P2G=schedule.P_P2G,
        P_P2A=schedule.P_P2A,
        P_wind_actual=P_wind_actual,
        P_solar_actual=P_solar_actual,
        P_thermal_total=P_thermal_total,
        power_balance=power_balance,
        SOC=SOC,
        H2_tank=H2_tank,
        NH3_tank=NH3_tank,
        H2_prod=H2_prod,
        H2_supply=H2_supply,
        H2_shortage=H2_shortage,
        H2_to_nh3=H2_to_nh3,
        NH3_prod=NH3_prod,
        NH3_supply=NH3_supply,
        NH3_shortage=NH3_shortage,
        total_cost=max(total_cost + penalty_cost, 0.0),
        total_carbon=max(total_carbon + penalty_carbon, 0.0),
        curtailment_ratio=float(curtailment_ratio),
    )


def objective_values(individual: np.ndarray, model: SystemModel) -> np.ndarray:
    metrics = simulate_dispatch(individual, model)
    return np.array([metrics.total_cost, metrics.total_carbon, metrics.curtailment_ratio], dtype=float)
