"""Catalog endpoints for registered digital twins."""

from fastapi import APIRouter

import epic_core.registry as registry_module
from epic_api.templates import TEMPLATES, template_summary

router = APIRouter(prefix="/catalog", tags=["catalog"])


def catalog_summary(twin) -> dict:
    metadata = twin.metadata()
    return {
        "twin_id": metadata["twin_id"],
        "name": metadata["name"],
        "description": metadata["description"],
        "version": metadata["version"],
    }


@router.get("")
def list_catalog():
    return {
        "twins": [
            catalog_summary(twin)
            for twin in registry_module.twin_registry.list()
        ]
    }


@router.get("/{twin_id}")
def get_catalog_profile(twin_id: str):
    twin = registry_module.twin_registry.get(twin_id)
    supported_quantities = twin.supported_quantities()
    return {
        "metadata": twin.metadata(),
        "supported_quantities": [
            quantity.value for quantity in sorted(
                supported_quantities, key=lambda item: item.value
            )
        ],
        "faults": [fault.metadata() for fault in twin.get_faults()],
        "sensors": [
            sensor.metadata()
            for sensor in registry_module.sensor_registry.list()
            if sensor.measured_quantity in supported_quantities
        ],
        "templates": [
            template_summary(template)
            for template in TEMPLATES
            if template["twin_id"] == twin_id
        ],
    }
