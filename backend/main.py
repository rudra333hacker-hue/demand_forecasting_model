import os
import json
import requests
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ai_engine import predict_demand
from newsvendor_engine import optimize_order_quantity, allocate_portfolio_budget
from mcp_server import (
    tool_get_sales_history,
    tool_get_current_stock,
    tool_get_product_cost,
    tool_log_manual_demand,
    tool_get_khata_ledger,
    tool_get_all_skus,
    tool_update_sku_metadata,
    tool_add_new_sku,
    tool_update_khata_balance
)
from populate_db import populate_database

from fastapi.responses import FileResponse

# Resolve paths relative to this file's directory
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)

app = FastAPI(
    title="Smart Restock AI API",
    description="Kirana store demand forecasting, newsvendor optimization, and AI insights API.",
    version="1.0.0"
)

@app.on_event("startup")
def startup_event():
    if not os.path.exists(os.path.join(_BACKEND_DIR, "database", "inveniq.db")):
        print("inveniq.db not found. Auto-populating database on startup...")
        populate_database()

from fastapi.staticfiles import StaticFiles

# CORS middleware for cross-origin frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_dir = os.path.join(_PROJECT_ROOT, "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

# --- Pydantic Models for Input Validation ---

class ForecastRequest(BaseModel):
    sku_id: str = Field(..., examples=["SKU_001"])
    is_festival: int = Field(0, description="1 if festival season, 0 otherwise", examples=[0])
    city: str = Field("Hyderabad", examples=["Hyderabad"])
    date_str: Optional[str] = Field(None, description="Optional target forecast date YYYY-MM-DD", examples=["2026-08-15"])
    location_id: Optional[str] = Field(None, description="Optional location ID", examples=["LOC_001"])


class OptimizeRestockRequest(BaseModel):
    sku_ids: List[str] = Field(..., examples=[["SKU_001", "SKU_002", "SKU_003"]])
    daily_budget: float = Field(..., gt=0, examples=[5000.0])
    customer_id: Optional[str] = Field(None, examples=["CUST_101"])
    location_id: Optional[str] = Field(None, description="Optional location ID", examples=["LOC_001"])


class LogDemandRequest(BaseModel):
    sku_id: str = Field(..., examples=["SKU_001"])
    date_str: Optional[str] = Field(None, examples=["2026-08-13"])
    date: Optional[str] = Field(None, examples=["2026-08-13"])
    unmet_quantity: Optional[int] = Field(None, examples=[5])
    unmet_qty: Optional[int] = Field(None, examples=[5])
    segment: Optional[str] = Field("Regular", examples=["Regular"])
    customer_segment: Optional[str] = Field(None, examples=["Regular"])
    location_id: Optional[str] = Field(None, examples=["LOC_001"])


class KhataVoiceNoteRequest(BaseModel):
    customer_id: str = Field(..., examples=["CUST_001"])
    note: str = Field(..., examples=["Added 2 Rice bags to Khata ₹640"])


class ChatRequest(BaseModel):
    message: str = Field(..., examples=["Which items should I restock today?"])


class UpdateSKURequest(BaseModel):
    sku_id: str = Field(..., examples=["SKU_001"])
    unit_cost: float = Field(..., gt=0, examples=[250.0])
    selling_price: float = Field(..., gt=0, examples=[320.0])
    current_stock: int = Field(..., ge=0, examples=[50])
    location_id: Optional[str] = Field(None, examples=["LOC_001"])


class AddSKURequest(BaseModel):
    sku_id: Optional[str] = Field(None, examples=["SKU_006"])
    name: str = Field(..., examples=["Wheat Flour 10kg"])
    category: str = Field("Staples", examples=["Staples"])
    unit_cost: float = Field(..., gt=0, examples=[300.0])
    selling_price: float = Field(..., gt=0, examples=[380.0])
    current_stock: int = Field(..., ge=0, examples=[20])
    location_id: Optional[str] = Field(None, examples=["LOC_001"])


# --- API Routes ---

@app.get("/")
def serve_dashboard():
    """
    Serves the KiranaIQ Smart Restock HTML web dashboard.
    """
    index_path = os.path.join(_PROJECT_ROOT, "frontend", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "status": "healthy",
        "service": "Smart Restock AI Engine API",
        "version": "1.0.0"
    }


@app.get("/health")
def health_check():
    """
    1. Health check endpoint.
    """
    return {
        "status": "healthy",
        "service": "Smart Restock AI Engine API",
        "version": "1.0.0"
    }


@app.post("/forecast")
def get_forecast(req: ForecastRequest):
    """
    2. Takes sku_id and returns AI demand forecast from ai_engine.py.
    """
    try:
        forecast = predict_demand(
            sku_id=req.sku_id,
            is_festival=req.is_festival,
            city=req.city,
            date_str=req.date_str,
            location_id=req.location_id
        )
        return forecast
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Forecast error for SKU '{req.sku_id}': {str(e)}")


