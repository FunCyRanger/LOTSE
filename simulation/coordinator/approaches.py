from __future__ import annotations
from simulation.core.types import CoordSignal, AgentConfig
from typing import TYPE_CHECKING
from abc import ABC, abstractmethod
from collections import defaultdict

if TYPE_CHECKING:
    from simulation.agents.base import BaseAgent
    from simulation.core.types import Action


class FairnessStrategy(ABC):
    name: str = ""

    @abstractmethod
    def process_flex(self, agents: list, actions: list, demand_kw: float) -> list[CoordSignal]:
        ...

    @abstractmethod
    def process_load_shed(self, agents: list, actions: list, grid_utilization_pct: float) -> list[CoordSignal]:
        ...

    def reset(self):
        ...


class StrategyA_SelfSelection(FairnessStrategy):
    name = "A: Self-Selection"

    def process_flex(self, agents, actions, demand_kw):
        return [CoordSignal(flex_request_kw=demand_kw / len(agents))] * len(agents)

    def process_load_shed(self, agents, actions, grid_utilization_pct):
        if grid_utilization_pct >= 100:
            return [CoordSignal(load_shed=True, reduction_pct=20)] * len(agents)
        return [CoordSignal()] * len(agents)


class StrategyB_MinPrice(FairnessStrategy):
    name = "B: Minimum Price"

    def __init__(self):
        self.participation_score = defaultdict(float)

    def process_flex(self, agents, actions, demand_kw):
        offers = []
        for i, (agent, action) in enumerate(zip(agents, actions)):
            flex = agent.compute_flexibility(action)
            if flex > 0.1:
                min_price = self._get_min_price(agent, action)
                offers.append((i, flex, min_price))

        offers.sort(key=lambda x: x[2])
        signals = [CoordSignal()] * len(agents)
        remaining = demand_kw
        for idx, flex, price in offers:
            if remaining <= 0:
                break
            take = min(flex, remaining)
            signals[idx] = CoordSignal(flex_request_kw=take)
            remaining -= take
            self.participation_score[idx] += take
        return signals

    def process_load_shed(self, agents, actions, grid_utilization_pct):
        if grid_utilization_pct >= 100:
            return [CoordSignal(load_shed=True, reduction_pct=20)] * len(agents)
        return [CoordSignal()] * len(agents)

    def _get_min_price(self, agent, action) -> float:
        ht = agent.config.household_type
        if ht == "T2":
            return agent.config.eeg_rate_ct
        return 3.0

    def reset(self):
        self.participation_score.clear()


class StrategyC_Rotation(FairnessStrategy):
    name = "C: Participation Tracking + Rotation"

    def __init__(self):
        self.scores = defaultdict(float)

    def process_flex(self, agents, actions, demand_kw):
        eligible = [(i, agent.compute_flexibility(actions[i]))
                     for i, agent in enumerate(agents)]
        eligible = [(i, f) for i, f in eligible if f > 0.1]
        eligible.sort(key=lambda x: self.scores[x[0]])

        signals = [CoordSignal()] * len(agents)
        remaining = demand_kw
        for idx, flex in eligible:
            if remaining <= 0:
                break
            take = min(flex, remaining)
            signals[idx] = CoordSignal(flex_request_kw=take)
            remaining -= take
            self.scores[idx] += take
        return signals

    def process_load_shed(self, agents, actions, grid_utilization_pct):
        if grid_utilization_pct >= 100:
            return [CoordSignal(load_shed=True, reduction_pct=20)] * len(agents)
        return [CoordSignal()] * len(agents)

    def reset(self):
        self.scores.clear()


class StrategyD_Proportional(FairnessStrategy):
    name = "D: Proportional Load Sharing"

    def process_flex(self, agents, actions, demand_kw):
        flexibilities = [agent.compute_flexibility(actions[i])
                         for i, agent in enumerate(agents)]
        total = sum(flexibilities)
        signals = [CoordSignal()] * len(agents)
        if total <= 0:
            return signals
        for i, f in enumerate(flexibilities):
            share = f / total * demand_kw
            signals[i] = CoordSignal(flex_request_kw=share)
        return signals

    def process_load_shed(self, agents, actions, grid_utilization_pct):
        if grid_utilization_pct >= 100:
            return [CoordSignal(load_shed=True,
                                reduction_pct=min(100, int(grid_utilization_pct - 90)))] * len(agents)
        return [CoordSignal()] * len(agents)


class StrategyE_MeritBudget(FairnessStrategy):
    name = "E: Merit Order + Budget"

    def __init__(self, budget_period_days: int = 30, max_budget_kwh: float = 50.0):
        self.budget = defaultdict(float)
        self.budget_period = budget_period_days
        self.max_budget = max_budget_kwh
        self.day = 0

    def process_flex(self, agents, actions, demand_kw):
        if self.day % self.budget_period == 0:
            self.budget.clear()

        offers = []
        for i, (agent, action) in enumerate(zip(agents, actions)):
            flex = agent.compute_flexibility(action)
            if flex > 0.1 and self.budget[i] < self.max_budget:
                offers.append((i, flex, self._get_cost(agent)))

        offers.sort(key=lambda x: x[2])
        signals = [CoordSignal()] * len(agents)
        remaining = demand_kw
        for idx, flex, _ in offers:
            if remaining <= 0:
                break
            take = min(flex, remaining, self.max_budget - self.budget[idx])
            if take > 0:
                signals[idx] = CoordSignal(flex_request_kw=take)
                remaining -= take
                self.budget[idx] += take
        return signals

    def process_load_shed(self, agents, actions, grid_utilization_pct):
        if grid_utilization_pct >= 100:
            return [CoordSignal(load_shed=True, reduction_pct=20)] * len(agents)
        return [CoordSignal()] * len(agents)

    def _get_cost(self, agent):
        ht = agent.config.household_type
        if ht == "T2":
            return agent.config.eeg_rate_ct
        return 3.0

    def reset(self):
        self.budget.clear()
        self.day = 0


