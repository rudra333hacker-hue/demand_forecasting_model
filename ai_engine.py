from typing import Optional, Union, Dict, Any, List
import sqlite3
import os
import json
import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

from mcp_server import (
    tool_get_sales_history,
    tool_get_product_cost,
    tool_log_manual_demand,
    tool_get_khata_balance,
    tool_get_promotions,
    tool_get_holiday_event,
    DB_PATH
)

# Suppress TensorFlow logging & set CPU execution
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

def get_weather_features(city: str = "Hyderabad") -> dict:
    """
    Fetches current weather features from OpenWeatherMap API.
    Includes fallback default values if API key is missing or request fails.
    """
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if api_key:
        try:
            url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric"
            response = requests.get(url, timeout=3)
            if response.status_code == 200:
                data = response.json()
                temp = data["main"]["temp"]
                weather_main = data["weather"][0]["main"].lower()
                is_rain = 1 if "rain" in weather_main or "drizzle" in weather_main else 0
                return {"temperature": temp, "is_rain": is_rain, "source": "openweathermap_api"}
        except Exception:
            pass

    # Kirana domain fallback defaults (Warm Hyderabad summer day)
    return {"temperature": 32.0, "is_rain": 0, "source": "fallback_default"}


def get_sku_metadata(sku_id: str) -> dict:
    """
    Queries SQLite database to fetch category and stock metadata for a given SKU.
    """
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name, category, unit_cost, selling_price, current_stock FROM skus WHERE sku_id = ?", (sku_id,))
        row = cursor.fetchone()

    if row:
        return {
            "name": row[0],
            "category": row[1],
            "unit_cost": row[2],
            "selling_price": row[3],
            "current_stock": row[4]
        }
    if "001" in sku_id or "002" in sku_id or "005" in sku_id:
        return {"name": f"Item {sku_id}", "category": "Staples", "unit_cost": 100.0, "selling_price": 130.0, "current_stock": 50}
    else:
        return {"name": f"Item {sku_id}", "category": "Beverages", "unit_cost": 50.0, "selling_price": 70.0, "current_stock": 30}


def get_censored_demand_map(sku_id: str) -> dict:
    """
    Ingests unfulfilled demand counts from manual_demand_logs table.
    Returns a dictionary mapping date -> unmet_quantity.
    """
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT date, SUM(unmet_quantity) FROM manual_demand_logs WHERE sku_id = ? GROUP BY date", (sku_id,))
        rows = cursor.fetchall()
    return {r[0]: r[1] for r in rows}


def build_true_demand_series(sku_id: str, limit: int = 60) -> pd.DataFrame:
    """
    Pulls sales history via tool_get_sales_history() and adds unmet demand back
    to actual sales to compute TRUE total latent demand.
    """
    raw_history = tool_get_sales_history(sku_id, limit=limit)
    if not raw_history:
        dates = pd.date_range(end=pd.Timestamp.now(), periods=30, freq='D').strftime("%Y-%m-%d")
        df = pd.DataFrame({"date": dates, "quantity_sold": [40.0] * 30})
    else:
        df = pd.DataFrame(raw_history)
        df = df.sort_values(by="date").reset_index(drop=True)

    unmet_map = get_censored_demand_map(sku_id)
    df["unmet_quantity"] = df["date"].map(lambda d: unmet_map.get(d, 0))
    df["true_demand"] = df["quantity_sold"] + df["unmet_quantity"]
    return df


# Cache for trained LSTM models to avoid retraining on every request
_lstm_model_cache = {}

