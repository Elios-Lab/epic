"""Core interfaces for EPIC."""

from __future__ import annotations

from abc import ABC, abstractmethod

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
