# KiranaIQ Smart Restock — AI Demand Forecasting & Inventory Optimization

**Problem Statement 04**: Based on Gołąbek, Senge, Neumann (2020), *Demand Forecasting using Long Short-Term Memory Neural Networks*, arXiv:2008.08522.

KiranaIQ Smart Restock is an enterprise-grade AI tool designed for Kirana (small retail) shopkeepers in India to predict demand, correct for lost sales due to stockouts, optimize purchase orders under daily budget constraints using cost-aware Newsvendor financial math, and manage customer credit (Khata) ledgers.

---

## 🏗️ Architecture & Model Design

```
+-----------------------------------------------------------------------+
|                    KiranaIQ Frontend Dashboard (index.html)            |
+-----------------------------------------------------------------------+
                                   | (REST API Calls)
                                   v
+-----------------------------------------------------------------------+
|                       FastAPI Backend (main.py)                       |
+-----------------------------------------------------------------------+
    |                             |                            |
    v                             v                            v
[AI Forecasting Engine]   [Newsvendor Optimizer]      [NVIDIA NIM Insights]
 (LSTM / Ridge Reg)     (Critical Fractile / VaR)       (Llama 3.1 8B)
    |                             |                            |
    +-----------------------------+----------------------------+
                                  |
                                  v
+-----------------------------------------------------------------------+
|               Model Context Protocol (MCP) Server Layer                |
|                           (mcp_server.py)                             |
+-----------------------------------------------------------------------+
            | (Default Demo Backend)          | (Enterprise Backend)
            v                                 v
     [SQLite: inveniq.db]              [SAP / Enterprise ERP API]
```

### 🔌 Standalone vs. Enterprise-Integrable MCP Decoupling
The core architectural feature of KiranaIQ Smart Restock is the **Model Context Protocol (MCP) Server Layer** (`mcp_server.py`).

- **Decoupled Data Access**: All FastAPI backend handlers in `main.py` interact exclusively with standardized MCP tools (e.g. `get_sales_history`, `get_current_stock`, `get_product_cost`, `log_manual_demand`, `get_khata_ledger`) rather than querying the database directly.
- **Plug-and-Play ERP Integration**: Out of the box, `mcp_server.py` queries `inveniq.db` (SQLite) for standalone demo use. To integrate with an enterprise ERP (e.g., SAP, Oracle, Odoo), only the internal tool implementations in `mcp_server.py` need to be redirected to ERP REST/gRPC endpoints — **zero changes are required in `main.py`, the AI engines, or the frontend dashboard**.

---

## ⚡ Quickstart & Running the App

### Prerequisites
Python 3.10+ installed. Install dependencies:
```bash
pip install -r requirements.txt
```

### Starting the Application Server
Run either of the following commands to start the FastAPI server:

```bash
# Option 1: Direct Python entrypoint
python main.py

# Option 2: Uvicorn module
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser to: **[http://localhost:8000/](http://localhost:8000/)**

> **Automatic DB Seeding**: On a fresh clone, `main.py` detects if `inveniq.db` is missing and automatically seeds it with sample SKU data, 60 days of sales history, supplier lead times, and Khata ledger entries. Zero manual setup required!

---

## 🛠️ MCP Standalone Tool Testing

You can test the MCP data access layer independently from the web app:

```bash
python test_mcp.py
```

This validates all 6 core MCP tools:
1. `get_all_skus()`
2. `get_product_cost(sku_id)`
3. `get_current_stock(sku_id)`
4. `get_sales_history(sku_id)`
5. `log_manual_demand(sku_id, date_str, unmet_qty)`
6. `get_khata_ledger()`

---

## 📊 Core Features & Algorithmic Math

### 1. Hybrid Neural Forecasting Engine (`ai_engine.py`)
- **LSTM Neural Network**: Trained on time-series windowed sales for stable SKUs (Rice, Milk, Staples).
- **Ridge Regression**: Handles volatile/elastic items (Beverages, Snacks) without overfitting.
- **Censored Demand Correction**: Adjusts historical sales upward by incorporating lost customer demand from `manual_demand_logs`: $\text{True Demand} = \text{Sales} + \text{Unmet Demand}$.
- **Multi-Factor Multipliers**: Dynamically adjusts forecasts based on weather (OpenWeatherMap API), Day-of-Week seasonality, promotional elasticity ($E_d = 1.5$), and Indian holiday/festival calendar.
- **Uncertainty Bands & Anomaly Detection**: Computes 95% Confidence Intervals (`confidence_interval`) and flags regime changes/spikes (`anomaly_flag`, `anomaly_reason`).

### 2. Cost-Aware Newsvendor & Portfolio Optimizer (`newsvendor_engine.py`)
- **Critical Fractile (CF)**: Computes optimal service level targets using asymmetric costs:
  $$C_u = \text{selling\_price} - \text{unit\_cost} \quad \text{(Underage Lost Profit)}$$
  $$C_o = \text{unit\_cost} \times 0.30 \quad \text{(Overage Spoilage/Holding Cost)}$$
  $$\text{CF} = \frac{C_u}{C_u + C_o}$$
- **Markowitz Mean-Variance Budget Allocation**: Ranks candidate orders by Risk-Adjusted Sharpe Ratio and allocates daily shopkeeper budget.
- **Khata Reserve**: Deducts 10% of customer credit balance to protect cash flow.
- **Substitute Correlation Discount**: Reduces order quantities by 10% when substitute items are co-ordered in a single restock plan.
- **Financial Risk Metrics**: Computes Portfolio Expected Profit and 95% Value at Risk (VaR) downside loss bounds.

---

## 🧪 Running Integration Tests

Run the backend API integration test suite:

```bash
python test_backend.py
```
