import pytest
from fastapi.testclient import TestClient

from epic_api.main import create_app
from epic_core.testing import test_registry_context
from epic_twins.mechanical.twin import MechanicalTwin


@pytest.fixture
def client():
    with test_registry_context(twins=[MechanicalTwin()]):
        test_client = TestClient(create_app())
        try:
            yield test_client
        finally:
            test_client.close()

