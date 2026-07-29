import uuid

import pytest

# This flow found a real gap: approving a supplier fertilizer request never touched
# FertilizerStock.quantity, so stock could be "issued" infinitely. Fixed in
# SupplierFertilizerRequestService.updateRequest -> issueStockForApprovedRequest():
# decrements stock on REQUESTED/PENDING -> APPROVED transitions, blocks the transition
# with a 400 if requested quantity exceeds available stock, and is idempotent (approving
# an already-APPROVED request does not decrement twice).


@pytest.fixture
def fertilizer_company_and_category(api_context):
    """No cleanup: FertilizerCompanyController's DELETE fails on the company_category
    link table, and categories have no delete endpoint at all -- leftover rows are
    harmless (company names are only checked for uniqueness, and we use uuid suffixes)."""
    unique = uuid.uuid4().hex[:8]
    response = api_context.post(
        "/api/fertilizer-companies",
        data={
            "name": f"PW Fert Co {unique}",
            "address": "Kandy",
            "contactPerson": "Test",
            "contactNumber": "0771234567",
            "email": f"pwfert-{unique}@test.com",
            "categories": [f"PW Category {unique}"],
        },
    )
    assert response.status == 200
    body = response.json()
    return body["id"]


@pytest.fixture
def fertilizer_stock(api_context, db_conn, fertilizer_company_and_category):
    cur = db_conn.cursor()
    cur.execute("SELECT id FROM fertilizer_category ORDER BY id DESC LIMIT 1")
    category_id = cur.fetchone()[0]
    cur.execute("SELECT id FROM users LIMIT 1")
    any_user_id = cur.fetchone()[0]
    cur.close()

    response = api_context.post(
        "/api/fertilizer-stocks",
        data={
            "userId": any_user_id,
            "categoryId": category_id,
            "companyId": fertilizer_company_and_category,
            "weightPerQuantity": 50,
            "purchasePrice": 100,
            "sellPrice": 120,
            "warehouse": "Main",
            "quantity": 10,
        },
    )
    assert response.status == 201
    stock_id = response.json()["id"]

    yield stock_id

    api_context.delete(f"/api/fertilizer-stocks/{stock_id}")


@pytest.fixture
def fert_supplier(db_conn):
    unique = uuid.uuid4().hex[:8]
    cur = db_conn.cursor()
    cur.execute(
        """
        INSERT INTO users (email, firebase_uid, name, nic, role, is_active, factory_id)
        VALUES (%s, %s, %s, %s, 'SUPPLIER', true, 1)
        RETURNING id
        """,
        (f"pw-fert-{unique}@test.com", f"pw-uid-fert-{unique}", "PW Fert Supplier", f"PWF{unique}"),
    )
    user_id = cur.fetchone()[0]
    cur.close()

    yield user_id

    cur = db_conn.cursor()
    cur.execute(
        "DELETE FROM supplier_fertilizer_request_item WHERE supplier_fertilizer_request_id IN "
        "(SELECT id FROM supplier_fertilizer_request WHERE supplier_id = %s)",
        (user_id,),
    )
    cur.execute("DELETE FROM supplier_fertilizer_request WHERE supplier_id = %s", (user_id,))
    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    cur.close()


def get_stock_quantity(api_context, stock_id):
    stocks = api_context.get("/api/fertilizer-stocks").json()
    return next(s for s in stocks if s["id"] == stock_id)["quantity"]


def test_create_supplier_fertilizer_request(api_context, fert_supplier, fertilizer_stock):
    response = api_context.post(
        "/api/supplier-fertilizer-requests",
        data={
            "supplierId": fert_supplier,
            "requestDate": "2026-07-29",
            "note": "Need fertilizer",
            "items": [{"fertilizerStockId": fertilizer_stock, "quantity": 3}],
        },
    )

    assert response.status == 200
    body = response.json()
    assert body["status"] == "PENDING"
    assert body["items"][0]["quantity"] == 3


def test_approving_request_decrements_stock(api_context, fert_supplier, fertilizer_stock):
    create_response = api_context.post(
        "/api/supplier-fertilizer-requests",
        data={
            "supplierId": fert_supplier,
            "requestDate": "2026-07-29",
            "note": "Need fertilizer",
            "items": [{"fertilizerStockId": fertilizer_stock, "quantity": 3}],
        },
    )
    request_id = create_response.json()["id"]

    response = api_context.put(
        f"/api/supplier-fertilizer-requests/{request_id}", data={"note": "Approved", "status": "APPROVED"}
    )

    assert response.status == 200
    assert response.json()["status"] == "APPROVED"
    assert get_stock_quantity(api_context, fertilizer_stock) == 7


def test_approving_already_approved_request_does_not_double_decrement(api_context, fert_supplier, fertilizer_stock):
    create_response = api_context.post(
        "/api/supplier-fertilizer-requests",
        data={
            "supplierId": fert_supplier,
            "requestDate": "2026-07-29",
            "note": "Need fertilizer",
            "items": [{"fertilizerStockId": fertilizer_stock, "quantity": 3}],
        },
    )
    request_id = create_response.json()["id"]

    first = api_context.put(
        f"/api/supplier-fertilizer-requests/{request_id}", data={"note": "Approved", "status": "APPROVED"}
    )
    assert first.status == 200
    assert get_stock_quantity(api_context, fertilizer_stock) == 7

    second = api_context.put(
        f"/api/supplier-fertilizer-requests/{request_id}", data={"note": "Approved again", "status": "APPROVED"}
    )
    assert second.status == 200
    assert get_stock_quantity(api_context, fertilizer_stock) == 7


def test_approving_request_exceeding_stock_is_rejected(api_context, fert_supplier, fertilizer_stock):
    create_response = api_context.post(
        "/api/supplier-fertilizer-requests",
        data={
            "supplierId": fert_supplier,
            "requestDate": "2026-07-29",
            "note": "Too much",
            "items": [{"fertilizerStockId": fertilizer_stock, "quantity": 100}],
        },
    )
    request_id = create_response.json()["id"]

    response = api_context.put(
        f"/api/supplier-fertilizer-requests/{request_id}", data={"note": "Approved", "status": "APPROVED"}
    )

    assert response.status == 400
    assert "Insufficient stock" in response.json()["message"]
    assert get_stock_quantity(api_context, fertilizer_stock) == 10