class StrategyF_PriorityAccess(FairnessStrategy):
    name = "F: Priority Access for Contributors"

    def __init__(self, history_days: int = 14):
        self.contributions = defaultdict(float)
        self.history_days = history_days
        self.day = 0

    def process_flex(self, agents, actions, demand_kw):
        sorted_idxs = sorted(
            range(len(agents)),
            key=lambda i: -self.contributions[i]
        )
        signals = [CoordSignal()] * len(agents)
        remaining = demand_kw
        for idx in sorted_idxs:
            if remaining <= 0:
                break
            flex = agents[idx].compute_flexibility(actions[idx])
            if flex > 0.1:
                take = min(flex, remaining)
                signals[idx] = CoordSignal(flex_request_kw=take)
                remaining -= take
                self.contributions[idx] += take
        return signals

    def process_load_shed(self, agents, actions, grid_utilization_pct):
        if grid_utilization_pct >= 100:
            signals = [CoordSignal(load_shed=True, reduction_pct=20)] * len(agents)
            for i, agent in enumerate(agents):
                flex = agent.compute_flexibility(actions[i])
                if flex > 0:
                    self.contributions[i] += flex * 0.5
            return signals
        return [CoordSignal()] * len(agents)

    def reset(self):
        self.contributions.clear()
        self.day = 0


class StrategyG_Narrow(FairnessStrategy):
    name = "G: Narrow (Symmetric)"

    def __init__(self):
        self.last_idx = 0

    def process_flex(self, agents, actions, demand_kw):
        signals = [CoordSignal()] * len(agents)
        n = len(agents)
        for _ in range(min(n, int(demand_kw / 0.5))):
            idx = self.last_idx % n
            flex = agents[idx].compute_flexibility(actions[idx])
            if flex > 0.1:
                signals[idx] = CoordSignal(flex_request_kw=min(flex, demand_kw / n))
            self.last_idx += 1
        return signals

    def process_load_shed(self, agents, actions, grid_utilization_pct):
        if grid_utilization_pct >= 100:
            return [CoordSignal(load_shed=True, reduction_pct=20)] * len(agents)
        return [CoordSignal()] * len(agents)

    def reset(self):
        self.last_idx = 0


class StrategyH_Emergency(FairnessStrategy):
    name = "H: Emergency-Only + Self-Selection"

    def process_flex(self, agents, actions, demand_kw):
        return [CoordSignal(flex_request_kw=demand_kw / len(agents))] * len(agents)

    def process_load_shed(self, agents, actions, grid_utilization_pct):
        if grid_utilization_pct >= 100:
            flexibilities = [agents[i].compute_flexibility(actions[i])
                             for i in range(len(agents))]
            total = sum(flexibilities)
            signals = [CoordSignal(load_shed=True)] * len(agents)
            if total > 0:
                for i, f in enumerate(flexibilities):
                    signals[i].reduction_pct = int(f / total * 100)
            return signals
        return [CoordSignal()] * len(agents)


class StrategyI_HybridB_C(FairnessStrategy):
    name = "I: Hybrid (Min Price + Rotation Budget)"

    def __init__(self, budget_cap: float = 30.0):
        self.budget = defaultdict(float)
        self.budget_cap = budget_cap

    def process_flex(self, agents, actions, demand_kw):
        offers = []
        for i, (agent, action) in enumerate(zip(agents, actions)):
            flex = agent.compute_flexibility(action)
            if flex > 0.1 and self.budget[i] < self.budget_cap:
                price = self._get_min_price(agent, actions[i])
                offers.append((i, flex, price, self.budget[i]))

        offers.sort(key=lambda x: (x[2], x[3]))
        signals = [CoordSignal()] * len(agents)
        remaining = demand_kw
        for idx, flex, price, used in offers:
            if remaining <= 0:
                break
            remaining_budget = self.budget_cap - used
            take = min(flex, remaining, remaining_budget)
            if take > 0:
                signals[idx] = CoordSignal(flex_request_kw=take)
                remaining -= take
                self.budget[idx] += take
        return signals

    def process_load_shed(self, agents, actions, grid_utilization_pct):
        if grid_utilization_pct >= 100:
            return [CoordSignal(load_shed=True, reduction_pct=20)] * len(agents)
        return [CoordSignal()] * len(agents)

    def _get_min_price(self, agent, action) -> float:
        ht = agent.config.household_type
        if ht == "T2":
            return agent.config.eeg_rate_ct
        return 2.0

    def reset(self):
        self.budget.clear()


def create_strategy(approach: str, config: dict) -> FairnessStrategy:
    mapping = {
        "A": StrategyA_SelfSelection,
        "B": StrategyB_MinPrice,
        "C": StrategyC_Rotation,
        "D": StrategyD_Proportional,
        "E": StrategyE_MeritBudget,
        "F": StrategyF_PriorityAccess,
        "G": StrategyG_Narrow,
        "H": StrategyH_Emergency,
        "I": StrategyI_HybridB_C,
    }
    cls = mapping.get(approach.upper())
    if cls is None:
        raise ValueError(f"Unknown approach: {approach}. Use A-I.")
    return cls()
