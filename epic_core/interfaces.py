"""Core interfaces for EPIC."""

from __future__ import annotations

import inspect
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from epic_core.quantities import PhysicalQuantity


class SimulationState(ABC):
    @abstractmethod
    def get_quantity(self, quantity: PhysicalQuantity) -> float | None:
        """
        Return the current value for a physical quantity.
        Return None if this state does not model the requested quantity.
        """
        pass


class FaultDescriptor(ABC):
    """
    Lightweight descriptor for a fault supported by a digital twin.
    Used only for API listing and contest validation.
    The twin manages all fault activation and application internally.
    """

    @property
    @abstractmethod
    def fault_id(self) -> str:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def metadata(self) -> dict:
        """
        Return fault metadata. Must include at minimum:
            {"fault_id": str, "name": str, "description": str}
        """
        pass


class DigitalTwin(ABC):
    @property
    @abstractmethod
    def twin_id(self) -> str:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def configure(
        self,
        initial_conditions: dict | None,
        fault_schedule: list[dict],
    ) -> SimulationState:
        """
        Called once by the engine before the simulation loop begins.

        The twin must:
        - Store the fault_schedule internally.
        - Build and return the initial SimulationState, applying
          initial_conditions overrides (if any) to its defaults.
        """
        pass

    @abstractmethod
    def step(self, state: SimulationState, dt: float) -> SimulationState:
        """
        Advance the simulation by one time step dt (seconds).

        The twin is responsible for fault scheduling and application.
        """
        pass

    @abstractmethod
    def get_active_faults(self) -> list[dict]:
        """
        Return the currently active faults for label generation only.

        Return format: [{"fault_id": str, "severity": float}, ...]
        """
        pass

    @abstractmethod
    def supported_quantities(self) -> set[PhysicalQuantity]:
        """Return the physical quantities this twin's state can provide."""
        pass

    @abstractmethod
    def get_faults(self) -> list[FaultDescriptor]:
        """Return descriptors for all faults this twin supports."""
        pass

    @abstractmethod
    def metadata(self) -> dict:
        """
        Return twin metadata. Must include at minimum:
            {"twin_id": str, "name": str, "version": str, "description": str}
        """
        pass


class Sensor(ABC):
    @property
    @abstractmethod
    def sensor_id(self) -> str:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def unit(self) -> str:
        pass

    @property
    @abstractmethod
    def measured_quantity(self) -> PhysicalQuantity:
        pass

    @abstractmethod
    def observe(self, state: SimulationState, dt: float = 0.0) -> float:
        pass

    @abstractmethod
    def metadata(self) -> dict:
        pass

    def configure(
        self, overrides: dict, rng: random.Random | None = None
    ) -> "Sensor":
        """
        Return a fresh, independent sensor instance configured for one
        simulation session.

        This is the formal configuration contract: the engine never calls
        a sensor constructor directly, it calls configure() on the
        registered prototype. The default implementation reconstructs the
        sensor through its own class, passing the overrides as constructor
        keyword arguments and injecting the per-session rng when the
        constructor declares an 'rng' parameter. Implementations with a
        different configuration mechanism may override this method.

        The returned instance must be independent of the prototype and of
        any other session (own drift state, buffers, RNG).
        """
        sensor_class = type(self)
        kwargs = {key: value for key, value in overrides.items() if key != "rng"}
        if rng is not None:
            try:
                parameters = inspect.signature(sensor_class.__init__).parameters
            except (TypeError, ValueError):
                parameters = {}
            if "rng" in parameters:
                kwargs["rng"] = rng
        return sensor_class(**kwargs)


class ScoringMetric(ABC):
    @property
    @abstractmethod
    def metric_id(self) -> str:
        pass

    @property
    @abstractmethod
    def direction(self) -> str:
        """Return 'minimize' or 'maximize'."""
        pass

    @abstractmethod
    def compute(self, y_true, y_pred) -> float:
        pass

    @abstractmethod
    def metadata(self) -> dict:
        pass


@dataclass
class MetricScore:
    """A single metric result produced by a TaskEvaluator."""

    metric_id: str
    value: float
    details: dict | None = None


@dataclass
class EvaluationResult:
    """The outcome of evaluating one submission.

    ranking_value / ranking_direction feed the leaderboard. A None
    ranking_value means the submission produces no leaderboard entry.
    """

    scores: list[MetricScore] = field(default_factory=list)
    ranking_value: float | None = None
    ranking_direction: str = "minimize"  # "minimize" | "maximize"


class TaskEvaluator(ABC):
    """
    Scoring policy for one task type (plugin).

    The evaluator is a pure function from a submission payload, the task
    configuration, the recorded evaluation-window observations, and the
    configured metrics to an EvaluationResult. It must not access the
    database, the registries, or any other platform service — the caller
    provides everything it needs. This keeps task types domain-independent
    and lets new contest types be added without modifying EPIC Core or the
    API layer.
    """

    @property
    @abstractmethod
    def task_type(self) -> str:
        """Unique task type identifier, e.g. 'FORECASTING'."""
        pass

    @property
    def default_metric_ids(self) -> list[str]:
        """Metrics to use when the task does not configure any."""
        return []

    def observation_limit(self, configuration: dict) -> int | None:
        """
        Return how many evaluation-window observations evaluate() needs
        (counted from the start of the window), or None for all of them.
        The caller uses this to bound the database query; evaluators that
        can declare a limit should, so scoring stays O(eval window) rather
        than O(whole contest).
        """
        return None

    @abstractmethod
    def evaluate(
        self,
        payload: dict,
        configuration: dict,
        observations: list[dict],
        metrics: list[ScoringMetric],
    ) -> EvaluationResult:
        """
        Score one submission.

        observations are plain dicts ordered by sequence_id:
            {"sequence_id": int, "sensors": dict, "ground_truth": dict | None,
             "labels": dict | None}

        Raises SubmissionError if the payload or configuration is invalid.
        Raises EvaluationPendingError if the evaluation window is not yet
        fully populated and scoring must be retried later.
        """
        pass

    @abstractmethod
    def metadata(self) -> dict:
        """
        Return evaluator metadata. Must include at minimum:
            {"task_type": str, "name": str, "version": str, "description": str}
        """
        pass
