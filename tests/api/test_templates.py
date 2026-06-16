from epic_core.api.templates import TEMPLATES


def test_list_templates_returns_all_templates(client):
    response = client.get("/api/v1/templates")

    assert response.status_code == 200
    templates = response.json()["templates"]
    assert len(templates) == len(TEMPLATES)
    assert {template["twin_id"] for template in templates} == {
        "mass_spring_damper",
        "industrial_pump",
        "electric_motor",
        "rotating_machinery",
        "smart_building",
    }
    assert all("template_id" in template for template in templates)
    assert all(template["target_variables"] for template in templates)


def test_get_known_template_returns_full_configuration(client):
    response = client.get("/api/v1/templates/pump_bearing_fault")

    assert response.status_code == 200
    template = response.json()
    assert template["template_id"] == "pump_bearing_fault"
    assert template["twin_id"] == "industrial_pump"
    assert template["sensor_configs"]
    assert template["fault_schedule"]
    assert template["initial_conditions"]
    assert template["sampling_rate_hz"] > 0
    assert template["task_type"]
    assert template["target_variables"]


def test_get_unknown_template_returns_404(client):
    response = client.get("/api/v1/templates/unknown_template")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PLUGIN_NOT_FOUND"
