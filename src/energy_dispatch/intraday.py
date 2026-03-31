from __future__ import annotations

from typing import Any

import numpy as np

from .config import IntradayParams, SystemModel
from .simulation import DispatchMetrics


def intraday_adjustment_step(
    P_wind_fc: float,
    P_solar_fc: float,
    P_load_fc: float,
    P_thermal_fix: float,
    P_P2G_fix: float,
    P_P2A_fix: float,
    P_ch_ref: float,
    P_dis_ref: float,
    SOC_now: float,
    SOC_ref: float,
    params: IntradayParams,
) -> tuple[float, float, float, float]:
    dt = params.dt
    SOC_min_abs = params.SOC_min * params.E_storage_max
    SOC_max_abs = params.SOC_max * params.E_storage_max

    P_storage_ref = P_dis_ref - P_ch_ref
    P_balance_ref = P_wind_fc + P_solar_fc + P_thermal_fix + P_storage_ref - P_P2G_fix - P_P2A_fix - P_load_fc
    P_storage_target = P_storage_ref - P_balance_ref - params.soc_track_gain * (SOC_ref - SOC_now) / dt

    charge_limit = min(params.P_charge_max, max(0.0, (SOC_max_abs - SOC_now) / (params.eta_charge * dt)))
    discharge_limit = min(params.P_discharge_max, max(0.0, (SOC_now - SOC_min_abs) * params.eta_discharge / dt))

    P_ch_ref_clamped = min(max(P_ch_ref, 0.0), charge_limit)
    P_dis_ref_clamped = min(max(P_dis_ref, 0.0), discharge_limit)
    P_storage_ref_clamped = P_dis_ref_clamped - P_ch_ref_clamped
    P_balance_ref_clamped = (
        P_wind_fc
        + P_solar_fc
        + P_thermal_fix
        + P_storage_ref_clamped
        - P_P2G_fix
        - P_P2A_fix
        - P_load_fc
    )

    if abs(P_balance_ref_clamped) <= params.imbalance_deadband:
        P_ch = P_ch_ref_clamped
        P_dis = P_dis_ref_clamped
        SOC_next = SOC_now + params.eta_charge * P_ch * dt - P_dis / params.eta_discharge * dt
        SOC_next = float(np.clip(SOC_next, SOC_min_abs, SOC_max_abs))
        delta_P_residual = -P_balance_ref_clamped
        return P_ch, P_dis, SOC_next, delta_P_residual

    if P_storage_target >= 0:
        P_dis = min(P_storage_target, discharge_limit)
        P_ch = 0.0
    else:
        P_ch = min(-P_storage_target, charge_limit)
        P_dis = 0.0

    P_balance_candidate = P_wind_fc + P_solar_fc + P_thermal_fix + P_dis - P_ch - P_P2G_fix - P_P2A_fix - P_load_fc
    if abs(P_balance_candidate) > abs(P_balance_ref_clamped):
        P_ch = P_ch_ref_clamped
        P_dis = P_dis_ref_clamped

    SOC_next = SOC_now + params.eta_charge * P_ch * dt - P_dis / params.eta_discharge * dt
    SOC_next = float(np.clip(SOC_next, SOC_min_abs, SOC_max_abs))

    P_balance_after = P_wind_fc + P_solar_fc + P_thermal_fix + P_dis - P_ch - P_P2G_fix - P_P2A_fix - P_load_fc
    delta_P_residual = -P_balance_after
    return P_ch, P_dis, SOC_next, delta_P_residual


