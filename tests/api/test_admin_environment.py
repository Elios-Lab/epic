def test_admin_can_read_environment_without_secret_values(client, admin_headers, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "DATABASE_URL=sqlite+aiosqlite:///existing.db\n"
        "SECRET_KEY=existing-secret\n"
        "SMTP_PASSWORD=existing-smtp-secret\n",
        encoding="utf-8",
    )
    client.app.state.env_file_path = env_path

    response = client.get("/api/v1/admin/environment", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["env_file"] == str(env_path)
    variables = {item["key"]: item for item in body["variables"]}
    assert variables["DATABASE_URL"]["value"] is None
    assert variables["DATABASE_URL"]["is_secret"] is True
    assert variables["DATABASE_URL"]["is_set"] is True
    assert variables["SECRET_KEY"]["value"] is None
    assert variables["SECRET_KEY"]["is_set"] is True
    assert variables["SMTP_PASSWORD"]["value"] is None
    assert variables["SMTP_PASSWORD"]["is_set"] is True
    assert variables["BASE_URL"]["value"] == "http://testserver"


def test_non_admin_cannot_read_or_update_environment(client, auth_headers, tmp_path):
    client.app.state.env_file_path = tmp_path / ".env"

    read_response = client.get("/api/v1/admin/environment", headers=auth_headers)
    update_response = client.put(
        "/api/v1/admin/environment",
        json={"values": {"BASE_URL": "https://example.test"}},
        headers=auth_headers,
    )

    assert read_response.status_code == 403
    assert update_response.status_code == 403


def test_admin_can_update_known_environment_variables(client, admin_headers, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "# keep this comment\n"
        "CUSTOM_FLAG=preserve-me\n"
        "DATABASE_URL=sqlite+aiosqlite:///existing.db\n"
        "SECRET_KEY=existing-secret\n",
        encoding="utf-8",
    )
    client.app.state.env_file_path = env_path

    response = client.put(
        "/api/v1/admin/environment",
        json={
            "values": {
                "BASE_URL": "https://epic.example.test",
                "SMTP_HOST": "smtp.example.test",
                "SMTP_PASSWORD": "new smtp password",
                "DEBUG": "true",
            }
        },
        headers=admin_headers,
    )

    assert response.status_code == 200, response.json()
    written = env_path.read_text(encoding="utf-8")
    assert "# keep this comment" in written
    assert "CUSTOM_FLAG=preserve-me" in written
    assert "BASE_URL=https://epic.example.test" in written
    assert "SMTP_HOST=smtp.example.test" in written
    assert 'SMTP_PASSWORD="new smtp password"' in written
    assert "DEBUG=true" in written
    assert "SECRET_KEY=existing-secret" in written


def test_admin_environment_rejects_unknown_variables(client, admin_headers, tmp_path):
    client.app.state.env_file_path = tmp_path / ".env"

    response = client.put(
        "/api/v1/admin/environment",
        json={"values": {"NOT_A_SETTING": "value"}},
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_admin_environment_rejects_invalid_typed_values(client, admin_headers, tmp_path):
    client.app.state.env_file_path = tmp_path / ".env"

    response = client.put(
        "/api/v1/admin/environment",
        json={"values": {"PORT": "not-a-number"}},
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
