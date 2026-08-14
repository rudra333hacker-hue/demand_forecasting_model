import sqlite3
import datetime
import random
import os

def populate_database():
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database", "inveniq.db")
    conn = sqlite3.connect(db_path)
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

    # 2. Insert Real Supermarket SKUs (20 items across 6 supermarket departments)
    skus_data = [
        # --- Produce ---
        ("SKU_001", "Fresh Farm Tomatoes 1kg", "Produce", 28.0, 40.0, 35, "LOC_001", None),
        ("SKU_002", "Red Onions 1kg", "Produce", 24.0, 35.0, 50, "LOC_001", None),
        ("SKU_003", "Fresh Potatoes 1kg", "Produce", 20.0, 30.0, 60, "LOC_001", None),
        ("SKU_004", "Robusta Bananas 1 Dozen", "Produce", 35.0, 50.0, 25, "LOC_001", None),

        # --- Dairy & Bakery ---
        ("SKU_005", "Amul Taaza Toned Milk 1L", "Dairy", 48.0, 56.0, 40, "LOC_001", None),
        ("SKU_006", "Amul Pasteurised Butter 500g", "Dairy", 240.0, 275.0, 15, "LOC_001", None),
        ("SKU_007", "Britannia White Bread 400g", "Dairy", 30.0, 40.0, 20, "LOC_001", None),
        ("SKU_008", "Milky Mist Fresh Paneer 200g", "Dairy", 75.0, 95.0, 18, "LOC_001", None),

        # --- Staples & Edible Oils ---
        ("SKU_009", "Fortune Sunflower Oil 1L", "Staples", 125.0, 155.0, 30, "LOC_001", None),
        ("SKU_010", "Aashirvaad Atta 10kg", "Staples", 340.0, 420.0, 25, "LOC_001", None),
        ("SKU_011", "India Gate Basmati Rice 5kg", "Staples", 480.0, 620.0, 20, "LOC_001", None),
        ("SKU_012", "Tata Iodized Salt 1kg", "Staples", 20.0, 28.0, 50, "LOC_001", None),
        ("SKU_013", "Tata Sampann Toor Dal 1kg", "Staples", 135.0, 175.0, 22, "LOC_001", None),

        # --- Beverages ---
        ("SKU_014", "Coca-Cola Original 1.5L", "Beverages", 60.0, 80.0, 24, "LOC_001", "SKU_015"),
        ("SKU_015", "Pepsi Soft Drink 1.5L", "Beverages", 58.0, 78.0, 20, "LOC_001", "SKU_014"),
        ("SKU_016", "Real Orange Juice 1L", "Beverages", 90.0, 125.0, 16, "LOC_001", None),

        # --- Snacks & Packaged Foods ---
        ("SKU_017", "Maggi Masala Noodles 4-Pack", "Snacks", 42.0, 56.0, 45, "LOC_001", None),
        ("SKU_018", "Britannia Good Day Biscuits 200g", "Snacks", 28.0, 38.0, 35, "LOC_001", None),

        # --- Personal & Home Care ---
        ("SKU_019", "Surf Excel Easy Wash 1kg", "Homecare", 115.0, 145.0, 25, "LOC_001", None),
        ("SKU_020", "Dettol Bath Soap Bar 125g", "Personal Care", 38.0, 50.0, 40, "LOC_001", None),
    ]
    cursor.executemany("INSERT INTO skus VALUES (?, ?, ?, ?, ?, ?, ?, ?)", skus_data)

    # 3. Generate daily sales history for 60 days up to today (Aug 14, 2026)
    base_date = datetime.date(2026, 6, 15)
    random.seed(2026)

    # Mean daily demand rates for each SKU
    base_demand = {
        "SKU_001": 42.0, "SKU_002": 48.0, "SKU_003": 55.0, "SKU_004": 28.0,
        "SKU_005": 52.0, "SKU_006": 12.0, "SKU_007": 24.0, "SKU_008": 16.0,
        "SKU_009": 22.0, "SKU_010": 18.0, "SKU_011": 15.0, "SKU_012": 35.0,
        "SKU_013": 20.0, "SKU_014": 30.0, "SKU_015": 26.0, "SKU_016": 14.0,
        "SKU_017": 40.0, "SKU_018": 32.0, "SKU_019": 18.0, "SKU_020": 25.0,
    }

    sales_entries = []
    for day_offset in range(60):
        current_dt = base_date + datetime.timedelta(days=day_offset)
        date_str = current_dt.strftime("%Y-%m-%d")
        is_weekend = current_dt.weekday() in (5, 6)

        for sku_id, mu in base_demand.items():
            mult = 1.25 if (is_weekend and sku_id in ("SKU_004", "SKU_014", "SKU_015", "SKU_017", "SKU_018")) else 1.0
            # Pre-Independence Day shopping bump for Aug 12-14
            if date_str in ("2026-08-12", "2026-08-13", "2026-08-14") and sku_id in ("SKU_009", "SKU_010", "SKU_011", "SKU_017"):
                mult *= 1.30

            qty = round(max(3.0, random.normalvariate(mu * mult, mu * 0.12)), 1)
            sales_entries.append((sku_id, date_str, qty))

    cursor.executemany("INSERT INTO sales_history (sku_id, date, quantity_sold) VALUES (?, ?, ?)", sales_entries)

    # 4. Insert Manual Unmet Demand Logs (Today & recent days stockouts)
    manual_logs = [
        ("SKU_005", "2026-08-14", 12, "Regular"),  # High morning demand for Amul Milk
        ("SKU_010", "2026-08-14", 8, "Bulk Kirana"), # Pre-holiday Atta stockout
        ("SKU_001", "2026-08-13", 6, "Regular"),
        ("SKU_014", "2026-08-13", 10, "VIP"),
    ]
    cursor.executemany("INSERT INTO manual_demand_logs (sku_id, date, unmet_quantity, customer_segment) VALUES (?, ?, ?, ?)", manual_logs)

    # 5. Insert Real Supermarket Khata Ledger
    khata_entries = [
        ("CUST_001", "Ramesh Kumar (Kirana Supply)", "Bulk", 3450.0),
        ("CUST_002", "Sunita Verma (Resident)", "Regular", 1280.0),
        ("CUST_003", "Rajesh Patel (Catering)", "Bulk", 4850.0),
        ("CUST_004", "Priya Sharma (RWA)", "VIP", 890.0),
    ]
    cursor.executemany("INSERT INTO khata_ledger VALUES (?, ?, ?, ?)", khata_entries)

    # 6. Insert Supermarket Promotions
    promotions_data = [
        ("SKU_010", "Independence Day Super Saver (10% OFF)", 10.0, "2026-08-12", "2026-08-16"),
        ("SKU_009", "Cooking Essential Combo (15% OFF)", 15.0, "2026-08-10", "2026-08-18"),
        ("SKU_014", "Monsoon Chiller Offer (12% OFF)", 12.0, "2026-08-14", "2026-08-20"),
    ]
    cursor.executemany("INSERT INTO promotions (sku_id, promo_name, discount_percent, start_date, end_date) VALUES (?, ?, ?, ?, ?)", promotions_data)

    # 7. Insert Holidays & Special Events Calendar
    holidays_data = [
        ("2026-08-15", "Independence Day 2026", "National Holiday", 1.35),
        ("2026-08-25", "Ganesh Chaturthi", "Major Festival", 1.45),
        ("2026-09-05", "Onam / Janmashtami", "Regional Festival", 1.30),
        ("2026-11-08", "Diwali Grand Super Sale", "Grand Festival", 1.65),
    ]
    cursor.executemany("INSERT INTO holidays_calendar VALUES (?, ?, ?, ?)", holidays_data)

    # 8. Insert Supplier Lead Times & MOQ
    lead_time_data = [
        ("SKU_001", 1, 0.2, 20), # Tomatoes daily local farm supply
        ("SKU_002", 2, 0.3, 25),
        ("SKU_003", 2, 0.3, 30),
        ("SKU_004", 1, 0.2, 15),
        ("SKU_005", 1, 0.1, 20), # Daily morning dairy delivery
        ("SKU_006", 2, 0.3, 10),
        ("SKU_007", 1, 0.1, 15), # Fresh bread daily
        ("SKU_008", 1, 0.2, 10),
        ("SKU_009", 3, 0.5, 10),
        ("SKU_010", 3, 0.4, 10),
        ("SKU_011", 3, 0.5, 5),
        ("SKU_012", 4, 0.6, 20),
        ("SKU_013", 3, 0.4, 10),
        ("SKU_014", 2, 0.3, 12),
        ("SKU_015", 2, 0.3, 12),
        ("SKU_016", 2, 0.3, 10),
        ("SKU_017", 2, 0.3, 20),
        ("SKU_018", 2, 0.3, 20),
        ("SKU_019", 4, 0.5, 10),
        ("SKU_020", 3, 0.4, 15),
    ]
    cursor.executemany("INSERT INTO supplier_lead_times VALUES (?, ?, ?, ?)", lead_time_data)

    conn.commit()
    conn.close()
    print("Database inveniq.db successfully updated with real Supermarket data for today (Aug 14, 2026)!")

if __name__ == "__main__":
    populate_database()
