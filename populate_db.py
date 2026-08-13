import sqlite3
import datetime
import random

def populate_database():
    conn = sqlite3.connect("inveniq.db")
    cursor = conn.cursor()

    # 0. Drop existing tables if schema is updating
    cursor.execute("DROP TABLE IF EXISTS sales_history")
    cursor.execute("DROP TABLE IF EXISTS manual_demand_logs")
    cursor.execute("DROP TABLE IF EXISTS skus")
    cursor.execute("DROP TABLE IF EXISTS khata_ledger")
    cursor.execute("DROP TABLE IF EXISTS promotions")
    cursor.execute("DROP TABLE IF EXISTS holidays_calendar")
    cursor.execute("DROP TABLE IF EXISTS supplier_lead_times")

    # 1. Create Tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS skus (
        sku_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        unit_cost REAL NOT NULL,
        selling_price REAL NOT NULL,
        current_stock INTEGER NOT NULL,
        location_id TEXT DEFAULT 'LOC_001',
        substitute_sku_id TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sales_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sku_id TEXT NOT NULL,
        date TEXT NOT NULL,
        quantity_sold REAL NOT NULL,
        location_id TEXT DEFAULT 'LOC_001',
        FOREIGN KEY (sku_id) REFERENCES skus (sku_id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS manual_demand_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sku_id TEXT NOT NULL,
        date TEXT NOT NULL,
        unmet_quantity INTEGER NOT NULL,
        customer_segment TEXT DEFAULT 'Regular',
        location_id TEXT DEFAULT 'LOC_001',
        FOREIGN KEY (sku_id) REFERENCES skus (sku_id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS khata_ledger (
        customer_id TEXT PRIMARY KEY,
        customer_name TEXT NOT NULL,
        segment TEXT NOT NULL,
        debit_balance REAL NOT NULL
    )
    """)

    # --- Enterprise Tables ---
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS promotions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sku_id TEXT NOT NULL,
        promo_name TEXT NOT NULL,
        discount_percent REAL NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS holidays_calendar (
        date TEXT PRIMARY KEY,
        holiday_name TEXT NOT NULL,
        event_type TEXT NOT NULL,
        demand_impact_multiplier REAL NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS supplier_lead_times (
        sku_id TEXT PRIMARY KEY,
        lead_time_days INTEGER NOT NULL,
        lead_time_std_dev REAL NOT NULL,
        moq INTEGER DEFAULT 10
    )
    """)

    # Clear existing data to ensure clean setup
    cursor.execute("DELETE FROM sales_history")
    cursor.execute("DELETE FROM skus")
    cursor.execute("DELETE FROM manual_demand_logs")
    cursor.execute("DELETE FROM khata_ledger")
    cursor.execute("DELETE FROM promotions")
    cursor.execute("DELETE FROM holidays_calendar")
    cursor.execute("DELETE FROM supplier_lead_times")

    # 2. Insert SKUs (sku_id, name, category, unit_cost, selling_price, current_stock, location_id, substitute_sku_id)
    skus_data = [
        ("SKU_001", "Basmati Rice 5kg", "Staples", 250.0, 320.0, 50, "LOC_001", "SKU_005"),
        ("SKU_002", "Full Cream Milk 1L", "Dairy", 45.0, 55.0, 30, "LOC_001", None),
        ("SKU_003", "Mango Drink 1L", "Beverages", 65.0, 90.0, 20, "LOC_001", "SKU_004"),
        ("SKU_004", "Potato Chips 100g", "Snacks", 15.0, 20.0, 40, "LOC_001", "SKU_003"),
        ("SKU_005", "Toor Dal 1kg", "Staples", 110.0, 140.0, 25, "LOC_001", "SKU_001"),
    ]
    cursor.executemany("INSERT INTO skus VALUES (?, ?, ?, ?, ?, ?, ?, ?)", skus_data)

    # 3. Generate daily time-series sales history for 60 days
    base_date = datetime.date(2026, 6, 15)
    random.seed(42)

    sales_entries = []
    for day_offset in range(60):
        current_date = (base_date + datetime.timedelta(days=day_offset)).strftime("%Y-%m-%d")
        
        # SKU_001 (Staple: Stable demand around 45 ± 3)
        qty_001 = round(45.0 + random.normalvariate(0, 3), 1)
        sales_entries.append(("SKU_001", current_date, max(10.0, qty_001)))

        # SKU_002 (Dairy: Stable demand around 30 ± 2.5)
        qty_002 = round(30.0 + random.normalvariate(0, 2.5), 1)
        sales_entries.append(("SKU_002", current_date, max(5.0, qty_002)))

        # SKU_003 (Beverages: Volatile demand 40-70 with weekend spike)
        qty_003 = round(50.0 + random.uniform(-15, 15) + (8 if day_offset % 7 in [5, 6] else 0), 1)
        sales_entries.append(("SKU_003", current_date, max(10.0, qty_003)))

        # SKU_004 (Snacks: High variance 25-50)
        qty_004 = round(35.0 + random.uniform(-10, 10), 1)
        sales_entries.append(("SKU_004", current_date, max(5.0, qty_004)))

        # SKU_005 (Staple: Stable demand around 20 ± 2)
        qty_005 = round(20.0 + random.normalvariate(0, 2), 1)
        sales_entries.append(("SKU_005", current_date, max(5.0, qty_005)))

    cursor.executemany("INSERT INTO sales_history (sku_id, date, quantity_sold) VALUES (?, ?, ?)", sales_entries)

    # 4. Insert Manual Unmet Demand Logs
    manual_logs = [
        ("SKU_001", "2026-08-10", 5, "Regular"),
        ("SKU_001", "2026-08-12", 3, "VIP"),
        ("SKU_003", "2026-08-11", 8, "Regular"),
        ("SKU_003", "2026-08-12", 12, "Regular"),
    ]
    cursor.executemany("INSERT INTO manual_demand_logs (sku_id, date, unmet_quantity, customer_segment) VALUES (?, ?, ?, ?)", manual_logs)

    # 5. Insert Khata Ledger
    khata_entries = [
        ("CUST_001", "Ramesh Kumar", "Regular", 1450.0),
        ("CUST_002", "Anita Sharma", "VIP", 0.0),
        ("CUST_003", "Suresh Patel", "Regular", 620.5),
    ]
    cursor.executemany("INSERT INTO khata_ledger VALUES (?, ?, ?, ?)", khata_entries)

    # 6. Insert Promotions Data
    promotions_data = [
        ("SKU_003", "Summer Refresh Fest (15% OFF)", 15.0, "2026-08-10", "2026-08-20"),
        ("SKU_004", "Snack Combo Promo (10% OFF)", 10.0, "2026-08-14", "2026-08-18"),
    ]
    cursor.executemany("INSERT INTO promotions (sku_id, promo_name, discount_percent, start_date, end_date) VALUES (?, ?, ?, ?, ?)", promotions_data)

    # 7. Insert Holidays & Events Calendar
    holidays_data = [
        ("2026-08-15", "Independence Day", "National Holiday", 1.30),
        ("2026-08-25", "Ganesh Chaturthi", "Major Festival", 1.45),
        ("2026-11-08", "Diwali Festival", "Grand Festival", 1.60),
    ]
    cursor.executemany("INSERT INTO holidays_calendar VALUES (?, ?, ?, ?)", holidays_data)

    # 8. Insert Supplier Lead Times
    lead_time_data = [
        ("SKU_001", 3, 0.5, 10),
        ("SKU_002", 1, 0.2, 5),
        ("SKU_003", 2, 0.4, 12),
        ("SKU_004", 2, 0.3, 20),
        ("SKU_005", 3, 0.5, 10),
    ]
    cursor.executemany("INSERT INTO supplier_lead_times VALUES (?, ?, ?, ?)", lead_time_data)

    conn.commit()
    conn.close()
    print("Database inveniq.db successfully populated with enterprise multi-factor tables!")

if __name__ == "__main__":
    populate_database()
