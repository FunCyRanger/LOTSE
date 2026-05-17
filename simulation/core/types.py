from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TimestepData:
    price_ct: float = 0.0
    load_w: float = 0.0
    pv_w: float = 0.0
    hour: int = 0
    dayofyear: int = 0
    dt_h: float = 0.25
    par14a_active: bool = False


@dataclass
class AgentConfig:
    household_type: str
    annual_consumption_kwh: float = 4000.0
    pv_kwp: float = 0.0
    battery_kwh: float = 0.0
    battery_kw: float = 0.0
    ev_kwh: float = 0.0
    ev_kw: float = 0.0
    ev_arrival_hour: int = 17
    ev_departure_hour: int = 8
    hp_kw: float = 0.0
    hp_buffer_kwh: float = 0.0
    grid_limit_w: float = 5000.0
    tariff_rate_ct: float = 30.0
    eeg_rate_ct: float = 8.2
    idx: int = 0


@dataclass
class AgentState:
    battery_soc: float = 0.5
    ev_soc: float = 0.5
    ev_connected: bool = False
    ev_departure_in: int = 0
    thermal_temp: float = 45.0
    cumulative_cost_baseline: float = 0.0
    cumulative_cost_coord: float = 0.0
    flex_offered_kwh: float = 0.0
    flex_accepted_kwh: float = 0.0
    load_shed_count: int = 0


@dataclass
class Action:
    net_grid_kw: float = 0.0
    pv_kw: float = 0.0
    curtailment_kw: float = 0.0
    battery_charge_kw: float = 0.0
    battery_discharge_kw: float = 0.0
    ev_charge_kw: float = 0.0
    hp_kw: float = 0.0
    flex_offered_kw: float = 0.0
    shed_kw: float = 0.0
    par14a_curtailed: bool = False

    def import_kwh(self, dt_h: float = 0.25) -> float:
        return max(0, self.net_grid_kw) * dt_h

    def export_kwh(self, dt_h: float = 0.25) -> float:
        return max(0, -self.net_grid_kw) * dt_h

    def cost_ct(self, price_ct: float, config: AgentConfig, dt_h: float = 0.25) -> float:
        ht = config.household_type
        if ht == "T1":
            return self.import_kwh(dt_h) * config.tariff_rate_ct
        elif ht == "T2":
            return self.import_kwh(dt_h) * config.tariff_rate_ct - self.export_kwh(dt_h) * config.eeg_rate_ct
        elif ht in ("T3", "T4", "T5", "T7", "T8", "T10"):
            return self.import_kwh(dt_h) * price_ct - self.export_kwh(dt_h) * price_ct
        elif ht == "T6":
            return self.import_kwh(dt_h) * price_ct
        elif ht == "T9":
            return self.import_kwh(dt_h) * config.tariff_rate_ct
        return self.import_kwh(dt_h) * config.tariff_rate_ct


@dataclass
class CoordSignal:
    flex_request_kw: float = 0.0
    load_shed: bool = False
    shed_priority: tuple = ("wallbox", "battery_charge", "heatpump")
    reduction_pct: int = 0
    price_signal_ct: Optional[float] = None


@dataclass
class SimulationResult:
    agent_results: list = field(default_factory=list)
    grid_results: list = field(default_factory=list)
    comms_results: list = field(default_factory=list)
    approach_name: str = ""
    config: Optional[dict] = None
    fairness_metrics: Optional[dict] = None
    grid_summary: Optional[dict] = None
    comms_summary: Optional[dict] = None
    per_agent: Optional[list] = None
