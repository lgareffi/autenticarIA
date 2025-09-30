import pathlib, subprocess

def test_train_smoke():
    root = pathlib.Path(__file__).resolve().parents[1]
    data = root / "data" / "dataset_autenticarIA200.csv"
    assert data.exists(), "Falta dataset_autenticarIA200.csv en data/"

    cmd = ["python", str(root/"train"/"train_model.py"), "--data", str(data)]
    subprocess.check_call(cmd)
    assert (root/"models"/"rf_model.pkl").exists()
    assert (root/"models"/"feature_spec.json").exists()
