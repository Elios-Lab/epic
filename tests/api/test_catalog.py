def test_catalog_list_returns_all_registered_twins(client):
    response = client.get("/api/v1/catalog")

    assert response.status_code == 200
    twins = response.json()["twins"]
    assert {twin["twin_id"] for twin in twins} == {
        "mass_spring_damper",
        "industrial_pump",
        "electric_motor",
        "rotating_machinery",
        "smart_building",
    }
    assert all(twin["name"] for twin in twins)
    assert all(twin["description"] for twin in twins)
    assert all(twin["version"] for twin in twins)


def test_catalog_profile_for_known_twin_returns_rich_documentation(client):
    response = client.get("/api/v1/catalog/industrial_pump")

    assert response.status_code == 200
    profile = response.json()
    assert profile["metadata"]["twin_id"] == "industrial_pump"
    assert "flow_rate" in profile["supported_quantities"]
    assert profile["faults"]
    assert all("fault_id" in fault for fault in profile["faults"])
    assert profile["sensors"]
    assert all("sensor_id" in sensor for sensor in profile["sensors"])
    assert profile["templates"]
    assert all(template["twin_id"] == "industrial_pump" for template in profile["templates"])


def test_catalog_profile_for_unknown_twin_returns_404(client):
    response = client.get("/api/v1/catalog/unknown_twin")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PLUGIN_NOT_FOUND"


def test_catalog_profile_includes_initial_conditions_schema(client):
    response = client.get("/api/v1/catalog/mass_spring_damper")

    assert response.status_code == 200
    profile = response.json()
    schema = profile["initial_conditions_schema"]
    assert isinstance(schema, list)
    assert len(schema) > 0
    required_fields = {"key", "default", "unit", "kind"}
    for field in schema:
        assert required_fields <= field.keys(), f"field missing keys: {field}"
        assert field["kind"] in ("state", "parameter")
        assert isinstance(field["default"], (int, float))


def test_initial_conditions_schema_covers_states_and_parameters(client):
    response = client.get("/api/v1/catalog/mass_spring_damper")

    schema = response.json()["initial_conditions_schema"]
    kinds = {entry["kind"] for entry in schema}
    assert "state" in kinds
    assert "parameter" in kinds


def test_all_twins_expose_initial_conditions_schema(client):
    twins_response = client.get("/api/v1/catalog")
    twin_ids = [t["twin_id"] for t in twins_response.json()["twins"]]

    for twin_id in twin_ids:
        profile = client.get(f"/api/v1/catalog/{twin_id}").json()
        assert "initial_conditions_schema" in profile, f"missing schema for {twin_id}"
        assert isinstance(profile["initial_conditions_schema"], list)
