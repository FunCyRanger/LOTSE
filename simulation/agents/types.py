from simulation.agents.base import BaseAgent
from simulation.core.types import AgentConfig, Action, CoordSignal, TimestepData
import numpy as np


class T1_NoPV(BaseAgent):
    def baseline_action(self, td: TimestepData) -> Action:
        return Action(net_grid_kw=td.load_w / 1000)

    def coordination_action(self, td: TimestepData, signal: CoordSignal) -> Action:
        return Action(net_grid_kw=td.load_w / 1000)


class T2_PV_EEG(BaseAgent):
    def baseline_action(self, td: TimestepData) -> Action:
        net_w = td.load_w - td.pv_w
        return Action(net_grid_kw=net_w / 1000, pv_kw=td.pv_w / 1000)

    def coordination_action(self, td: TimestepData, signal: CoordSignal) -> Action:
        net_w = td.load_w - td.pv_w
        action = Action(net_grid_kw=net_w / 1000, pv_kw=td.pv_w / 1000)
        if signal.load_shed and td.pv_w > td.load_w and net_w < 0:
            curtail = min(td.pv_w - td.load_w, signal.flex_request_kw * 1000) if signal.flex_request_kw > 0 else 0
            if signal.reduction_pct > 0:
                curtail = max(curtail, td.pv_w * signal.reduction_pct / 100)
            action.curtailment_kw = curtail / 1000
            action.net_grid_kw = (td.load_w - (td.pv_w - curtail)) / 1000
            action.shed_kw = curtail / 1000
        return action


class T3_PV_Dynamic(BaseAgent):
    def baseline_action(self, td: TimestepData) -> Action:
        net_w = td.load_w - td.pv_w
        return Action(net_grid_kw=net_w / 1000, pv_kw=td.pv_w / 1000)

    def coordination_action(self, td: TimestepData, signal: CoordSignal) -> Action:
        if td.price_ct < 0:
            curtail = td.pv_w
            return Action(net_grid_kw=td.load_w / 1000, pv_kw=0, curtailment_kw=curtail / 1000)
        net_w = td.load_w - td.pv_w
        action = Action(net_grid_kw=net_w / 1000, pv_kw=td.pv_w / 1000)
        if signal.load_shed and net_w < 0:
            curtail = min(-net_w, signal.flex_request_kw * 1000) if signal.flex_request_kw > 0 else 0
            if signal.reduction_pct > 0 and td.pv_w > 0:
                curtail = max(curtail, td.pv_w * signal.reduction_pct / 100)
            action.curtailment_kw = curtail / 1000
            action.net_grid_kw = (td.load_w - (td.pv_w - curtail)) / 1000
        return action


class T4_PV_Battery(BaseAgent):
    def _battery_dispatch(self, td: TimestepData, price_threshold: float = 10.0) -> tuple:
        soc = self.state.battery_soc
        cap_kwh = self.config.battery_kwh
        power_kw = self.config.battery_kw
        if soc < 0.2 and td.price_ct < 25:
            charge = min(power_kw, (0.9 - soc) * cap_kwh / td.dt_h)
            soc += charge * td.dt_h / cap_kwh * 0.9
            return charge, 0.0, soc
        elif soc > 0.8 and td.price_ct > price_threshold:
            discharge = min(power_kw, (soc - 0.2) * cap_kwh / td.dt_h)
            soc -= discharge * td.dt_h / cap_kwh / 0.9
            return 0.0, discharge, soc
        elif td.price_ct < 5 and soc < 0.95:
            charge = min(power_kw, (0.95 - soc) * cap_kwh / td.dt_h)
            soc += charge * td.dt_h / cap_kwh * 0.9
            return charge, 0.0, soc
        return 0.0, 0.0, soc

    def baseline_action(self, td: TimestepData) -> Action:
        charge_kw, discharge_kw, soc = self._battery_dispatch(td)
        net_w = td.load_w - td.pv_w + charge_kw * 1000 - discharge_kw * 1000
        self.state.battery_soc = soc
        return Action(
            net_grid_kw=net_w / 1000,
            pv_kw=td.pv_w / 1000,
            battery_charge_kw=charge_kw,
            battery_discharge_kw=discharge_kw,
        )

    def coordination_action(self, td: TimestepData, signal: CoordSignal) -> Action:
        base = self.baseline_action(td)
        if not signal.load_shed and signal.flex_request_kw <= 0:
            return base
        if signal.load_shed and self.state.battery_soc > 0.3:
            discharge = min(self.config.battery_kw,
                            (self.state.battery_soc - 0.1) * self.config.battery_kwh / td.dt_h)
            base.battery_discharge_kw = discharge
            base.battery_charge_kw = 0
            net_w = td.load_w - td.pv_w - discharge * 1000
            base.net_grid_kw = net_w / 1000
            base.shed_kw = discharge
            self.state.battery_soc -= discharge * td.dt_h / self.config.battery_kwh / 0.9
        return base


