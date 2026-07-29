import uuid

import pytest

pytestmark = pytest.mark.api


def test_create_route(api_context):
    route_code = f"PW-{uuid.uuid4().hex[:8]}"

    response = api_context.post(
        "/api/routes",
        data={
            "name": "Playwright Test Route",
            "startLocation": "Kandy",
            "endLocation": "Galle",
            "factoryId": 1,
            "routeCode": route_code,
        },
    )

    assert response.status == 200
    body = response.json()
    assert body["routeCode"] == route_code
    assert body["factory"]["factoryId"] == 1
    assert body["routeId"] is not None


def test_get_routes_by_factory(api_context):
    response = api_context.get("/api/routes/factory/1")

    assert response.status == 200
    assert isinstance(response.json(), list)


def test_create_route_with_duplicate_route_code_fails(api_context):
    route_code = f"PW-DUP-{uuid.uuid4().hex[:8]}"
    payload = {
        "name": "Duplicate Route",
        "startLocation": "A",
        "endLocation": "B",
        "factoryId": 1,
        "routeCode": route_code,
    }

    first = api_context.post("/api/routes", data=payload)
    assert first.status == 200

    second = api_context.post("/api/routes", data=payload)
    assert second.status == 500
