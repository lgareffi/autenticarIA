import pathlib, json
import pandas as pd
import joblib
from sklearn.metrics import mean_absolute_error, root_mean_squared_error, r2_score

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "dataset_autenticarIA200.csv"
MODELS = ROOT / "models"

def load_feature_spec():
    with open(MODELS / "feature_spec.json", "r", encoding="utf-8") as f:
        return json.load(f)

if __name__ == "__main__":
    df = pd.read_csv(DATA)
    spec = load_feature_spec()
    cols = spec["features"]
    y = df["y_score_1_100"].astype(float)
    y01 = (y - y.min()) / (y.max() - y.min()) if y.max() > y.min() else y/100.0

    X = df[cols].copy().fillna(0)
    for c in X.columns:
        if X[c].dtype == bool:
            X[c] = X[c].astype(int)

    model = joblib.load(MODELS / "rf_model.pkl")
    preds01 = model.predict(X)

    mae = mean_absolute_error(y01, preds01)
    rmse = root_mean_squared_error(y01, preds01) 
    r2 = r2_score(y01, preds01)
    print(f"[FULL EVAL] MAE={mae:.4f} | RMSE={rmse:.4f} | R2={r2:.4f}")
