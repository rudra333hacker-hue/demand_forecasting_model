import os
from fastapi.testclient import TestClient
from main import app
from populate_db import populate_database

client = TestClient(app)

def test_fresh_clone_and_endpoints():
    # 1. Test /health
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json().get("status") == "healthy"

    # 2. Test /skus
    res = client.get("/skus")
    assert res.status_code == 200
    skus = res.json()
    assert isinstance(skus, list) and len(skus) > 0
    print("[OK] GET /skus returned", len(skus), "SKUs")

    # 3. Test /forecast with uncertainty bands and anomaly flag
    res = client.post("/forecast", json={"sku_id": "SKU_001", "is_festival": 0, "city": "Hyderabad"})
    assert res.status_code == 200
    forecast_data = res.json()
    assert "confidence_interval" in forecast_data
    assert "anomaly_flag" in forecast_data
    assert "anomaly_reason" in forecast_data
    print("[OK] POST /forecast returned valid response with CI & Anomaly Flag:", forecast_data["confidence_interval"])

    # 4. Test /log-demand
    res = client.post("/log-demand", json={
        "sku_id": "SKU_001",
        "date_str": "2026-08-14",
        "unmet_quantity": 10,
        "segment": "Regular"
    })
    assert res.status_code == 200
    assert res.json().get("status") == "success"
    print("[OK] POST /log-demand logged unmet demand")

    # 5. Test /optimize-restock with location_id
    res = client.post("/optimize-restock", json={
        "sku_ids": ["SKU_001", "SKU_002", "SKU_003", "SKU_005"],
        "daily_budget": 5000.0,
        "customer_id": "CUST_001",
        "location_id": "LOC_001"
    })
    assert res.status_code == 200
    plan = res.json()
    assert "allocated_orders" in plan
    assert "portfolio_var_95_loss" in plan
    print("[OK] POST /optimize-restock returned portfolio plan with spend INR", plan["total_allocated_spend"])

    # 6. Test /khata-ledger
    res = client.get("/khata-ledger")
    assert res.status_code == 200
    ledger = res.json()
    assert isinstance(ledger, list) and len(ledger) > 0
    print("[OK] GET /khata-ledger returned", len(ledger), "entries")

    # 7. Test /generate-nim-insights (graceful fallback)
    res = client.post("/generate-nim-insights", json={"restock_plan": plan})
    assert res.status_code == 200
    insights = res.json()
    assert "recommendation" in insights
    print("[OK] POST /generate-nim-insights returned recommendation")

    # 8. Test /chat
    res = client.post("/chat", json={"message": "Which items should I restock today?"})
    assert res.status_code == 200
    chat_resp = res.json()
    assert "reply" in chat_resp
    print("[OK] POST /chat returned response:", chat_resp["reply"][:50], "...")

if __name__ == "__main__":
    test_fresh_clone_and_endpoints()
    print("\nALL BACKEND ENDPOINT INTEGRATION TESTS PASSED SUCCESSFULLY!")
