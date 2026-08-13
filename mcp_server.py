import sqlite3
import os
from typing import Optional, List, Dict, Any, Union

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inveniq.db")


def get_db_connection():
    return sqlite3.connect(DB_PATH)


# --- MCP Tool 1: Get Sales History ---
def tool_get_sales_history(sku_id: str, location_id: Optional[str] = None, limit: int = 60, date_range: Optional[tuple] = None) -> List[Dict[str, Any]]:
    """
    Standardized MCP Tool: Reads historical daily sales for a SKU.
    Supports optional location_id filtering and date_range filtering.
    """
    query = "SELECT date, quantity_sold FROM sales_history WHERE sku_id = ?"
    params = [sku_id]

    if location_id:
        query += " AND location_id = ?"
        params.append(location_id)

    if date_range and len(date_range) == 2:
        query += " AND date BETWEEN ? AND ?"
        params.extend(date_range)

    query += " ORDER BY date DESC LIMIT ?"
    params.append(limit)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
    return [{"date": r[0], "quantity_sold": float(r[1])} for r in rows]


# --- MCP Tool 2: Get Current Stock Level ---
def tool_get_current_stock(sku_id: str, location_id: Optional[str] = None) -> Optional[int]:
    """
    Standardized MCP Tool: Reads current inventory stock level for a SKU.
    """
    query = "SELECT current_stock FROM skus WHERE sku_id = ?"
    params = [sku_id]

    if location_id:
        query += " AND location_id = ?"
        params.append(location_id)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        row = cursor.fetchone()
    return row[0] if row else None


# --- MCP Tool 3: Get Product Pricing & Costs ---
def tool_get_product_cost(sku_id: str) -> Optional[Dict[str, Any]]:
    """
    Standardized MCP Tool: Reads unit_cost, selling_price, current_stock, and substitute_sku_id for Newsvendor math.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT unit_cost, selling_price, current_stock, substitute_sku_id, name, category 
            FROM skus WHERE sku_id = ?
        """,
            (sku_id,),
        )
        row = cursor.fetchone()
    if row:
        return {
            "sku_id": sku_id,
            "unit_cost": float(row[0]),
            "selling_price": float(row[1]),
            "current_stock": int(row[2]),
            "substitute_sku_id": row[3],
            "name": row[4],
            "category": row[5]
        }
    return None


# --- MCP Tool 4: Log Manual Unmet Demand ---
def tool_log_manual_demand(
    sku_id: str,
    date_str: str,
    unmet_quantity: int,
    customer_segment: str = "Regular",
    location_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Standardized MCP Tool: Records unfulfilled customer demand to correct for stockout demand censoring.
    """
    loc_id = location_id if location_id else "LOC_001"
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO manual_demand_logs (sku_id, date, unmet_quantity, customer_segment, location_id)
            VALUES (?, ?, ?, ?, ?)
        """,
            (sku_id, date_str, int(unmet_quantity), customer_segment, loc_id),
        )
        conn.commit()
    return {"status": "success", "logged_unmet_qty": int(unmet_quantity)}


# --- MCP Tool 5: Get Customer Khata Ledger ---
def tool_get_khata_ledger(customer_id: Optional[str] = None) -> Union[Dict[str, Any], List[Dict[str, Any]], None]:
    """
    Standardized MCP Tool: Reads credit/debit balances for a single customer or all customers.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if customer_id:
            cursor.execute(
                "SELECT customer_id, customer_name, segment, debit_balance FROM khata_ledger WHERE customer_id = ?",
                (customer_id,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "customer_id": row[0],
                    "customer_name": row[1],
                    "segment": row[2],
                    "debit_balance": float(row[3]),
                }
            return None
        else:
            cursor.execute("SELECT customer_id, customer_name, segment, debit_balance FROM khata_ledger")
            rows = cursor.fetchall()
            return [
                {
                    "customer_id": r[0],
                    "customer_name": r[1],
                    "segment": r[2],
                    "debit_balance": float(r[3]),
                }
                for r in rows
            ]


# --- MCP Tool 6: Get Khata Balance for single customer (alias) ---
def tool_get_khata_balance(customer_id: str) -> Optional[Dict[str, Any]]:
    res = tool_get_khata_ledger(customer_id)
    if isinstance(res, dict):
        return res
    return None


# --- MCP Tool 7: Get All SKUs ---
def tool_get_all_skus(location_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Standardized MCP Tool: Retrieves all inventory SKUs.
    """
    query = "SELECT sku_id, name, category, unit_cost, selling_price, current_stock, location_id, substitute_sku_id FROM skus"
    params = []
    if location_id:
        query += " WHERE location_id = ?"
        params.append(location_id)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
    return [
        {
            "sku_id": r[0],
            "name": r[1],
            "category": r[2],
            "unit_cost": float(r[3]),
            "selling_price": float(r[4]),
            "current_stock": int(r[5]),
            "location_id": r[6],
            "substitute_sku_id": r[7],
        }
        for r in rows
    ]


