"""Contest template endpoints."""

from copy import deepcopy

from fastapi import APIRouter

from epic.api.schemas import TemplateDetail, TemplateListResponse
from epic.api.templates import TEMPLATES, template_summary
from epic.core.exceptions import PluginNotFoundError

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=TemplateListResponse)
def list_templates():
    return {"templates": [template_summary(template) for template in TEMPLATES]}


@router.get("/{template_id}", response_model=TemplateDetail)
def get_template(template_id: str):
    for template in TEMPLATES:
        if template["template_id"] == template_id:
            return deepcopy(template)
    raise PluginNotFoundError(f"template '{template_id}' is not registered")
