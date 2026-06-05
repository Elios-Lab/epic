"""Contest template endpoints."""

from copy import deepcopy

from fastapi import APIRouter

from epic_api.templates import TEMPLATES, template_summary
from epic_core.exceptions import PluginNotFoundError

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("")
def list_templates():
    return {"templates": [template_summary(template) for template in TEMPLATES]}


@router.get("/{template_id}")
def get_template(template_id: str):
    for template in TEMPLATES:
        if template["template_id"] == template_id:
            return deepcopy(template)
    raise PluginNotFoundError(f"template '{template_id}' is not registered")
