import uuid
from decimal import Decimal

import pytest

# These tests found and drove the fix for two real backend bugs (see PaymentService.java
# disburseCash / generateBankCsv, and CashCollectionBatch.java / Payment.java entities):
#   1. CashCollectionBatch.batchNumber and BankCsvBatch.batchNumber (NOT NULL, unique)
#      were never set before save() -> every disbursement/CSV generation call threw 500.
#      Fixed by using the existing (but previously unused) findTopByOrderByBatchNumberDesc()
#      repository methods to compute the next sequential number.
#   2. CashCollectionBatch.receiptPrinted had a Java field default (`= false`) but no
#      @Builder.Default, so Lombok's @Builder silently dropped it and inserted NULL into
#      a NOT NULL column. Same latent issue fixed defensively on Payment.isDeduction.
#   3. BankCsvBatch.fileName/filePath (NOT NULL) were never set by generateBankCsv().


@pytest.fixture
def cash_payment(db_conn):
    payment_id = f"PW-CASH-{uuid.uuid4().hex[:8].upper()}"
    net_amount = Decimal("1000.00")
    cur = db_conn.cursor()
    cur.execute(
        """
        INSERT INTO payments (id, payment_type, supplier_id, route_id, period_month, period_year,
          gross_amount, total_weight, tea_rate, deduction_amount, net_amount, disbursement_method,
          status, created_at, updated_at)
        VALUES (%s, 'MONTHLY', '999', '1', 7, 2026, %s, 10.00, 100.00, 0.00, %s, 'CASH', 'APPROVED', now(), now())
        """,
        (payment_id, net_amount, net_amount),
    )
    cur.close()

    yield {"id": payment_id, "net_amount": net_amount}

    cur = db_conn.cursor()
    cur.execute("SELECT batch_id FROM cash_collection_payments WHERE payment_id = %s", (payment_id,))
    row = cur.fetchone()
    cur.execute("DELETE FROM payment_audit_log WHERE payment_id = %s", (payment_id,))
    cur.execute("DELETE FROM cash_collection_payments WHERE payment_id = %s", (payment_id,))
    if row:
        cur.execute("DELETE FROM cash_collection_batches WHERE id = %s", (row[0],))
    cur.execute("DELETE FROM payments WHERE id = %s", (payment_id,))
    cur.close()


@pytest.fixture
def bank_payment(db_conn):
    payment_id = f"PW-BANK-{uuid.uuid4().hex[:8].upper()}"
    net_amount = Decimal("1000.00")
    cur = db_conn.cursor()
    cur.execute(
        """
        INSERT INTO payments (id, payment_type, supplier_id, route_id, period_month, period_year,
          gross_amount, total_weight, tea_rate, deduction_amount, net_amount, disbursement_method,
          status, created_at, updated_at)
        VALUES (%s, 'MONTHLY', '999', '1', 7, 2026, %s, 10.00, 100.00, 0.00, %s, 'BANK', 'APPROVED', now(), now())
        """,
        (payment_id, net_amount, net_amount),
    )
    cur.close()

    yield {"id": payment_id, "net_amount": net_amount}

    cur = db_conn.cursor()
    cur.execute("SELECT batch_id FROM bank_csv_payments WHERE payment_id = %s", (payment_id,))
    row = cur.fetchone()
    cur.execute("DELETE FROM payment_audit_log WHERE payment_id = %s", (payment_id,))
    cur.execute("DELETE FROM bank_csv_payments WHERE payment_id = %s", (payment_id,))
    if row:
        cur.execute("DELETE FROM bank_csv_batches WHERE id = %s", (row[0],))
    cur.execute("DELETE FROM payments WHERE id = %s", (payment_id,))
    cur.close()


def test_cash_disbursement_marks_payment_disbursed(api_context, db_conn, cash_payment):
    response = api_context.post(
        "/api/payments/cash/disburse",
        data={
            "routeId": "1",
            "driverId": "1",
            "paymentIds": [cash_payment["id"]],
            "collectedBy": "admin",
            "totalAmount": float(cash_payment["net_amount"]),
        },
    )

    assert response.status == 201
    body = response.json()
    assert body["totalAmount"] == pytest.approx(float(cash_payment["net_amount"]))
    assert body["batchNumber"] is not None

    cur = db_conn.cursor()
    cur.execute("SELECT status, disbursed_by FROM payments WHERE id = %s", (cash_payment["id"],))
    status, disbursed_by = cur.fetchone()
    cur.close()
    assert status == "DISBURSED"
    assert disbursed_by == "admin"


def test_cash_disbursement_rejects_amount_mismatch(api_context, cash_payment):
    response = api_context.post(
        "/api/payments/cash/disburse",
        data={
            "routeId": "1",
            "driverId": "1",
            "paymentIds": [cash_payment["id"]],
            "collectedBy": "admin",
            "totalAmount": float(cash_payment["net_amount"]) - 1,
        },
    )

    assert response.status == 400


def test_cash_disbursement_rejects_bank_payment(api_context, bank_payment):
    response = api_context.post(
        "/api/payments/cash/disburse",
        data={
            "routeId": "1",
            "driverId": "1",
            "paymentIds": [bank_payment["id"]],
            "collectedBy": "admin",
            "totalAmount": float(bank_payment["net_amount"]),
        },
    )

    assert response.status == 400


def test_bank_csv_generation_moves_payment_to_processing(api_context, db_conn, bank_payment):
    response = api_context.post(
        "/api/payments/bank/generate-csv",
        data={"paymentIds": [bank_payment["id"]], "generatedBy": "admin", "factoryId": "1"},
    )

    assert response.status == 201
    body = response.json()
    assert body["status"] == "GENERATED"
    assert body["fileName"]
    assert body["filePath"]

    cur = db_conn.cursor()
    cur.execute("SELECT status, batch_id FROM payments WHERE id = %s", (bank_payment["id"],))
    status, batch_id = cur.fetchone()
    cur.close()
    assert status == "PROCESSING"
    assert batch_id == body["id"]


def test_bank_csv_generation_twice_on_same_payment_fails(api_context, bank_payment):
    first = api_context.post(
        "/api/payments/bank/generate-csv",
        data={"paymentIds": [bank_payment["id"]], "generatedBy": "admin", "factoryId": "1"},
    )
    assert first.status == 201

    second = api_context.post(
        "/api/payments/bank/generate-csv",
        data={"paymentIds": [bank_payment["id"]], "generatedBy": "admin", "factoryId": "1"},
    )
    assert second.status == 500