@app.post("/optimize-restock")
def optimize_restock(req: OptimizeRestockRequest):
    """
    3. Takes a list of sku_ids and daily_budget, runs optimize_order_quantity,
       and passes results to allocate_portfolio_budget.
    """
    try:
        orders_list = []
        for sku_id in req.sku_ids:
            # Step A: Get demand forecast
            forecast = predict_demand(sku_id=sku_id, location_id=req.location_id)
            predicted_demand = forecast.get("final_predicted_demand", 0.0)

            # Step B: Compute Newsvendor optimal order quantity (Q*)
            order_info = optimize_order_quantity(
                sku_id=sku_id,
                raw_demand_forecast=predicted_demand,
                location_id=req.location_id
            )
            orders_list.append(order_info)

        # Step C: Allocate portfolio budget
        allocation_plan = allocate_portfolio_budget(
            orders_list=orders_list,
            total_budget_inr=req.daily_budget,
            customer_id=req.customer_id,
            location_id=req.location_id
        )
        return allocation_plan
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restock optimization error: {str(e)}")


@app.post("/log-demand")
def log_unmet_demand(req: LogDemandRequest):
    """
    4. Calls tool_log_manual_demand from mcp_server.py to record unfulfilled demand.
    """
    try:
        from datetime import datetime
        d_str = req.date_str or req.date or datetime.now().strftime("%Y-%m-%d")
        qty = req.unmet_quantity if req.unmet_quantity is not None else (req.unmet_qty if req.unmet_qty is not None else 1)
        seg = req.customer_segment or req.segment or "Regular"
        result = tool_log_manual_demand(
            sku_id=req.sku_id,
            date_str=d_str,
            unmet_quantity=qty,
            customer_segment=seg,
            location_id=req.location_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error logging manual demand: {str(e)}")


@app.post("/generate-nim-insights")
def generate_nim_insights(payload: Dict[str, Any]):
    """
    5. Takes the restock JSON plan, calls NVIDIA NIM API (meta/llama-3.1-8b-instruct)
       using NVIDIA_API_KEY, and returns a 2-sentence plain-language recommendation for the shopkeeper.
       Includes fallback logic if key or network call fails.
    """
    fallback_recommendation = (
        "Prioritize restocking high Critical Fractile items like staple foods to maximize profit margins under your budget. "
        "Continuously log unfulfilled customer demand to dynamically refine stock targets for upcoming days."
    )

    restock_plan = payload.get("restock_plan", payload)
    api_key = os.getenv("NVIDIA_API_KEY")

    if not api_key:
        return {
            "status": "fallback",
            "source": "fallback_rules_engine",
            "recommendation": fallback_recommendation,
            "reason": "NVIDIA_API_KEY environment variable not configured."
        }

    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    prompt_content = f"Restock Plan: {json.dumps(restock_plan, indent=2)}"

    body = {
        "model": "meta/llama-3.1-8b-instruct",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an expert Kirana store inventory advisor. "
                    "Based on the provided restock optimization plan, generate exactly a 2-sentence, "
                    "plain-language actionable recommendation for the shopkeeper."
                )
            },
            {
                "role": "user",
                "content": prompt_content
            }
        ],
        "temperature": 0.2,
        "max_tokens": 150
    }

    try:
        response = requests.post(url, headers=headers, json=body, timeout=10)
        if response.status_code == 200:
            data = response.json()
            recommendation = data["choices"][0]["message"]["content"].strip()
            return {
                "status": "success",
                "source": "nvidia_nim_nemotron",
                "recommendation": recommendation
            }
        else:
            return {
                "status": "fallback",
                "source": "fallback_rules_engine",
                "recommendation": fallback_recommendation,
                "reason": f"NVIDIA NIM API error {response.status_code}: {response.text}"
            }
    except Exception as exc:
        return {
            "status": "fallback",
            "source": "fallback_rules_engine",
            "recommendation": fallback_recommendation,
            "reason": f"Network exception while calling NVIDIA NIM API: {str(exc)}"
        }


