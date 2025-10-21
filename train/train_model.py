import json, pathlib, argparse
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error, r2_score
import joblib
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "dataset_autenticarIA200.csv"
MODELS = ROOT / "models"
MODELS.mkdir(exist_ok=True)

TARGET_COL = "y_score_1_100"   
LABEL_COL  = "y_label"         

# columnas que seguro NO van como features
DROP_EXPLICIT = {
    "doc_id", "tipo_doc", "file_ext", "document_language",
    "meta_producer", "meta_creator", "meta_createdate", "meta_modifydate",
    LABEL_COL, TARGET_COL
}

def load_dataset(path: pathlib.Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    return df

def build_matrices(df: pd.DataFrame):
    candidates = [c for c in df.columns if c not in DROP_EXPLICIT]
    X = df[candidates].copy()

    for c in X.columns:
        if X[c].dtype == bool:
            X[c] = X[c].astype(int)
    X = X.fillna(0)

    y = df[TARGET_COL].astype(float)

    y01 = (y - y.min()) / (y.max() - y.min()) if y.max() > y.min() else y / 100.0

    feature_spec = {
        "version": 1,
        "features": list(X.columns),
        "target": TARGET_COL,
        "target_scaling": "minmax_01_if_needed"
    }
    return X, y01, feature_spec

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=str(DATA))
    parser.add_argument("--n_estimators", type=int, default=400)
    parser.add_argument("--max_depth", type=int, default=None)
    args = parser.parse_args()

    df = load_dataset(pathlib.Path(args.data))
    X, y, feature_spec = build_matrices(df)

    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=42)

    model = RandomForestRegressor(
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        random_state=42,
        n_jobs=-1
    )
    model.fit(Xtr, ytr)

    preds = model.predict(Xte)
    mae = mean_absolute_error(yte, preds)
    rmse = root_mean_squared_error(yte, preds)
    r2 = r2_score(yte, preds)

    print(f"MAE={mae:.4f} | RMSE={rmse:.4f} | R2={r2:.4f}")

    # guardar
    joblib.dump(model, MODELS / "rf_model.pkl")
    with open(MODELS / "feature_spec.json", "w", encoding="utf-8") as f:
        json.dump(feature_spec, f, ensure_ascii=False, indent=2)

    print(f"Guardado modelo en {MODELS/'rf_model.pkl'} y spec en {MODELS/'feature_spec.json'}")
