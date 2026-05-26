import pandas as pd
from sklearn.preprocessing import StandardScaler, MinMaxScaler

STRESSOR_MAP = {
    "timeout": 0,
    "latency": 1,
    "failure": 2,
    "none": 3
}

def encode_stressor(stressor):
    return STRESSOR_MAP.get(stressor, 3)

def extract_features_from_csv(csv_path="chaos_events1.csv", scale="standard"):
    df = pd.read_csv(csv_path)

    # Encode categorical stressor
    df["stressor_type"] = df["stressor"].apply(encode_stressor)
    df["value"] = df["value"].astype(float)
    df["fallback_used"] = df["fallback_used"].astype(int)
    df["success"] = df["success"].astype(int)
    df["cpu"] = df["cpu"].astype(float)
    df["mem"] = df["mem"].astype(float)
    df["prediction"] = df["prediction"].astype(int)
    df["confidence"] = df["confidence"].astype(float)

    # Optional columns
    if "response_time" not in df.columns:
        df["response_time"] = 0.0
    if "retry_attempts" not in df.columns:
        df["retry_attempts"] = 0

    feature_cols = [
        "stressor_type", "value", "response_time",
        "fallback_used", "retry_attempts", "cpu", "mem", "confidence"
    ]

    features = df[feature_cols]

    # Apply scaling
    if scale == "standard":
        scaler = StandardScaler()
    elif scale == "minmax":
        scaler = MinMaxScaler()
    else:
        raise ValueError("scale must be 'standard' or 'minmax'")

    scaled_features = scaler.fit_transform(features)
    X_scaled = pd.DataFrame(scaled_features, columns=feature_cols)

    y = df["success"]
    return X_scaled, y
