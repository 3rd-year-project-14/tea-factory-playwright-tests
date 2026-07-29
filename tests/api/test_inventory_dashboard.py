import pytest

pytestmark = pytest.mark.api

def test_factory_dashboard_summary_shape(api_context):
    response = api_context.get("/api/inventory-process/1/dashboard-summary")

    assert response.status == 200
    body = response.json()
    for field in (
        "totalActiveRoutes",
        "totalBags",
        "totalGrossWeight",
        "totalSuppliers",
        "todaySuppliers",
        "estimatedTotalBags",
        "completedRoutes",
        "completedSuppliers",
    ):
        assert field in body


def test_inventory_summary_daily_view(api_context):
    response = api_context.get(
        "/api/factory-dashboard/inventory/1", params={"viewMode": "daily", "date": "2026-07-29"}
    )

    assert response.status == 200
    body = response.json()
    assert "totalGrossWeight" in body
    assert "totalNetWeight" in body
    assert "totalBags" in body


def test_inventory_summary_for_unknown_factory_returns_empty(api_context):
    response = api_context.get(
        "/api/factory-dashboard/inventory/999999", params={"viewMode": "daily", "date": "2026-07-29"}
    )

    assert response.status == 200
    body = response.json()
    assert body["totalBags"] == 0
