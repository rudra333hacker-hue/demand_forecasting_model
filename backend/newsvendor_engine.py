"""
Newsvendor Engine for Smart Restock Inventory Optimization.

Provides functions for:
1. Critical Fractile calculation based on underage/overage costs.
2. Optimal Order Quantity calculation (Q*) using Newsvendor math & MCP metadata tools.
3. Portfolio Budget Allocation with Khata balance deduction and CF ranking.
"""

from typing import Union, Dict, List, Optional
import numpy as np
from scipy.stats import norm

from mcp_server import tool_get_product_cost, tool_get_khata_balance, tool_get_supplier_lead_time


def calculate_critical_fractile(unit_cost: float, selling_price: float) -> float:
    """
    Calculates the Critical Fractile (CF) for a given product using cost-aware asymmetric loss math.
    
    Formula:
      Cu (Cost of Understocking / Lost Profit) = selling_price - unit_cost
      Co (Cost of Overstocking / Holding & Spoilage) = unit_cost * 0.30
      CF = Cu / (Cu + Co)
      
    Interpretation:
      - High margin items (Cu >> Co) yield CF near 1.0 -> order higher safety stock to prevent lost sales.
      - Low margin items (Cu < Co) yield lower CF -> order conservatively to prevent excess inventory holding costs.
    """
    if unit_cost <= 0 or selling_price <= unit_cost:
        return 0.0

    cu = selling_price - unit_cost
    co = unit_cost * 0.30
    denom = cu + co

    if denom <= 0:
        return 0.0

    cf = cu / denom
    return float(np.clip(cf, 0.0, 1.0))


def optimize_order_quantity(
    sku_id: str,
    raw_demand_forecast: Union[float, int, dict, list, np.ndarray],
    location_id: Optional[str] = None
) -> dict:
    """
    Queries SKU metadata via tool_get_product_cost and calculates optimal order quantity Q*
    based on Critical Fractile and demand distribution.
    """
    product_cost_info = tool_get_product_cost(sku_id)
    if not product_cost_info:
        raise ValueError(f"SKU '{sku_id}' not found in database metadata.")

    unit_cost = float(product_cost_info["unit_cost"])
    selling_price = float(product_cost_info["selling_price"])
    current_stock = int(product_cost_info.get("current_stock", 0))
    substitute_sku_id = product_cost_info.get("substitute_sku_id")

    cf = calculate_critical_fractile(unit_cost, selling_price)

    # Extract mean demand and daily std dev
    if isinstance(raw_demand_forecast, dict):
        raw_mean = raw_demand_forecast.get("mean") or raw_demand_forecast.get("forecast") or 0.0
        mean_demand = float(raw_mean)
        raw_std = raw_demand_forecast.get("std") or raw_demand_forecast.get("std_dev") or (mean_demand * 0.20)
        std_demand = float(raw_std)
    elif isinstance(raw_demand_forecast, (list, np.ndarray)):
        mean_demand = float(np.mean(raw_demand_forecast)) if len(raw_demand_forecast) > 0 else 0.0
        std_demand = float(np.std(raw_demand_forecast)) if len(raw_demand_forecast) > 0 and np.std(raw_demand_forecast) > 0 else max(1.0, mean_demand * 0.20)
    else:
        mean_demand = float(raw_demand_forecast)
        std_demand = max(1.0, mean_demand * 0.20)

    if std_demand <= 0:
        std_demand = max(1.0, mean_demand * 0.20)

    if cf <= 0.0:
        target_stock_level = current_stock
        optimal_order_qty = 0
    else:
        try:
            lead_info = tool_get_supplier_lead_time(sku_id)
        except Exception:
            lead_info = {"lead_time_days": 1, "lead_time_std_dev": 0.2}

        lead_days = lead_info.get("lead_time_days", 1)
        lead_std = lead_info.get("lead_time_std_dev", 0.2)

        # Enterprise Lead Time Demand & Safety Stock Math: S* = (mu * L) + z * sqrt(L * std_D^2 + mu^2 * std_L^2)
        lead_time_mean = mean_demand * lead_days
        lead_time_std = float(np.sqrt(lead_days * (std_demand ** 2) + (mean_demand ** 2) * (lead_std ** 2)))

        z_score = float(norm.ppf(cf)) if 0 < cf < 1 else 0.0
        target_stock = lead_time_mean + z_score * lead_time_std

        target_stock_level = max(0, int(round(target_stock)))
        optimal_order_qty = max(0, target_stock_level - current_stock)

    # --- Stock Market Financial Risk & Sharpe Ratio Math ---
    profit_per_unit = max(0.0, selling_price - unit_cost)
    profit_margin_pct = (profit_per_unit / unit_cost) if unit_cost > 0 else 0.0
    demand_cv = (std_demand / mean_demand) if mean_demand > 0 else 0.20
    
    # Inventory Sharpe Ratio: Risk-adjusted return per unit of volatility
    sharpe_ratio = round(profit_margin_pct / (demand_cv + 0.10), 3)

    # Financial Value at Risk (VaR 95% worst-case downside loss bound)
    worst_case_demand_5pct = max(0.0, mean_demand - 1.645 * std_demand)
    unsold_units_risk = max(0.0, (current_stock + optimal_order_qty) - worst_case_demand_5pct)
    var_95_loss_inr = round(unsold_units_risk * unit_cost * 0.30, 2)  # Overage holding/spoilage loss

    return {
        "sku_id": sku_id,
        "unit_cost": unit_cost,
        "selling_price": selling_price,
        "current_stock": current_stock,
        "substitute_sku_id": substitute_sku_id,
        "critical_fractile": round(cf, 4),
        "sharpe_ratio": sharpe_ratio,
        "var_95_loss_inr": var_95_loss_inr,
        "mean_demand": round(mean_demand, 2),
        "target_stock_level": target_stock_level,
        "optimal_order_quantity": optimal_order_qty
    }