class T5_BatteryOnly(BaseAgent):
    def _arbitrage(self, td: TimestepData) -> tuple:
        soc = self.state.battery_soc
        cap_kwh = self.config.battery_kwh
        power_kw = self.config.battery_kw
        if soc > 0.8 and td.price_ct > 8:
            discharge = min(power_kw, (soc - 0.1) * cap_kwh / td.dt_h)
            soc -= discharge * td.dt_h / cap_kwh / 0.9
            return 0.0, discharge, soc
        elif td.price_ct < 6 and soc < 0.95:
            charge = min(power_kw, (0.95 - soc) * cap_kwh / td.dt_h)
            soc += charge * td.dt_h / cap_kwh * 0.9
            return charge, 0.0, soc
        return 0.0, 0.0, soc

    def baseline_action(self, td: TimestepData) -> Action:
        charge, discharge, soc = self._arbitrage(td)
        net_w = charge * 1000 - discharge * 1000
        self.state.battery_soc = soc
        return Action(
            net_grid_kw=net_w / 1000,
            battery_charge_kw=charge,
            battery_discharge_kw=discharge,
        )

    def coordination_action(self, td: TimestepData, signal: CoordSignal) -> Action:
        base = self.baseline_action(td)
        if signal.load_shed and self.state.battery_soc > 0.3:
            discharge = min(self.config.battery_kw,
                            (self.state.battery_soc - 0.1) * self.config.battery_kwh / td.dt_h)
            base.battery_charge_kw = 0
            base.battery_discharge_kw = discharge
            net_w = -discharge * 1000
            base.net_grid_kw = net_w / 1000
            base.shed_kw = discharge
            self.state.battery_soc -= discharge * td.dt_h / self.config.battery_kwh / 0.9
        return base


class T6_HeatPump(BaseAgent):
    def baseline_action(self, td: TimestepData) -> Action:
        temp = self.state.thermal_temp
        setpoint = 45.0
        loss = 0.1 * (temp - 20) * td.dt_h
        temp -= loss
        hp_kw = 0.0
        if temp < setpoint - 2 and not td.par14a_active:
            hp_kw = self.config.hp_kw
            temp += hp_kw * 3.5 * td.dt_h / self.config.hp_buffer_kwh
        elif td.price_ct < 3 and not td.par14a_active and temp < 55:
            hp_kw = self.config.hp_kw * 0.5
            temp += hp_kw * 3.5 * td.dt_h / self.config.hp_buffer_kwh
        self.state.thermal_temp = min(temp, 60)
        net_w = td.load_w + hp_kw * 1000
        return Action(net_grid_kw=net_w / 1000, hp_kw=hp_kw)

    def coordination_action(self, td: TimestepData, signal: CoordSignal) -> Action:
        base = self.baseline_action(td)
        if signal.load_shed and self.state.thermal_temp > 35 and base.hp_kw > 0:
            base.net_grid_kw = td.load_w / 1000
            base.shed_kw = base.hp_kw
            base.hp_kw = 0.0
        elif signal.flex_request_kw > 0 and not signal.load_shed and self.state.thermal_temp > 35:
            base.net_grid_kw = td.load_w / 1000
            base.shed_kw = base.hp_kw
            base.hp_kw = 0.0
        return base


class T7_EVWallbox(BaseAgent):
    def baseline_action(self, td: TimestepData) -> Action:
        hour = td.hour
        arrival = self.config.ev_arrival_hour
        departure = self.config.ev_departure_hour

        if departure > arrival:
            connected = (hour >= arrival) or (hour < departure)
        else:
            connected = (hour >= arrival) or (hour < departure)

        ev_kw = 0.0
        if connected and self.state.ev_soc < 0.9:
            cheapest_window = self._find_cheapest_window(td.price_ct, arrival, departure, hour)
            if cheapest_window:
                ev_kw = min(self.config.ev_kw, (0.9 - self.state.ev_soc) * self.config.ev_kwh / td.dt_h)
                soc_add = ev_kw * td.dt_h * 0.95 / self.config.ev_kwh
                self.state.ev_soc = min(0.9, self.state.ev_soc + soc_add)

        net_w = td.load_w + ev_kw * 1000
        return Action(net_grid_kw=net_w / 1000, ev_charge_kw=ev_kw)

    def coordination_action(self, td: TimestepData, signal: CoordSignal) -> Action:
        base = self.baseline_action(td)
        if signal.load_shed and base.ev_charge_kw > 0:
            base.net_grid_kw = td.load_w / 1000
            base.shed_kw = base.ev_charge_kw
            base.ev_charge_kw = 0.0
        return base

    def _find_cheapest_window(self, price, arrival, departure, current_hour):
        return True