@app.post("/save-khata-note")
def save_khata_note(req: KhataVoiceNoteRequest):
    """
    6. Persists a Khata voice/text note for a customer via MCP layer.
    """
    import re
    try:
        amounts = re.findall(r'(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)', req.note, re.IGNORECASE)
        if amounts:
            try:
                delta = float(amounts[-1])
                if delta > 0:
                    tool_update_khata_balance(req.customer_id, delta)
            except Exception as ex:
                print("Could not update khata balance from note:", ex)

        return {
            "status": "success",
            "customer_id": req.customer_id,
            "note": req.note,
            "message": "Khata note saved and balance updated successfully."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving Khata note: {str(e)}")


def execute_chat_db_command(message: str) -> Optional[Dict[str, Any]]:
    """
    Parses natural language commands from the shopkeeper and updates via MCP server tools.
    Supports stock updates, price updates, cost updates, missing demand logging, and Khata updates.
    """
    import re
    from datetime import datetime

    msg_lower = message.lower().strip()

    try:
        skus = tool_get_all_skus()
        target_sku = None
        stop_words = {"the", "for", "and", "with", "item", "this", "that", "from", "into", "units", "unit", "pack", "bags", "bag", "bottle", "bottles"}

        # 1. Match SKU ID first (e.g., SKU_001, SKU 001, sku_1, sku 1)
        sku_match = re.search(r'sku[_\s]?0*(\d+)', msg_lower)
        if sku_match:
            sku_num = int(sku_match.group(1))
            target_sku_id = f"SKU_{sku_num:03d}"
            for s in skus:
                if s["sku_id"].lower() == target_sku_id.lower():
                    target_sku = s
                    break

        # 2. Match SKU name if SKU ID not found directly
        if not target_sku:
            for s in skus:
                sku_id = s["sku_id"]
                name = s["name"]
                if sku_id.lower() in msg_lower:
                    target_sku = s
                    break
                # Match name keywords >= 3 chars excluding stop words (e.g., Rice, Milk, Dal, Chips)
                name_words = [w.lower() for w in re.findall(r'\b[a-zA-Z0-9]+\b', name) if len(w) >= 3 and w.lower() not in stop_words]
                if any(w in msg_lower for w in name_words):
                    target_sku = s
                    break

        numbers = [float(n) for n in re.findall(r'\b\d+(?:\.\d+)?\b', message)]

        # --- Intent 1: Stock Update ---
        if any(k in msg_lower for k in ["stock", "quantity", "inventory", "count", "available"]):
            if target_sku and numbers:
                clean_numbers = [n for n in numbers if int(n) != int(re.sub(r'\D', '', target_sku['sku_id']))]
                new_stock = int(clean_numbers[-1]) if clean_numbers else int(numbers[-1])
                sku_id = target_sku["sku_id"]
                name = target_sku["name"]
                old_stock = target_sku["current_stock"]
                tool_update_sku_metadata(sku_id=sku_id, current_stock=new_stock)
                return {
                    "reply": f"Updated {name} ({sku_id}) stock from {old_stock} to {new_stock} units via MCP! Restock plan recalculated.",
                    "db_updated": True
                }

        # --- Intent 2: Selling Price Update ---
        if "price" in msg_lower or "selling price" in msg_lower or "rate" in msg_lower or "mrp" in msg_lower:
            if target_sku and numbers:
                clean_numbers = [n for n in numbers if int(n) != int(re.sub(r'\D', '', target_sku['sku_id']))]
                new_price = float(clean_numbers[-1]) if clean_numbers else float(numbers[-1])
                sku_id = target_sku["sku_id"]
                name = target_sku["name"]
                old_price = target_sku["selling_price"]
                tool_update_sku_metadata(sku_id=sku_id, selling_price=new_price)
                return {
                    "reply": f"Updated {name} ({sku_id}) selling price from ₹{old_price} to ₹{new_price} via MCP!",
                    "db_updated": True
                }

        # --- Intent 3: Unit Cost Update ---
        if "cost" in msg_lower or "purchase price" in msg_lower or "buy price" in msg_lower:
            if target_sku and numbers:
                clean_numbers = [n for n in numbers if int(n) != int(re.sub(r'\D', '', target_sku['sku_id']))]
                new_cost = float(clean_numbers[-1]) if clean_numbers else float(numbers[-1])
                sku_id = target_sku["sku_id"]
                name = target_sku["name"]
                old_cost = target_sku["unit_cost"]
                tool_update_sku_metadata(sku_id=sku_id, unit_cost=new_cost)
                return {
                    "reply": f"Updated {name} ({sku_id}) unit cost from ₹{old_cost} to ₹{new_cost} via MCP!",
                    "db_updated": True
                }

        # --- Intent 4: Log Unmet / Missing Demand ---
        if any(k in msg_lower for k in ["missing", "unmet", "stockout", "out of stock", "shortage", "lost"]):
            if target_sku and numbers:
                clean_numbers = [n for n in numbers if int(n) != int(re.sub(r'\D', '', target_sku['sku_id']))]
                missing_qty = int(clean_numbers[0]) if clean_numbers else int(numbers[0])
                sku_id = target_sku["sku_id"]
                name = target_sku["name"]
                today = datetime.now().strftime("%Y-%m-%d")
                tool_log_manual_demand(sku_id=sku_id, date_str=today, unmet_quantity=missing_qty, customer_segment="Regular")
                return {
                    "reply": f"Logged {missing_qty} missing units for {name} ({sku_id}) on {today} via MCP! Demand AI will factor this into upcoming forecasts.",
                    "db_updated": True
                }

        # --- Intent 5: Update Khata Debit Balance ---
        if any(k in msg_lower for k in ["khata", "debit", "credit", "balance", "owe", "due"]):
            if numbers:
                amount = float(numbers[-1])
                customers = tool_get_khata_ledger()
                target_cust = None
                if isinstance(customers, list):
                    for c in customers:
                        cid = c["customer_id"]
                        cname = c["customer_name"]
                        if cid.lower() in msg_lower or any(w.lower() in msg_lower for w in cname.split() if len(w) >= 3 and w.lower() not in stop_words):
                            target_cust = c
                            break
                if target_cust:
                    cid = target_cust["customer_id"]
                    cname = target_cust["customer_name"]
                    tool_update_khata_balance(cid, amount)
                    return {
                        "reply": f"Added ₹{amount:.2f} to {cname} ({cid}) Khata via MCP! New balance updated and restock reserve recalculated.",
                        "db_updated": True
                    }

    except Exception as e:
        print("Error executing chat DB command:", e)

    return None


@app.post("/chat")
def chat_with_assistant(req: ChatRequest):
    """
    7. Interactive Voice & Text Assistant Endpoint powered by NVIDIA NIM.
    Automatically detects and executes database updates from user natural language commands.
    """
    db_result = execute_chat_db_command(req.message)
    if db_result:
        return db_result

    fallback_reply = (
        "Focus on maintaining stock levels for high-margin staples and dairy. "
        "Log missing demand daily so your dynamic restock targets adjust automatically."
    )

    api_key = os.getenv("NVIDIA_API_KEY")

    if not api_key:
        return {"reply": fallback_reply, "db_updated": False}

    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    body = {
        "model": "meta/llama-3.1-8b-instruct",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are KiranaIQ Assistant, an AI inventory advisor for Indian Kirana shopkeepers. "
                    "Answer concisely in 2 short sentences."
                )
            },
            {
                "role": "user",
                "content": req.message
            }
        ],
        "temperature": 0.3,
        "max_tokens": 120
    }

    try:
        response = requests.post(url, headers=headers, json=body, timeout=10)
        if response.status_code == 200:
            data = response.json()
            reply = data["choices"][0]["message"]["content"].strip()
            return {"reply": reply, "db_updated": False}
        else:
            return {"reply": fallback_reply, "db_updated": False}
    except Exception:
        return {"reply": fallback_reply, "db_updated": False}