def run_intraday(
    model: SystemModel,
    best_metrics: DispatchMetrics,
    sigma: float = 0.02,
    seed: int = 42,
) -> dict[str, Any]:
    rng = np.random.default_rng(seed + 1)

    P_wind_da_15min = np.repeat(model.P_wind_forecast, 4)
    P_solar_da_15min = np.repeat(model.P_solar_forecast, 4)
    P_load_da_15min = np.repeat(model.P_load_forecast, 4)

    P_wind_fc_15min = np.maximum(0.0, P_wind_da_15min * (1.0 + sigma * rng.standard_normal(96)))
    P_solar_fc_15min = np.maximum(0.0, P_solar_da_15min * (1.0 + sigma * rng.standard_normal(96)))
    P_load_fc_15min = np.maximum(0.0, P_load_da_15min * (1.0 + sigma * rng.standard_normal(96)))

    P_ch_da_15min = np.repeat(best_metrics.P_charge, 4)
    P_dis_da_15min = np.repeat(best_metrics.P_discharge, 4)
    P_thermal_da_15min = np.repeat(best_metrics.P_thermal_total, 4)
    P_P2G_da_15min = np.repeat(best_metrics.P_P2G, 4)
    P_P2A_da_15min = np.repeat(best_metrics.P_P2A, 4)
    P_wc_da_15min = np.repeat(best_metrics.P_wind_curt, 4)
    P_sc_da_15min = np.repeat(best_metrics.P_solar_curt, 4)

    P_wind_inj_da_15min = np.maximum(0.0, P_wind_da_15min - P_wc_da_15min)
    P_solar_inj_da_15min = np.maximum(0.0, P_solar_da_15min - P_sc_da_15min)
    P_wind_inj_fc_15min = np.maximum(0.0, P_wind_fc_15min - P_wc_da_15min)
    P_solar_inj_fc_15min = np.maximum(0.0, P_solar_fc_15min - P_sc_da_15min)

    SOC_da_15min = np.zeros(97, dtype=float)
    SOC_da_15min[0] = model.SOC_initial * model.E_storage_max
    for k in range(96):
        hour_idx = k // 4
        SOC_da_15min[k + 1] = (
            SOC_da_15min[k]
            + model.eta_charge * best_metrics.P_charge[hour_idx] * 0.25
            - best_metrics.P_discharge[hour_idx] / model.eta_discharge * 0.25
        )
        SOC_da_15min[k + 1] = np.clip(SOC_da_15min[k + 1], model.SOC_min_abs, model.SOC_max_abs)

    params = IntradayParams(
        E_storage_max=model.E_storage_max,
        P_charge_max=model.P_charge_max,
        P_discharge_max=model.P_discharge_max,
        eta_charge=model.eta_charge,
        eta_discharge=model.eta_discharge,
        SOC_min=model.SOC_min,
        SOC_max=model.SOC_max,
        dt=0.25,
        soc_track_gain=0.05,
        imbalance_deadband=5.0,
    )

    SOC = model.SOC_initial * model.E_storage_max
    P_ch_id = np.zeros(96, dtype=float)
    P_dis_id = np.zeros(96, dtype=float)
    SOC_id = np.zeros(97, dtype=float)
    SOC_id[0] = SOC
    residual_id = np.zeros(96, dtype=float)

    for k in range(96):
        Pch, Pdis, SOC_next, residual = intraday_adjustment_step(
            P_wind_inj_fc_15min[k],
            P_solar_inj_fc_15min[k],
            P_load_fc_15min[k],
            P_thermal_da_15min[k],
            P_P2G_da_15min[k],
            P_P2A_da_15min[k],
            P_ch_da_15min[k],
            P_dis_da_15min[k],
            SOC,
            SOC_da_15min[k],
            params,
        )
        P_ch_id[k] = Pch
        P_dis_id[k] = Pdis
        SOC_id[k + 1] = SOC_next
        residual_id[k] = residual
        SOC = SOC_next

    P_net_da = P_load_da_15min - (
        P_wind_inj_da_15min
        + P_solar_inj_da_15min
        + P_thermal_da_15min
        + P_dis_da_15min
        - P_ch_da_15min
        - P_P2G_da_15min
        - P_P2A_da_15min
    )
    P_net_id = P_load_fc_15min - (
        P_wind_inj_fc_15min
        + P_solar_inj_fc_15min
        + P_thermal_da_15min
        + P_dis_id
        - P_ch_id
        - P_P2G_da_15min
        - P_P2A_da_15min
    )

    state = np.zeros(96, dtype=int)
    state[P_ch_id > 0.1] = 1
    state[P_dis_id > 0.1] = 2
    switch_count = int(np.sum(np.abs(np.diff(state)) > 0))

    rms_ch_dev = float(np.sqrt(np.mean((P_ch_id - P_ch_da_15min) ** 2)))
    rms_dis_dev = float(np.sqrt(np.mean((P_dis_id - P_dis_da_15min) ** 2)))
    rms_soc_dev = float(np.sqrt(np.mean((SOC_id - SOC_da_15min) ** 2)))
    max_soc_dev = float(np.max(np.abs(SOC_id - SOC_da_15min)))
    rms_net_actual = float(np.sqrt(np.mean(P_net_id**2)))
    rms_net_if_da = float(
        np.sqrt(
            np.mean(
                (
                    P_load_fc_15min
                    - (
                        P_wind_inj_fc_15min
                        + P_solar_inj_fc_15min
                        + P_thermal_da_15min
                        + P_dis_da_15min
                        - P_ch_da_15min
                        - P_P2G_da_15min
                        - P_P2A_da_15min
                    )
                )
                ** 2
            )
        )
    )

    intraday_fallback_used = False
    if rms_net_actual > rms_net_if_da:
        intraday_fallback_used = True
        P_ch_id = P_ch_da_15min.copy()
        P_dis_id = P_dis_da_15min.copy()
        SOC_id = SOC_da_15min.copy()
        P_net_id = P_load_fc_15min - (
            P_wind_inj_fc_15min
            + P_solar_inj_fc_15min
            + P_thermal_da_15min
            + P_dis_id
            - P_ch_id
            - P_P2G_da_15min
            - P_P2A_da_15min
        )
        residual_id = P_net_id.copy()
        state = np.zeros(96, dtype=int)
        state[P_ch_id > 0.1] = 1
        state[P_dis_id > 0.1] = 2
        switch_count = int(np.sum(np.abs(np.diff(state)) > 0))
        rms_ch_dev = float(np.sqrt(np.mean((P_ch_id - P_ch_da_15min) ** 2)))
        rms_dis_dev = float(np.sqrt(np.mean((P_dis_id - P_dis_da_15min) ** 2)))
        rms_soc_dev = float(np.sqrt(np.mean((SOC_id - SOC_da_15min) ** 2)))
        max_soc_dev = float(np.max(np.abs(SOC_id - SOC_da_15min)))
        rms_net_actual = float(np.sqrt(np.mean(P_net_id**2)))

    return {
        "P_ch_day_ahead": P_ch_da_15min,
        "P_dis_day_ahead": P_dis_da_15min,
        "P_ch_intraday": P_ch_id,
        "P_dis_intraday": P_dis_id,
        "SOC_day_ahead": SOC_da_15min,
        "SOC_intraday": SOC_id,
        "P_net_day_ahead": P_net_da,
        "P_net_intraday": P_net_id,
        "P_wind_day_ahead": P_wind_da_15min,
        "P_solar_day_ahead": P_solar_da_15min,
        "P_load_day_ahead": P_load_da_15min,
        "P_wind_intraday_forecast": P_wind_fc_15min,
        "P_solar_intraday_forecast": P_solar_fc_15min,
        "P_load_intraday_forecast": P_load_fc_15min,
        "residual": residual_id,
        "charge_rms_dev": rms_ch_dev,
        "discharge_rms_dev": rms_dis_dev,
        "soc_rms_dev": rms_soc_dev,
        "soc_max_dev": max_soc_dev,
        "net_rms_intraday": rms_net_actual,
        "net_rms_if_day_ahead": rms_net_if_da,
        "switch_count": switch_count,
        "fallback_used": intraday_fallback_used,
    }