class T8_Mixed(BaseAgent):
    def baseline_action(self, td: TimestepData) -> Action:
        hp = T6_HeatPump(AgentConfig(
            household_type="T6", hp_kw=self.config.hp_kw,
            hp_buffer_kwh=self.config.hp_buffer_kwh,
            annual_consumption_kwh=self.config.annual_consumption_kwh,
            grid_limit_w=self.config.grid_limit_w,
        ))
        hp.state = self.state
        hp_action = hp.baseline_action(td)
        self.state.thermal_temp = hp.state.thermal_temp

        ev = T7_EVWallbox(AgentConfig(
            household_type="T7", ev_kwh=self.config.ev_kwh, ev_kw=self.config.ev_kw,
            ev_arrival_hour=self.config.ev_arrival_hour,
            ev_departure_hour=self.config.ev_departure_hour,
            annual_consumption_kwh=0, grid_limit_w=self.config.grid_limit_w,
        ))
        ev.state.ev_soc = self.state.ev_soc
        ev_ld = td.load_w + hp_action.hp_kw * 1000
        ev_td = TimestepData(
            price_ct=td.price_ct, load_w=ev_ld, pv_w=td.pv_w,
            hour=td.hour, dayofyear=td.dayofyear, dt_h=td.dt_h,
            par14a_active=td.par14a_active,
        )
        ev_action = ev.baseline_action(ev_td)
        self.state.ev_soc = ev.state.ev_soc

        battery = T4_PV_Battery(AgentConfig(
            household_type="T4",
            pv_kwp=self.config.pv_kwp, battery_kwh=self.config.battery_kwh,
            battery_kw=self.config.battery_kw,
            annual_consumption_kwh=0, grid_limit_w=self.config.grid_limit_w,
        ))
        battery.state.battery_soc = self.state.battery_soc
        bat_ld = ev_ld + ev_action.ev_charge_kw * 1000
        bat_td = TimestepData(
            price_ct=td.price_ct, load_w=bat_ld, pv_w=td.pv_w,
            hour=td.hour, dayofyear=td.dayofyear, dt_h=td.dt_h,
        )
        bat_action = battery.baseline_action(bat_td)
        self.state.battery_soc = battery.state.battery_soc

        net_w = bat_ld - td.pv_w + bat_action.battery_charge_kw * 1000 - bat_action.battery_discharge_kw * 1000
        return Action(
            net_grid_kw=net_w / 1000,
            pv_kw=td.pv_w / 1000,
            battery_charge_kw=bat_action.battery_charge_kw,
            battery_discharge_kw=bat_action.battery_discharge_kw,
            ev_charge_kw=ev_action.ev_charge_kw,
            hp_kw=hp_action.hp_kw,
        )

    def coordination_action(self, td: TimestepData, signal: CoordSignal) -> Action:
        return self.baseline_action(td)


class T9_BalconySolar(BaseAgent):
    def baseline_action(self, td: TimestepData) -> Action:
        net_w = td.load_w - td.pv_w
        return Action(net_grid_kw=net_w / 1000, pv_kw=td.pv_w / 1000)

    def coordination_action(self, td: TimestepData, signal: CoordSignal) -> Action:
        return Action(net_grid_kw=td.load_w / 1000, pv_kw=td.pv_w / 1000)


class T10_BalconySolarBattery(BaseAgent):
    def baseline_action(self, td: TimestepData) -> Action:
        soc = self.state.battery_soc
        cap_kwh = self.config.battery_kwh
        power_kw = self.config.battery_kw
        charge, discharge = 0.0, 0.0
        if soc > 0.8 and td.price_ct > 8:
            discharge = min(power_kw, (soc - 0.1) * cap_kwh / td.dt_h)
            soc -= discharge * td.dt_h / cap_kwh / 0.9
        elif td.price_ct < 6 and soc < 0.95:
            charge = min(power_kw, (0.95 - soc) * cap_kwh / td.dt_h)
            soc += charge * td.dt_h / cap_kwh * 0.9
        self.state.battery_soc = soc
        net_w = td.load_w - td.pv_w + charge * 1000 - discharge * 1000
        return Action(
            net_grid_kw=net_w / 1000,
            pv_kw=td.pv_w / 1000,
            battery_charge_kw=charge,
            battery_discharge_kw=discharge,
        )

    def coordination_action(self, td: TimestepData, signal: CoordSignal) -> Action:
        return self.baseline_action(td)


def create_agent(config: AgentConfig) -> BaseAgent:
    mapping = {
        "T1": T1_NoPV,
        "T2": T2_PV_EEG,
        "T3": T3_PV_Dynamic,
        "T4": T4_PV_Battery,
        "T5": T5_BatteryOnly,
        "T6": T6_HeatPump,
        "T7": T7_EVWallbox,
        "T8": T8_Mixed,
        "T9": T9_BalconySolar,
        "T10": T10_BalconySolarBattery,
    }
    cls = mapping.get(config.household_type)
    if cls is None:
        raise ValueError(f"Unknown household type: {config.household_type}")
    return cls(config)
