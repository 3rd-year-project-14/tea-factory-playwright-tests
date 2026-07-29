import pytest

pytestmark = pytest.mark.api

def test_create_trip_for_driver_and_route(api_context):
    response = api_context.post("/api/trips", data={"driverId": 1, "routeId": 1})

    assert response.status == 200
    body = response.json()
    assert body["driverId"] == 1
    assert body["routeId"] == 1
    assert body["status"] == "pending"
    assert body["tripDate"] is not None


def test_get_trip_by_id(api_context):
    create_response = api_context.post("/api/trips", data={"driverId": 1, "routeId": 1})
    trip_id = create_response.json()["tripId"]

    response = api_context.get(f"/api/trips/{trip_id}")

    assert response.status == 200
    assert response.json()["tripId"] == trip_id


def test_get_trip_not_found(api_context):
    response = api_context.get("/api/trips/999999")

    assert response.status == 404


def test_create_trip_with_nonexistent_driver_fails(api_context):
    response = api_context.post("/api/trips", data={"driverId": 999999, "routeId": 1})

    assert response.status == 500


def test_create_trip_with_nonexistent_route_fails(api_context):
    response = api_context.post("/api/trips", data={"driverId": 1, "routeId": 999999})

    assert response.status == 500


def test_update_trip_status_to_completed(api_context):
    create_response = api_context.post("/api/trips", data={"driverId": 1, "routeId": 1})
    trip_id = create_response.json()["tripId"]

    response = api_context.put(f"/api/trips/{trip_id}/status", data={"status": "completed"})

    assert response.status == 200
    assert response.json()["status"] == "completed"