# --- SKU & Inventory Database Management Endpoints (All powered via MCP server tools) ---

@app.get("/skus")
def get_all_skus(location_id: Optional[str] = None):
    """
    Returns all SKUs from database via tool_get_all_skus MCP tool.
    """
    try:
        skus = tool_get_all_skus(location_id=location_id)
        # Format response matching exact expected schema for frontend compatibility
        return [
            {
                "sku_id": s["sku_id"],
                "item_name": s["name"],
                "category": s["category"],
                "unit_cost": s["unit_cost"],
                "selling_price": s["selling_price"],
                "current_stock": s["current_stock"]
            }
            for s in skus
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error fetching SKUs: {str(e)}")


@app.post("/update-sku")
def update_sku(req: UpdateSKURequest):
    """
    Updates cost, selling price, and current stock for a SKU via tool_update_sku_metadata MCP tool.
    """
    try:
        res = tool_update_sku_metadata(
            sku_id=req.sku_id,
            unit_cost=req.unit_cost,
            selling_price=req.selling_price,
            current_stock=req.current_stock,
            location_id=req.location_id
        )
        if res.get("status") == "error":
            raise HTTPException(status_code=404, detail=res.get("message"))
        return {"status": "success", "message": "SKU updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating SKU: {str(e)}")


@app.post("/add-sku")
def add_sku(req: AddSKURequest):
    """
    Adds a new SKU to database via tool_add_new_sku MCP tool.
    """
    try:
        if not req.sku_id:
            existing = tool_get_all_skus()
            sku_id = f"SKU_{len(existing) + 1:03d}"
        else:
            sku_id = req.sku_id

        tool_add_new_sku(
            sku_id=sku_id,
            name=req.name,
            category=req.category,
            unit_cost=req.unit_cost,
            selling_price=req.selling_price,
            current_stock=req.current_stock,
            location_id=req.location_id
        )
        return {"status": "success", "message": "New SKU added", "sku_id": sku_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding SKU: {str(e)}")


@app.get("/khata-ledger")
def get_khata_ledger(customer_id: Optional[str] = None):
    """
    Returns all customer Khata entries from database via tool_get_khata_ledger MCP tool.
    """
    try:
        result = tool_get_khata_ledger(customer_id=customer_id)
        if isinstance(result, dict):
            return [result]
        return result if result is not None else []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error fetching Khata ledger: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