# --- MCP Tool 8: Real-time Update SKU Stock/Price/Cost/Name ---
def tool_update_sku_metadata(
    sku_id: str,
    name: Optional[str] = None,
    category: Optional[str] = None,
    unit_cost: Optional[float] = None,
    selling_price: Optional[float] = None,
    current_stock: Optional[int] = None,
    location_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Standardized MCP Tool: Updates inventory metadata for a SKU.
    """
    fields = []
    params = []

    if name is not None:
        fields.append("name = ?")
        params.append(name)
    if category is not None:
        fields.append("category = ?")
        params.append(category)
    if unit_cost is not None:
        fields.append("unit_cost = ?")
        params.append(float(unit_cost))
    if selling_price is not None:
        fields.append("selling_price = ?")
        params.append(float(selling_price))
    if current_stock is not None:
        fields.append("current_stock = ?")
        params.append(int(current_stock))
    if location_id is not None:
        fields.append("location_id = ?")
        params.append(location_id)

    if not fields:
        return {"status": "error", "message": "No fields provided to update."}

    params.append(sku_id)
    query = f"UPDATE skus SET {', '.join(fields)} WHERE sku_id = ?"

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        updated = cursor.rowcount
        conn.commit()

    if updated > 0:
        return {"status": "success", "sku_id": sku_id, "updated_fields": len(fields)}
    return {"status": "error", "message": f"SKU '{sku_id}' not found in database."}


# --- MCP Tool 9: Real-time Add New SKU ---
def tool_add_new_sku(
    sku_id: str,
    name: str,
    category: str,
    unit_cost: float,
    selling_price: float,
    current_stock: int,
    location_id: Optional[str] = None,
    substitute_sku_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Standardized MCP Tool: Adds or replaces a SKU in the database.
    """
    loc_id = location_id if location_id else "LOC_001"
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO skus (sku_id, name, category, unit_cost, selling_price, current_stock, location_id, substitute_sku_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (sku_id, name, category, float(unit_cost), float(selling_price), int(current_stock), loc_id, substitute_sku_id),
        )
        conn.commit()
    return {
        "status": "success",
        "sku_id": sku_id,
        "name": name,
        "category": category,
        "unit_cost": unit_cost,
        "selling_price": selling_price,
        "current_stock": current_stock,
        "location_id": loc_id,
        "substitute_sku_id": substitute_sku_id,
    }


# --- MCP Tool 10: Update Customer Khata Debit Balance ---
def tool_update_khata_balance(customer_id: str, debit_delta: float) -> Dict[str, Any]:
    """
    Standardized MCP Tool: Adjusts customer credit ledger balance.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT debit_balance FROM khata_ledger WHERE customer_id = ?",
            (customer_id,),
        )
        row = cursor.fetchone()
        if row:
            new_balance = max(0.0, float(row[0]) + float(debit_delta))
            cursor.execute(
                "UPDATE khata_ledger SET debit_balance = ? WHERE customer_id = ?",
                (new_balance, customer_id),
            )
            conn.commit()
            return {"status": "success", "customer_id": customer_id, "new_debit_balance": new_balance}
        else:
            new_balance = max(0.0, float(debit_delta))
            cust_name = f"Customer {customer_id}" if customer_id.startswith("CUST_") else customer_id
            cursor.execute(
                "INSERT INTO khata_ledger (customer_id, customer_name, segment, debit_balance) VALUES (?, ?, ?, ?)",
                (customer_id, cust_name, "Regular", new_balance),
            )
            conn.commit()
            return {"status": "success", "customer_id": customer_id, "new_debit_balance": new_balance}


# --- MCP Tool 11: Read Active Promotions ---
def tool_get_promotions(sku_id: str, date_str: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if date_str:
            cursor.execute(
                """
                SELECT promo_name, discount_percent FROM promotions 
                WHERE sku_id = ? AND ? BETWEEN start_date AND end_date
            """,
                (sku_id, date_str),
            )
        else:
            cursor.execute(
                """
                SELECT promo_name, discount_percent FROM promotions WHERE sku_id = ?
            """,
                (sku_id,),
            )
        rows = cursor.fetchall()
    if rows:
        return [{"promo_name": r[0], "discount_percent": float(r[1])} for r in rows]
    return []


# --- MCP Tool 12: Read Holiday/Event Multiplier ---
def tool_get_holiday_event(date_str: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not date_str:
        return None
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT holiday_name, event_type, demand_impact_multiplier 
            FROM holidays_calendar WHERE date = ?
        """,
            (date_str,),
        )
        row = cursor.fetchone()
    if row:
        return {
            "holiday_name": row[0],
            "event_type": row[1],
            "multiplier": float(row[2]),
        }
    return None


# --- MCP Tool 13: Read Supplier Lead Time & Risk ---
def tool_get_supplier_lead_time(sku_id: str) -> Dict[str, Any]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT lead_time_days, lead_time_std_dev, moq 
            FROM supplier_lead_times WHERE sku_id = ?
        """,
            (sku_id,),
        )
        row = cursor.fetchone()
    if row:
        return {
            "lead_time_days": int(row[0]),
            "lead_time_std_dev": float(row[1]),
            "moq": int(row[2]),
        }
    return {"lead_time_days": 2, "lead_time_std_dev": 0.3, "moq": 10}


# Direct alias mappings for standard tool names requested in Part 3 specification
get_sales_history = tool_get_sales_history
get_current_stock = tool_get_current_stock
get_product_cost = tool_get_product_cost
log_manual_demand = tool_log_manual_demand
get_khata_ledger = tool_get_khata_ledger
get_all_skus = tool_get_all_skus