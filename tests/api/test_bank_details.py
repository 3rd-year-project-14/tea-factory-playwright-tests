import uuid

import pytest


pytestmark = pytest.mark.api

# BankDetailsController only exposes GET endpoints -- there is no POST/PUT/DELETE
# anywhere in the codebase for bank_details (confirmed by grepping every controller).
# So these tests seed data directly via SQL (the only way it can exist) and verify
# the read paths, rather than pretending a create flow exists.


@pytest.fixture
def bank_details_row(db_conn):
    unique = uuid.uuid4().hex[:8]
    cur = db_conn.cursor()
    cur.execute(
        """
        INSERT INTO users (email, firebase_uid, name, nic, role, is_active, factory_id)
        VALUES (%s, %s, %s, %s, 'SUPPLIER', true, 1)
        RETURNING id
        """,
        (f"pw-bank-{unique}@test.com", f"pw-uid-bank-{unique}", "PW Bank Supplier", f"PWB{unique}"),
    )
    user_id = cur.fetchone()[0]

    cur.execute(
        """
        INSERT INTO bank_details (account_holder_name, account_number, bank_name, branch, user_id)
        VALUES (%s, '1234567890', 'Test Bank', 'Kandy', %s)
        RETURNING bank_details_id
        """,
        ("PW Bank Supplier", user_id),
    )
    bank_details_id = cur.fetchone()[0]
    cur.close()

    yield bank_details_id

    cur = db_conn.cursor()
    cur.execute("DELETE FROM bank_details WHERE bank_details_id = %s", (bank_details_id,))
    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    cur.close()


def test_get_all_bank_details_includes_seeded_row(api_context, bank_details_row):
    response = api_context.get("/api/bank-details")

    assert response.status == 200
    ids = [row["bankDetailsId"] for row in response.json()]
    assert bank_details_row in ids


def test_get_bank_details_by_id(api_context, bank_details_row):
    response = api_context.get(f"/api/bank-details/{bank_details_row}")

    assert response.status == 200
    body = response.json()
    assert body["bankName"] == "Test Bank"
    assert body["accountNumber"] == "1234567890"


def test_get_bank_details_not_found(api_context):
    response = api_context.get("/api/bank-details/999999")

    assert response.status == 404
