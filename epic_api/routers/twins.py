"""Digital twin metadata endpoints."""

from fastapi import APIRouter

import epic_core.registry as registry_module
from epic_api.schemas import (
    TwinFaultsResponse,
    TwinListResponse,
    TwinMetadata,
    TwinSensorsResponse,
)

router = APIRouter(prefix="/twins", tags=["twins"])


@router.get("", response_model=TwinListResponse)
def list_twins():
    return {"twins": [twin.metadata() for twin in registry_module.twin_registry.list()]}


@router.get("/{twin_id}", response_model=TwinMetadata)
def get_twin(twin_id: str):
    return registry_module.twin_registry.get(twin_id).metadata()


@router.get("/{twin_id}/sensors", response_model=TwinSensorsResponse)
def list_twin_sensors(twin_id: str):
    twin = registry_module.twin_registry.get(twin_id)
    supported_quantities = twin.supported_quantities()
    return {
        "twin_id": twin_id,
        "sensors": [
            sensor.metadata()
            for sensor in registry_module.sensor_registry.list()
            if sensor.measured_quantity in supported_quantities
        ],
    }


@router.get("/{twin_id}/faults", response_model=TwinFaultsResponse)
def list_twin_faults(twin_id: str):
    twin = registry_module.twin_registry.get(twin_id)
    return {
        "twin_id": twin_id,
        "faults": [fault.metadata() for fault in twin.get_faults()],
    }
