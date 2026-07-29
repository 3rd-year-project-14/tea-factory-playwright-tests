import uuid

import pytest

# The service enforces one availability record per driver per day (POST fails with 400
# if one already exists for "today"), so each test uses its own throwaway driver row
# rather than sharing driver_id=1 with other tests/runs.


@pytest.fixture
def fresh_driver(db_conn):
    unique = uuid.uuid4().hex[:8]
    cur = db_conn.cursor()
    cur.execute(
        "INSERT INTO driver (factory_id, driver_type, is_active) VALUES (1, 'PW_TEST', true) RETURNING driver_id"
    )
    driver_id = cur.fetchone()[0]
    cur.close()

    yield driver_id

    cur = db_conn.cursor()
    cur.execute("DELETE FROM driver_availability WHERE driver_id = %s", (driver_id,))
    cur.execute("DELETE FROM driver WHERE driver_id = %s", (driver_id,))
    cur.close()


def test_set_driver_availability(api_context, fresh_driver):
    response = api_context.post(
        "/api/driver-availability", data={"driverId": fresh_driver, "isAvailable": True, "reason": "On duty"}
    )

    assert response.status == 200
    body = response.json()
    assert body["driverId"] == fresh_driver
    assert body["isAvailable"] is True
    assert body["date"] is not None


def test_setting_availability_twice_in_one_day_fails(api_context, fresh_driver):
    first = api_context.post(
        "/api/driver-availability", data={"driverId": fresh_driver, "isAvailable": True, "reason": "On duty"}
    )
    assert first.status == 200

    second = api_context.post(
        "/api/driver-availability", data={"driverId": fresh_driver, "isAvailable": False, "reason": "Retry"}
    )
    assert second.status == 400


def test_get_driver_availability_history(api_context, fresh_driver):
    api_context.post(
        "/api/driver-availability", data={"driverId": fresh_driver, "isAvailable": True, "reason": "On duty"}
    )

    response = api_context.get(f"/api/driver-availability/{fresh_driver}")

    assert response.status == 200
    assert len(response.json()) == 1


def test_get_driver_availability_today(api_context, fresh_driver):
    api_context.post(
        "/api/driver-availability", data={"driverId": fresh_driver, "isAvailable": False, "reason": "On leave"}
    )

    response = api_context.get(f"/api/driver-availability/today/{fresh_driver}")

    assert response.status == 200
    assert response.json()["driverId"] == fresh_driver


def test_get_driver_availability_today_for_unknown_driver(api_context):
    response = api_context.get("/api/driver-availability/today/999999")

    assert response.status == 404