def predict_lstm(demand_series: np.ndarray, window_size: int = 7, cache_key: Optional[str] = None) -> float:
    """
    Trains a TensorFlow/Keras LSTM model on sequence windowed daily demand data
    for Stable SKUs (Staples, Dairy, Rice).
    Uses a per-SKU model cache to avoid retraining on every request.
    """
    import tensorflow as tf

    tf.random.set_seed(42)
    np.random.seed(42)

    values = demand_series.astype(np.float32)
    if len(values) == 0:
        return 0.0
    mean_val = float(np.mean(values))
    std_val = float(np.std(values)) if np.std(values) > 0 else 1.0
    scaled_values = (values - mean_val) / std_val

    X, y = [], []
    for i in range(len(scaled_values) - window_size):
        X.append(scaled_values[i : i + window_size])
        y.append(scaled_values[i + window_size])

    if len(X) == 0:
        return float(demand_series[-1]) if len(demand_series) > 0 else 0.0

    X = np.array(X)[..., np.newaxis]  # shape: (samples, window_size, 1)
    y = np.array(y)

    # Use cached model if available for this SKU, otherwise train and cache
    if cache_key and cache_key in _lstm_model_cache:
        model = _lstm_model_cache[cache_key]
    else:
        from keras.models import Sequential
        from keras.layers import LSTM, Dense, Input

        model = Sequential([
            Input(shape=(window_size, 1)),
            LSTM(16, activation='relu'),
            Dense(1)
        ])
        model.compile(optimizer='adam', loss='mse')
        model.fit(X, y, epochs=10, verbose=0, batch_size=8)
        if cache_key:
            _lstm_model_cache[cache_key] = model

    last_window = scaled_values[-window_size:].reshape(1, window_size, 1)
    pred_scaled = float(model.predict(last_window, verbose=0)[0][0])
    pred_raw = (pred_scaled * std_val) + mean_val
    return float(max(0.0, pred_raw))


def predict_ridge_regression(demand_series: np.ndarray, window_size: int = 7) -> float:
    """
    Uses a Scikit-Learn / Ridge Regression model to handle high variance without overfitting
    for Price-Elastic / Volatile SKUs (Beverages, Snacks).
    """
    values = demand_series.astype(np.float32)
    if len(values) == 0:
        return 0.0
    X, y = [], []
    for i in range(len(values) - window_size):
        X.append(values[i : i + window_size])
        y.append(values[i + window_size])

    if len(X) == 0:
        return float(demand_series[-1]) if len(demand_series) > 0 else 0.0

    X = np.array(X)
    y = np.array(y)

    try:
        from sklearn.linear_model import Ridge
        model = Ridge(alpha=1.0)
        model.fit(X, y)
        last_window = values[-window_size:].reshape(1, -1)
        pred_raw = float(model.predict(last_window)[0])
    except Exception:
        # Analytical NumPy closed-form Ridge Regression fallback: beta = (X^T X + alpha*I)^(-1) X^T y
        alpha = 1.0
        X_b = np.hstack([np.ones((X.shape[0], 1)), X])
        last_window_b = np.hstack([1.0, values[-window_size:]])
        beta = np.linalg.inv(X_b.T @ X_b + alpha * np.eye(X_b.shape[1])) @ X_b.T @ y
        pred_raw = float(last_window_b @ beta)

    return float(max(0.0, pred_raw))


def calculate_weather_multiplier(weather: dict, category: str) -> float:
    """
    Computes numerical weather multiplier based on temperature and rain.
    """
    temp = weather.get("temperature", 32.0)
    is_rain = weather.get("is_rain", 0)

    category_lower = category.lower()
    multiplier = 1.0

    # Temperature Effect
    if "beverage" in category_lower or "snack" in category_lower:
        if temp > 30.0:
            multiplier += 0.15  # Hot weather increases beverage consumption
        elif temp < 20.0:
            multiplier -= 0.10
    else:
        # Staples / Dairy
        if temp > 35.0:
            multiplier += 0.05

    # Rain Effect
    if is_rain == 1:
        if "beverage" in category_lower:
            multiplier *= 0.90  # Rain lowers cold drink sales
        elif "snack" in category_lower or "staple" in category_lower:
            multiplier *= 1.10  # Rain boosts indoor snack cooking

    return round(multiplier, 2)


def calculate_day_of_week_multiplier(date_str: Optional[str] = None, category: str = "Staples") -> float:
    """
    Computes Day-of-Week (DOW) seasonality multiplier.
    Saturdays/Sundays boost snacks and beverages by +20%, staples remain steady (+0%).
    """
    if not date_str:
        dt = pd.Timestamp.now()
    else:
        try:
            dt = pd.to_datetime(date_str)
        except Exception:
            dt = pd.Timestamp.now()

    day_of_week = dt.dayofweek  # 0=Mon, 5=Sat, 6=Sun
    category_lower = category.lower()

    if day_of_week in [5, 6]:  # Weekend
        if "beverage" in category_lower or "snack" in category_lower:
            return 1.20
        elif "dairy" in category_lower:
            return 1.10
    return 1.00