def allocate_portfolio_budget(
    orders_list: List[dict],
    total_budget_inr: float,
    customer_id: Optional[str] = None,
    location_id: Optional[str] = None
) -> dict:
    """
    Markowitz Mean-Variance Portfolio Budget Optimizer:
    Allocates available budget across candidate SKU orders ranked by Risk-Adjusted Sharpe Ratio & Critical Fractile.
    Deducts 10% of customer Khata debit balance if customer_id is provided.
    Applies a 10% correlation discount on substitute products to avoid double-ordering correlated items.
    Calculates Portfolio Expected Profit and 95% Value at Risk (VaR) downside loss bound.
    """
    khata_deduction = 0.0
    if customer_id:
        khata_info = tool_get_khata_balance(customer_id)
        if khata_info and "debit_balance" in khata_info:
            debit_balance = float(khata_info["debit_balance"])
            if debit_balance > 0:
                khata_deduction = debit_balance * 0.10

    effective_budget = max(0.0, float(total_budget_inr) - khata_deduction)

    # Sort orders by Markowitz Risk-Adjusted Score = (0.6 * CF) + (0.4 * Sharpe Ratio)
    sorted_orders = sorted(
        orders_list,
        key=lambda x: (
            (0.6 * x.get("critical_fractile", 0.0)) + (0.4 * min(3.0, x.get("sharpe_ratio", 0.0) / 3.0)),
            (x.get("selling_price", 0.0) - x.get("unit_cost", 0.0)) / (x.get("unit_cost", 1.0))
        ),
        reverse=True
    )

    remaining_budget = effective_budget
    allocated_orders = []
    total_expected_profit = 0.0
    total_var_95_loss = 0.0
    allocated_skus = set()

    for order in sorted_orders:
        sku_id = order.get("sku_id")
        unit_cost = float(order.get("unit_cost", 0.0))
        selling_price = float(order.get("selling_price", 0.0))
        requested_qty = int(order.get("optimal_order_quantity") or order.get("order_quantity") or 0)
        substitute_sku_id = order.get("substitute_sku_id")

        # Apply substitute correlation discount if a substitute SKU was already allocated in portfolio
        if substitute_sku_id and substitute_sku_id in allocated_skus:
            requested_qty = max(1, int(round(requested_qty * 0.90)))

        if unit_cost > 0:
            affordable_qty = min(requested_qty, int(remaining_budget // unit_cost))
        else:
            affordable_qty = requested_qty

        allocated_cost = affordable_qty * unit_cost
        remaining_budget -= allocated_cost

        unit_profit = max(0.0, selling_price - unit_cost)
        expected_profit = affordable_qty * unit_profit
        total_expected_profit += expected_profit

        var_loss = order.get("var_95_loss_inr", 0.0) * (affordable_qty / max(1, requested_qty))
        total_var_95_loss += var_loss

        allocated_order = dict(order)
        allocated_order["allocated_quantity"] = affordable_qty
        allocated_order["allocated_cost"] = round(allocated_cost, 2)
        allocated_order["expected_profit"] = round(expected_profit, 2)
        allocated_order["fulfilled"] = (affordable_qty == requested_qty)

        allocated_orders.append(allocated_order)
        if sku_id:
            allocated_skus.add(sku_id)

    return {
        "initial_budget": float(total_budget_inr),
        "customer_id": customer_id,
        "khata_deduction": round(khata_deduction, 2),
        "effective_budget": round(effective_budget, 2),
        "remaining_budget": round(remaining_budget, 2),
        "total_allocated_spend": round(effective_budget - remaining_budget, 2),
        "expected_portfolio_profit": round(total_expected_profit, 2),
        "portfolio_var_95_loss": round(total_var_95_loss, 2),
        "allocated_orders": allocated_orders
    }


if __name__ == "__main__":
    print("--- 1. Testing calculate_critical_fractile ---")
    cf1 = calculate_critical_fractile(unit_cost=250.0, selling_price=320.0)
    print(f"SKU_001 CF: {cf1:.4f}")

    print("\n--- 2. Testing optimize_order_quantity ---")
    skus = ["SKU_001", "SKU_002", "SKU_003", "SKU_004", "SKU_005"]
    orders = []
    for sku in skus:
        order = optimize_order_quantity(sku, raw_demand_forecast=60.0)
        orders.append(order)
        print(f"{sku}: CF={order['critical_fractile']}, TargetStock={order['target_stock_level']}, CurrentStock={order['current_stock']}, OrderQty={order['optimal_order_quantity']}")

    print("\n--- 3. Testing allocate_portfolio_budget ---")
    allocation = allocate_portfolio_budget(orders_list=orders, total_budget_inr=5000.0, customer_id="CUST_001")
    print(f"Initial Budget: INR {allocation['initial_budget']}")
    print(f"Khata Deduction (10% of CUST_001 balance): INR {allocation['khata_deduction']}")
    print(f"Effective Budget: INR {allocation['effective_budget']}")
    print(f"Total Allocated Spend: INR {allocation['total_allocated_spend']}")
    print(f"Remaining Budget: INR {allocation['remaining_budget']}")
    print("Allocated Orders:")
    for ao in allocation['allocated_orders']:
        print(f"  {ao['sku_id']} | CF: {ao['critical_fractile']} | UnitCost: INR {ao['unit_cost']} | Requested: {ao['optimal_order_quantity']} | Allocated: {ao['allocated_quantity']} | Spend: INR {ao['allocated_cost']} | Fulfilled: {ao['fulfilled']}")
