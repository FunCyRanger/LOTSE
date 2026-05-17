from simulation.core.types import AgentConfig, AgentState, Action, TimestepData
from abc import ABC, abstractmethod


class BaseAgent(ABC):
    def __init__(self, config: AgentConfig):
        self.config = config
        self.state = AgentState()

    @abstractmethod
    def baseline_action(self, timestep_data) -> Action:
        ...

    @abstractmethod
    def coordination_action(self, timestep_data, signal) -> Action:
        ...

    def compute_flexibility(self, action: Action) -> float:
        limit_import_w = self.config.grid_limit_w
        current_import_w = max(0, action.net_grid_kw * 1000)
        headroom = max(0, limit_import_w - current_import_w)
        return headroom / 1000

    def reset(self):
        self.state = AgentState()
