import sys
from mcp_server import (
    get_sales_history,
    get_current_stock,
    get_product_cost,
    log_manual_demand,
    get_khata_ledger,
    get_all_skus
)

def run_mcp_tests():
    print("==================================================")
    print("   Running Standalone MCP Data Access Layer Tests ")
    print("==================================================\n")

    # 1. Test get_all_skus
    skus = get_all_skus()
    assert isinstance(skus, list) and len(skus) > 0, "Failed: get_all_skus returned empty or invalid list"
    print(f"[OK] 1. get_all_skus(): Successfully fetched {len(skus)} SKUs")
    print(f"     Sample: {skus[0]['sku_id']} - {skus[0]['name']} (Stock: {skus[0]['current_stock']})")

    target_sku = skus[0]['sku_id']

    # 2. Test get_product_cost
    cost_info = get_product_cost(target_sku)
    assert cost_info is not None and "unit_cost" in cost_info and "selling_price" in cost_info, f"Failed: get_product_cost({target_sku})"
    print(f"[OK] 2. get_product_cost('{target_sku}'): Unit Cost INR {cost_info['unit_cost']}, Selling Price INR {cost_info['selling_price']}")

    # 3. Test get_current_stock
    stock = get_current_stock(target_sku)
    assert stock is not None and stock >= 0, f"Failed: get_current_stock({target_sku})"
    print(f"[OK] 3. get_current_stock('{target_sku}'): {stock} units")

    # 4. Test get_sales_history
    sales = get_sales_history(target_sku, limit=5)
    assert isinstance(sales, list), f"Failed: get_sales_history({target_sku})"
    print(f"[OK] 4. get_sales_history('{target_sku}'): Retreived {len(sales)} historical daily records")

    # 5. Test log_manual_demand
    log_res = log_manual_demand(target_sku, "2026-08-14", 7, "VIP")
    assert log_res.get("status") == "success" and log_res.get("logged_unmet_qty") == 7, "Failed: log_manual_demand"
    print(f"[OK] 5. log_manual_demand('{target_sku}'): Logged 7 unmet demand units on 2026-08-14")

    # 6. Test get_khata_ledger
    ledger = get_khata_ledger()
    assert isinstance(ledger, list) and len(ledger) > 0, "Failed: get_khata_ledger"
    print(f"[OK] 6. get_khata_ledger(): Fetched {len(ledger)} customer ledger accounts")
    print(f"     Sample: {ledger[0]['customer_id']} - {ledger[0]['customer_name']} (Debit: INR {ledger[0]['debit_balance']})")

    print("\n==================================================")
    print("   ALL 6 MCP TOOL TESTS PASSED SUCCESSFULLY! SUCCESS ")
    print("==================================================")

if __name__ == "__main__":
    run_mcp_tests()
