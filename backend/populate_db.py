import csv
import sqlite3
import datetime
import random
import os
from pathlib import Path

def parse_date(date_str):
    # Handle formats like '11-08-2017', '4/15/2018', '06-09-2015', '11/22/2016'
    for fmt in ("%d-%m-%Y", "%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            pass
    return datetime.date(2026, 8, 14)

def update_db_from_csv():
    backend_dir = Path(__file__).parent.resolve()
    csv_path = backend_dir / "data" / "sales_data.csv"
    db_path = backend_dir / "database" / "inveniq.db"

    if not csv_path.exists():
        print(f"CSV file not found at {csv_path}")
        return

    print(f"Reading sales data from {csv_path}...")
    
    # Category and Sub-category to SKU mapping
    sku_mapping = {
        ("Fruits & Veggies", "Fresh Vegetables"): ("SKU_001", "Fresh Farm Tomatoes 1kg", 28.0, 40.0),
        ("Fruits & Veggies", "Organic Vegetables"): ("SKU_002", "Red Onions 1kg", 24.0, 35.0),
        ("Fruits & Veggies", "Fresh Fruits"): ("SKU_003", "Fresh Potatoes 1kg", 20.0, 30.0),
        ("Fruits & Veggies", "Organic Fruits"): ("SKU_004", "Robusta Bananas 1 Dozen", 35.0, 50.0),
        ("Dairy", "Health Drinks"): ("SKU_005", "Amul Taaza Toned Milk 1L", 48.0, 56.0),
        ("Dairy", "Butter"): ("SKU_006", "Amul Pasteurised Butter 500g", 240.0, 275.0),
        ("Bakery", "Breads & Buns"): ("SKU_007", "Britannia White Bread 400g", 30.0, 40.0),
        ("Bakery", "Cakes"): ("SKU_008", "Milky Mist Fresh Paneer 200g", 75.0, 95.0),
        ("Oil & Masala", "Edible Oil & Ghee"): ("SKU_009", "Fortune Sunflower Oil 1L", 125.0, 155.0),
        ("Food Grains", "Atta & Flour"): ("SKU_010", "Aashirvaad Atta 10kg", 340.0, 420.0),
        ("Food Grains", "Rice"): ("SKU_011", "India Gate Basmati Rice 5kg", 480.0, 620.0),
        ("Oil & Masala", "Spices"): ("SKU_012", "Tata Iodized Salt 1kg", 20.0, 28.0),
        ("Food Grains", "Dals & Pulses"): ("SKU_013", "Tata Sampann Toor Dal 1kg", 135.0, 175.0),
        ("Beverages", "Soft Drinks"): ("SKU_014", "Coca-Cola Original 1.5L", 60.0, 80.0),
        ("Beverages", "Health Drinks"): ("SKU_015", "Pepsi Soft Drink 1.5L", 58.0, 78.0),
        ("Beverages", "Juices"): ("SKU_016", "Real Orange Juice 1L", 90.0, 125.0),
        ("Snacks", "Noodles"): ("SKU_017", "Maggi Masala Noodles 4-Pack", 42.0, 56.0),
        ("Bakery", "Biscuits"): ("SKU_018", "Britannia Good Day Biscuits 200g", 28.0, 38.0),
        ("Snacks", "Chocolates"): ("SKU_019", "Surf Excel Easy Wash 1kg", 115.0, 145.0),
        ("Snacks", "Cookies"): ("SKU_020", "Dettol Bath Soap Bar 125g", 38.0, 50.0),
    }

    # Default mapping generator for any unknown category/sub-category in CSV
    skus_dict = {}
    sales_rows = []
    
    with open(csv_path, mode="r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cat = row.get("Category", "").strip()
            subcat = row.get("Sub Category", "").strip()
            sales_val = float(row.get("Sales", 0) or 0)
            profit_val = float(row.get("Profit", 0) or 0)
            date_str = row.get("Order Date", "").strip()
            dt = parse_date(date_str)
            dt_iso = dt.strftime("%Y-%m-%d")

            key = (cat, subcat)
            if key in sku_mapping:
                sku_id, name, unit_cost, selling_price = sku_mapping[key]
            else:
                # Dynamically assign SKU
                sku_id = f"SKU_{len(skus_dict) + 1:03d}"
                name = f"{subcat} ({cat})" if subcat else cat
                unit_cost = round(max(10.0, (sales_val - profit_val)), 2)
                selling_price = round(max(15.0, sales_val), 2)

            if sku_id not in skus_dict:
                # Estimate current stock
                stock = random.randint(20, 60)
                sub_id = "SKU_015" if sku_id == "SKU_014" else ("SKU_014" if sku_id == "SKU_015" else None)
                skus_dict[sku_id] = (sku_id, name, cat if cat else "General", unit_cost, selling_price, stock, "LOC_001", sub_id)

            # Estimate quantity sold from sales & unit price
            price = skus_dict[sku_id][4]
            qty = max(1.0, round(sales_val / max(1.0, price), 1))
            sales_rows.append((sku_id, dt_iso, qty))

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS sales_history")
    cursor.execute("DROP TABLE IF EXISTS manual_demand_logs")
    cursor.execute("DROP TABLE IF EXISTS skus")
    cursor.execute("DROP TABLE IF EXISTS khata_ledger")
    cursor.execute("DROP TABLE IF EXISTS promotions")
    cursor.execute("DROP TABLE IF EXISTS holidays_calendar")
    cursor.execute("DROP TABLE IF EXISTS supplier_lead_times")

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

    # Populate skus table
    skus_list = list(skus_dict.values())
    cursor.executemany("INSERT INTO skus VALUES (?, ?, ?, ?, ?, ?, ?, ?)", skus_list)

    # Populate sales_history table
    cursor.executemany("INSERT INTO sales_history (sku_id, date, quantity_sold) VALUES (?, ?, ?)", sales_rows)

    # Populate manual demand logs
    manual_logs = [
        ("SKU_005", "2026-08-14", 12, "Regular"),
        ("SKU_010", "2026-08-14", 8, "Bulk Kirana"),
        ("SKU_001", "2026-08-13", 6, "Regular"),
        ("SKU_014", "2026-08-13", 10, "VIP"),
    ]
    cursor.executemany("INSERT INTO manual_demand_logs (sku_id, date, unmet_quantity, customer_segment) VALUES (?, ?, ?, ?)", manual_logs)

    # Populate khata_ledger
    khata_entries = [
        ("CUST_001", "Ramesh Kumar (Kirana Supply)", "Bulk", 3450.0),
        ("CUST_002", "Sunita Verma (Resident)", "Regular", 1280.0),
        ("CUST_003", "Rajesh Patel (Catering)", "Bulk", 4850.0),
        ("CUST_004", "Priya Sharma (RWA)", "VIP", 890.0),
    ]
    cursor.executemany("INSERT INTO khata_ledger VALUES (?, ?, ?, ?)", khata_entries)

    # Populate promotions
    promotions_data = [
        ("SKU_010", "Independence Day Super Saver (10% OFF)", 10.0, "2026-08-12", "2026-08-16"),
        ("SKU_009", "Cooking Essential Combo (15% OFF)", 15.0, "2026-08-10", "2026-08-18"),
        ("SKU_014", "Monsoon Chiller Offer (12% OFF)", 12.0, "2026-08-14", "2026-08-20"),
    ]
    cursor.executemany("INSERT INTO promotions (sku_id, promo_name, discount_percent, start_date, end_date) VALUES (?, ?, ?, ?, ?)", promotions_data)

    # Populate holidays_calendar
    holidays_data = [
        ("2026-08-15", "Independence Day 2026", "National Holiday", 1.35),
        ("2026-08-25", "Ganesh Chaturthi", "Major Festival", 1.45),
        ("2026-09-05", "Onam / Janmashtami", "Regional Festival", 1.30),
        ("2026-11-08", "Diwali Grand Super Sale", "Grand Festival", 1.65),
    ]
    cursor.executemany("INSERT INTO holidays_calendar VALUES (?, ?, ?, ?)", holidays_data)

    # Populate supplier lead times
    lead_time_data = [
        (s[0], random.choice([1, 2, 3]), 0.3, 10) for s in skus_list
    ]
    cursor.executemany("INSERT INTO supplier_lead_times VALUES (?, ?, ?, ?)", lead_time_data)

    conn.commit()
    conn.close()
    print(f"Successfully processed CSV ({len(sales_rows)} sales records) and updated inveniq.db with {len(skus_list)} SKUs!")

def populate_database():
    update_db_from_csv()

if __name__ == "__main__":
    populate_database()
