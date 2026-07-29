import pytest

pytestmark = pytest.mark.api


@pytest.mark.smoke
def test_backend_is_up(api_context):
    response = api_context.get("/api/manager-info/ping")

    assert response.status == 200
    assert response.text() == "pong"
