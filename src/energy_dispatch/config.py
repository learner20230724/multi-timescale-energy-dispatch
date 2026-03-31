from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any

import numpy as np


@dataclass(slots=True)
class RunConfig:
    seed: int = 42
    pop_size: int = 80
    max_gen: int = 100
    crossover_prob: float = 0.85
    mutation_prob: float = 0.06
    intraday_error_sigma: float = 0.02
    enable_plots: bool = False
    verbose: bool = True


@dataclass(slots=True)
class SystemModel:
    T: int
    N_thermal: int
    P_wind_forecast: np.ndarray
    P_solar_forecast: np.ndarray
    P_load_forecast: np.ndarray
    H2_load_forecast: np.ndarray
    P_thermal_min: np.ndarray
    P_thermal_max: np.ndarray
    ramp_up: np.ndarray
    ramp_down: np.ndarray
    a_cost: np.ndarray
    b_cost: np.ndarray
    c_cost: np.ndarray
    carbon_thermal: np.ndarray
    E_storage_max: float
    P_charge_max: float
    P_discharge_max: float
    eta_charge: float
    eta_discharge: float
    SOC_min: float
    SOC_max: float
    SOC_min_abs: float
    SOC_max_abs: float
    SOC_initial: float
    SOC_target_final: float
    P2G_min: float
    P2G_max: float
    P2G_efficiency: float
    H2_conversion: float
    P2G_carbon_reduction: float
    H2_tank_min: float
    H2_tank_max: float
    H2_tank_initial: float
    H2_loss_rate: float
    P2A_min: float
    P2A_max: float
    P2A_efficiency: float
    P2A_H2_input_max: float
    NH3_production_max: float
    H2_to_NH3_ratio: float
    NH3_tank_min: float
    NH3_tank_max: float
    NH3_tank_initial: float
    NH3_loss_rate: float
    r_NH3: float
    k_NH3: float
    NH3_coal_replacement: float
    CO2_reduction_per_combustion: float
    C_wind: float
    C_solar: float
    C_storage_op: float
    C_P2G_op: float
    C_P2A_op: float
    coal_price: float

    @property
    def n_vars(self) -> int:
        return self.N_thermal * self.T + 6 * self.T


@dataclass(slots=True)
class IntradayParams:
    E_storage_max: float
    P_charge_max: float
    P_discharge_max: float
    eta_charge: float
    eta_discharge: float
    SOC_min: float
    SOC_max: float
    dt: float = 0.25
    soc_track_gain: float = 0.05
    imbalance_deadband: float = 5.0


def validate_model_inputs(model: SystemModel) -> None:
    if model.T <= 0:
        raise ValueError("T must be positive")
    if model.N_thermal <= 0:
        raise ValueError("N_thermal must be positive")
    if model.P_wind_forecast.shape != (model.T,):
        raise ValueError("P_wind_forecast must have shape (T,)")
    if model.P_solar_forecast.shape != (model.T,):
        raise ValueError("P_solar_forecast must have shape (T,)")
    if model.P_load_forecast.shape != (model.T,):
        raise ValueError("P_load_forecast must have shape (T,)")
    if model.H2_load_forecast.shape != (model.T,):
        raise ValueError("H2_load_forecast must have shape (T,)")