def calculate_promo_multiplier(sku_id: str, date_str: Optional[str] = None) -> float:
    """
    Computes Promotional Discount Elasticity multiplier via tool_get_promotions.
    Price Elasticity of Demand (Ed): % Delta Q = Ed * % Delta P (assuming Ed = 1.5).
    """
    try:
        promos = tool_get_promotions(sku_id, date_str)
        if not promos:
            return 1.00

        total_discount = sum(p.get("discount_percent", 0.0) for p in promos)
        elasticity_boost = 1.0 + (1.5 * (total_discount / 100.0))
        return round(elasticity_boost, 2)
    except Exception:
        return 1.00


def calculate_holiday_multiplier(date_str: Optional[str] = None, is_festival: int = 0) -> float:
    """
    Queries holidays_calendar database or checks festival flag for major Indian events.
    """
    try:
        holiday_info = tool_get_holiday_event(date_str) if date_str else None
        if holiday_info:
            return holiday_info.get("multiplier", 1.0)
    except Exception:
        pass

    return 1.25 if is_festival == 1 else 1.00


def predict_demand(
    sku_id: str,
    is_festival: int = 0,
    city: str = "Hyderabad",
    date_str: Optional[str] = None
) -> dict:
    """
    Main Multi-Factor Demand Forecasting Engine:
    1. Detects item category (Staple vs. Beverage/Volatile).
    2. Reconstructs latent true demand from sales history + unmet stockouts.
    3. Runs inference on neural LSTM vs. Ridge Regression.
    4. Evaluates Weather, Holiday/Event, Promotional Elasticity, and Day-of-Week Seasonality Multipliers.
    5. Returns transparent multi-factor breakdown.
    """
    metadata = get_sku_metadata(sku_id)
    category = metadata.get("category", "Staples")
    category_lower = category.lower()

    is_stable_sku = any(cat in category_lower for cat in ["staple", "dairy", "rice", "dal", "flour"])

    df_demand = build_true_demand_series(sku_id, limit=60)
    demand_series = df_demand["true_demand"].values

    if is_stable_sku:
        predicted_demand_raw = predict_lstm(demand_series, window_size=7, cache_key=sku_id)
        model_used = "LSTM"
    else:
        predicted_demand_raw = predict_ridge_regression(demand_series, window_size=7)
        model_used = "Regression"

    weather = get_weather_features(city=city)
    weather_multiplier = calculate_weather_multiplier(weather, category)
    dow_multiplier = calculate_day_of_week_multiplier(date_str, category)
    promo_multiplier = calculate_promo_multiplier(sku_id, date_str)
    holiday_multiplier = calculate_holiday_multiplier(date_str, is_festival)

    combined_multiplier = round(weather_multiplier * dow_multiplier * promo_multiplier * holiday_multiplier, 2)
    final_predicted_demand = predicted_demand_raw * combined_multiplier

    return {
        "sku_id": sku_id,
        "predicted_demand_raw": round(predicted_demand_raw, 1),
        "weather_multiplier": weather_multiplier,
        "dow_multiplier": dow_multiplier,
        "promo_multiplier": promo_multiplier,
        "holiday_multiplier": holiday_multiplier,
        "combined_multiplier": combined_multiplier,
        "final_predicted_demand": round(final_predicted_demand, 1),
        "model_used": model_used,
        "factor_breakdown": {
            "latent_demand_reconstructed": True,
            "weather_impact": f"{(weather_multiplier - 1.0)*100:+.0f}%",
            "dow_impact": f"{(dow_multiplier - 1.0)*100:+.0f}%",
            "promo_impact": f"{(promo_multiplier - 1.0)*100:+.0f}%",
            "holiday_impact": f"{(holiday_multiplier - 1.0)*100:+.0f}%"
        }
    }


if __name__ == "__main__":
    print("InvenIQ Multi-Factor Hybrid Forecasting Engine Initialized.", flush=True)
    res_001 = predict_demand("SKU_001")
    print("\n--- SKU_001 (Staple / Rice) Prediction ---")
    print(json.dumps(res_001, indent=2), flush=True)
    
    res_003 = predict_demand("SKU_003", date_str="2026-08-15")
    print("\n--- SKU_003 (Beverage / Mango Drink - Independence Day + Promo) Prediction ---")
    print(json.dumps(res_003, indent=2), flush=True)

