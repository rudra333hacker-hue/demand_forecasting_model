import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inveniq.db")


def get_db_connection():
  return sqlite3.connect(DB_PATH)


# --- MCP Tool 1: Get Sales History for AI Engine ---
def tool_get_sales_history(sku_id: str, limit: int = 30):
  with get_db_connection() as conn:
    cursor = conn.cursor()
    cursor.execute(
        """
          SELECT date, quantity_sold FROM sales_history
          WHERE sku_id = ? ORDER BY date DESC LIMIT ?
      """,
        (sku_id, limit),
    )
    rows = cursor.fetchall()
  return [{"date": r[0], "quantity_sold": r[1]} for r in rows]


# --- MCP Tool 2: Get Product Pricing & Costs for Newsvendor Math ---
def tool_get_product_cost(sku_id: str):
  with get_db_connection() as conn:
    cursor = conn.cursor()
    cursor.execute(
        """
          SELECT unit_cost, selling_price, current_stock FROM skus WHERE sku_id = ?
      """,
        (sku_id,),
    )
    row = cursor.fetchone()
  if row:
    return {"unit_cost": row[0], "selling_price": row[1], "current_stock": row[2]}
  return None


# --- MCP Tool 3: Log Manual Unmet Demand (Fixes Censored Demand) ---
def tool_log_manual_demand(
    sku_id: str,
    date_str: str,
    unmet_quantity: int,
    segment: str = "Regular",
):
  with get_db_connection() as conn:
    cursor = conn.cursor()
    cursor.execute(
        """
          INSERT INTO manual_demand_logs (sku_id, date, unmet_quantity, customer_segment)
          VALUES (?, ?, ?, ?)
      """,
        (sku_id, date_str, unmet_quantity, segment),
    )
    conn.commit()
  return {"status": "success", "logged_unmet_qty": unmet_quantity}


# --- MCP Tool 4: Read Customer Khata Balance ---
def tool_get_khata_balance(customer_id: str):
  with get_db_connection() as conn:
    cursor = conn.cursor()
    cursor.execute(
        """
          SELECT customer_name, segment, debit_balance FROM khata_ledger WHERE customer_id = ?
      """,
        (customer_id,),
    )
    row = cursor.fetchone()
  if row:
    return {
        "customer_name": row[0],
        "segment": row[1],
        "debit_balance": row[2],
    }
  return None


# --- MCP Tool 5: Get All SKUs in Database ---
def tool_get_all_skus():
  with get_db_connection() as conn:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT sku_id, name, category, unit_cost, selling_price, current_stock FROM skus"
    )
    rows = cursor.fetchall()
  return [
      {
          "sku_id": r[0],
          "name": r[1],
          "category": r[2],
          "unit_cost": r[3],
          "selling_price": r[4],
          "current_stock": r[5],
      }
      for r in rows
  ]


# --- MCP Tool 6: Real-time Update SKU Stock/Price/Cost/Name ---
def tool_update_sku_metadata(
    sku_id: str,
    name: str = None,
    category: str = None,
    unit_cost: float = None,
    selling_price: float = None,
    current_stock: int = None,
):
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


# --- MCP Tool 7: Real-time Add New SKU ---
def tool_add_new_sku(
    sku_id: str,
    name: str,
    category: str,
    unit_cost: float,
    selling_price: float,
    current_stock: int,
):
  with get_db_connection() as conn:
    cursor = conn.cursor()
    cursor.execute(
        """
          INSERT OR REPLACE INTO skus (sku_id, name, category, unit_cost, selling_price, current_stock)
          VALUES (?, ?, ?, ?, ?, ?)
      """,
        (sku_id, name, category, float(unit_cost), float(selling_price), int(current_stock)),
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
  }


# --- MCP Tool 8: Update Customer Khata Debit Balance ---
def tool_update_khata_balance(customer_id: str, debit_delta: float):
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
      # Insert new walk-in / registered customer entry
      new_balance = max(0.0, float(debit_delta))
      cust_name = f"Customer {customer_id}" if customer_id.startswith("CUST_") else customer_id
      cursor.execute(
          "INSERT INTO khata_ledger (customer_id, customer_name, segment, debit_balance) VALUES (?, ?, ?, ?)",
          (customer_id, cust_name, "Regular", new_balance),
      )
      conn.commit()
      return {"status": "success", "customer_id": customer_id, "new_debit_balance": new_balance}


# --- MCP Tool 9: Read Active Promotions for SKU ---
def tool_get_promotions(sku_id: str, date_str: str = None):
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
    return [
        {"promo_name": r[0], "discount_percent": float(r[1])} for r in rows
    ]
  return []


# --- MCP Tool 10: Read Holiday/Event Multiplier ---
def tool_get_holiday_event(date_str: str = None):
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


# --- MCP Tool 11: Read Supplier Lead Time & Risk ---
def tool_get_supplier_lead_time(sku_id: str):
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
