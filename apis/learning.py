import os
import csv
import pandas as pd
from sklearn.linear_model import LogisticRegression
from feature_extraction import extract_features_from_csv
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestClassifier
import matplotlib

matplotlib.use("Agg")  # Use non-GUI backend - for headless environment

# Globals
MODEL = None
CSV_PATH = "chaos_events1.csv" #Change to chaos_events.csv later

# Stressor encoding map
STRESSOR_MAP = {
    "timeout": 0,
    "latency": 1,
    "failure": 2,
    "none": 3
}

def train_model(X=None, y=None, scale="standard"):
    """
    Trains a logistic regression model on chaos event logs.
    """
    global MODEL

    if X is None or y is None:
        X, y = extract_features_from_csv(scale=scale)
   #X, y = extract_features_from_csv(scale="standard")
    MODEL = LogisticRegression(max_iter=1000)
    MODEL.fit(X, y)
    return MODEL

def predict_with_confidence(stressor, value, cpu, mem):
    """
    Predicts success likelihood and returns confidence score.
    """
    global MODEL
    if MODEL is None:
        try:
            train_model()
        except Exception:
            return True, 0.5  # Default optimistic guess

    stressor_code = STRESSOR_MAP.get(stressor, 3)

    # Create feature vector (match training schema)
    input_df = pd.DataFrame([{
        "stressor_type": stressor_code,
        "value": value,
        "response_time": 0.0,
        "fallback_used": 0,
        "retry_attempts": 0,
        "cpu": cpu,
        "mem": mem,
        "confidence": 0.5  # placeholder
    }])

    # Scale using training logic
    #logger.info("Raw input for prediction", extra=input_df.to_dict(orient="records")[0])
    X_scaled, _ = extract_features_from_csv(scale="standard")
    scaler_mean = X_scaled.mean()
    scaler_std = X_scaled.std()
    input_scaled = (input_df - scaler_mean) / scaler_std

    prob = MODEL.predict_proba(input_scaled)[0][1]
    prediction = int(prob >= 0.5)
    return prediction, round(prob, 3)

def log_chaos_to_csv(stressor, value, result, success, fallback_used, cpu, mem, prediction, confidence, injected_by_ai=False):
    """ 
    Appends a chaos event with metadata to the CSV log.
    """
    file_exists = os.path.isfile(CSV_PATH)
    with open(CSV_PATH, mode="a", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=[
            "timestamp", "stressor", "value", "result", "success",
            "fallback_used", "cpu", "mem", "prediction", "confidence", "injected_by_ai"
        ])
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "timestamp": pd.Timestamp.now().isoformat(),
            "stressor": stressor,
            "value": value,
            "result": result if result is not None else -1,
            "success": int(success),
            "fallback_used": int(fallback_used),
            "cpu": round(cpu, 2),
            "mem": round(mem, 2),
            "prediction": int(prediction),
            "confidence": round(confidence, 3),
            "injected_by_ai": int(injected_by_ai)
        })




def plot_feature_importance(model, feature_names):
    importance = model.coef_[0]     #shape: (4,)
    if len(importance) != len(feature_names):
        raise ValueError(f"Mismatch: {len(importance)} coefficients vs {len(feature_names)} features")
    plt.figure(figsize=(8, 4))
    plt.barh(feature_names, importance)
    plt.xlabel("Feature Importance")
    plt.title("Logistic Regression Coefficients")
    plt.tight_layout()
    plt.show()
    #plt.savefig("output/feature_importance.png")
    plt.savefig("feature_importance.png") #Since I am running it inside a container
    print("[PLOT] Saved feature importance plot")


#Chaos sector model - to inject chaos using Artificial Intelligence
import os
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

def train_chaos_selector(csv_path="chaos_events1.csv"):
    if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
        # Return a dummy model that always selects "none"
        class DummyChaosSelector:
            def predict(self, X):
                return [3] * len(X)  # 3 = "none" in STRESSOR_MAP
        return DummyChaosSelector()

    df = pd.read_csv(csv_path)

    if df.empty or "stressor" not in df.columns:
        return DummyChaosSelector()

    df["stressor_type"] = df["stressor"].map({
        "timeout": 0, "latency": 1, "failure": 2, "none": 3
    })
    df["success"] = df["success"].astype(int)

    feature_cols = ["value", "cpu", "mem", "confidence"]
    if not all(col in df.columns for col in feature_cols):
        return DummyChaosSelector()

    X = df[feature_cols]
    y = df["stressor_type"]

    model = RandomForestClassifier()
    model.fit(X, y)
    return model

#Delete the one on top of this (train_chaos_selector) and replace with the commented one
""" 
def train_chaos_selector():
    df = pd.read_csv("chaos_events.csv")
    df["stressor_type"] = df["stressor"].map(STRESSOR_MAP)
    df["success"] = df["success"].astype(int)

    feature_cols = ["value", "cpu", "mem", "confidence"]
    X = df[feature_cols]
    y = df["stressor_type"]  # Predict which stressor reveals weakness

    model = RandomForestClassifier()
    model.fit(X, y)
    return model
"""