def build_default_model(seed: int = 42) -> SystemModel:
    rng = np.random.default_rng(seed)
    T = 24
    time = np.arange(1, T + 1, dtype=float)

    P_wind_max = 150.0
    P_solar_max = 120.0
    P_load_max = 420.0

    P_wind_base = P_wind_max * (0.50 + 0.30 * np.sin(2 * np.pi * (time - 4) / 24))
    P_wind_random = P_wind_max * 0.10 * (rng.random(T) - 0.5)
    P_wind_forecast = np.clip(P_wind_base + P_wind_random, 0.0, P_wind_max)

    P_solar_forecast = np.zeros(T, dtype=float)
    for idx, t in enumerate(range(1, T + 1)):
        hour = t % 24
        if 6 <= hour <= 18:
            solar_shape = max(0.0, 1 - ((hour - 12) / 6) ** 2)
            P_solar_forecast[idx] = P_solar_max * solar_shape * (0.92 + 0.16 * rng.random())

    P_load_base = 0.62 * P_load_max
    P_load_forecast = np.zeros(T, dtype=float)
    for idx, t in enumerate(range(1, T + 1)):
        hour = t % 24
        if hour < 6:
            P_load_forecast[idx] = P_load_base * 0.78
        elif hour < 8:
            P_load_forecast[idx] = P_load_base * 0.92
        elif hour < 10:
            P_load_forecast[idx] = P_load_max * (0.88 + 0.07 * rng.random())
        elif hour < 18:
            P_load_forecast[idx] = P_load_base * (1.00 + 0.05 * rng.random())
        elif hour < 21:
            P_load_forecast[idx] = P_load_max * (0.92 + 0.06 * rng.random())
        else:
            P_load_forecast[idx] = P_load_base * (0.82 + 0.05 * rng.random())
    P_load_forecast *= 0.97 + 0.06 * rng.random(T)

    P_thermal_min = np.array([30.0, 20.0, 25.0], dtype=float)
    P_thermal_max = np.array([150.0, 100.0, 120.0], dtype=float)
    ramp_up = np.array([30.0, 25.0, 28.0], dtype=float)
    ramp_down = np.array([30.0, 25.0, 28.0], dtype=float)
    a_cost = np.array([0.00048, 0.00052, 0.00050], dtype=float)
    b_cost = np.array([16.19, 17.26, 16.60], dtype=float)
    c_cost = np.array([1000.0, 970.0, 950.0], dtype=float)
    carbon_thermal = np.array([950.0, 980.0, 960.0], dtype=float)

    E_storage_max = 200.0
    P_charge_max = 50.0
    P_discharge_max = 50.0
    eta_charge = 0.95
    eta_discharge = 0.95
    SOC_min = 0.10
    SOC_max = 0.90
    SOC_initial = 0.50

    P2G_min = 0.0
    P2G_max = 40.0
    P2G_efficiency = 0.65
    H2_conversion = 0.02
    P2G_carbon_reduction = 800.0
    H2_tank_min = 500.0
    H2_tank_max = 4500.0
    H2_loss_rate = 0.001

    P2A_min = 0.0
    P2A_max = 25.0
    P2A_efficiency = 0.85
    P2A_H2_input_max = 450.0
    NH3_production_max = 6000.0
    H2_to_NH3_ratio = 0.1765
    NH3_tank_min = 1000.0
    NH3_tank_max = 9000.0
    NH3_loss_rate = 0.0005
    r_NH3 = 0.10
    k_NH3 = 2.5
    NH3_coal_replacement = 0.6
    CO2_reduction_per_combustion = 2.2

    C_wind = 300.0
    C_solar = 400.0
    C_storage_op = 50.0
    C_P2G_op = 78.0
    C_P2A_op = 60.0
    coal_price = 780.0

    H2_load_forecast = np.full(T, 100.0, dtype=float)
    H2_tank_initial = 0.50 * (H2_tank_min + H2_tank_max)
    NH3_tank_initial = 0.50 * (NH3_tank_min + NH3_tank_max)

    model = SystemModel(
        T=T,
        N_thermal=3,
        P_wind_forecast=P_wind_forecast,
        P_solar_forecast=P_solar_forecast,
        P_load_forecast=P_load_forecast,
        H2_load_forecast=H2_load_forecast,
        P_thermal_min=P_thermal_min,
        P_thermal_max=P_thermal_max,
        ramp_up=ramp_up,
        ramp_down=ramp_down,
        a_cost=a_cost,
        b_cost=b_cost,
        c_cost=c_cost,
        carbon_thermal=carbon_thermal,
        E_storage_max=E_storage_max,
        P_charge_max=P_charge_max,
        P_discharge_max=P_discharge_max,
        eta_charge=eta_charge,
        eta_discharge=eta_discharge,
        SOC_min=SOC_min,
        SOC_max=SOC_max,
        SOC_min_abs=SOC_min * E_storage_max,
        SOC_max_abs=SOC_max * E_storage_max,
        SOC_initial=SOC_initial,
        SOC_target_final=SOC_initial * E_storage_max,
        P2G_min=P2G_min,
        P2G_max=P2G_max,
        P2G_efficiency=P2G_efficiency,
        H2_conversion=H2_conversion,
        P2G_carbon_reduction=P2G_carbon_reduction,
        H2_tank_min=H2_tank_min,
        H2_tank_max=H2_tank_max,
        H2_tank_initial=H2_tank_initial,
        H2_loss_rate=H2_loss_rate,
        P2A_min=P2A_min,
        P2A_max=P2A_max,
        P2A_efficiency=P2A_efficiency,
        P2A_H2_input_max=P2A_H2_input_max,
        NH3_production_max=NH3_production_max,
        H2_to_NH3_ratio=H2_to_NH3_ratio,
        NH3_tank_min=NH3_tank_min,
        NH3_tank_max=NH3_tank_max,
        NH3_tank_initial=NH3_tank_initial,
        NH3_loss_rate=NH3_loss_rate,
        r_NH3=r_NH3,
        k_NH3=k_NH3,
        NH3_coal_replacement=NH3_coal_replacement,
        CO2_reduction_per_combustion=CO2_reduction_per_combustion,
        C_wind=C_wind,
        C_solar=C_solar,
        C_storage_op=C_storage_op,
        C_P2G_op=C_P2G_op,
        C_P2A_op=C_P2A_op,
        coal_price=coal_price,
    )
    validate_model_inputs(model)
    return model


def model_to_dict(model: SystemModel) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in model.__dict__.items():
        result[key] = value.tolist() if isinstance(value, np.ndarray) else value
    return result
