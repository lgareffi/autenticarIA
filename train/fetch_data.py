# train/fetch_data.py
import shutil
import pathlib
import argparse
import subprocess
import zipfile
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

# Tomado de tu URL pública:
# https://www.kaggle.com/datasets/lucagareffisapia/autenticar-dataset
DEFAULT_SLUG = "lucagareffisapia/autenticar-dataset"
DEFAULT_CSV  = "dataset_autenticarIA200.csv"

def require_kaggle_cli():
    """Asegura que la CLI de Kaggle esté instalada y disponible en PATH."""
    if shutil.which("kaggle") is None:
        raise SystemExit(
            "No se encontró la CLI de Kaggle.\n"
            "Instalala con: pip install kaggle\n"
            "y reintentá: python train/fetch_data.py"
        )

def download_from_kaggle(slug: str, csv_name: str) -> pathlib.Path:
    """
    Descarga el dataset público de Kaggle y deja data/dataset_autenticarIA200.csv.
    No exige tokens/credenciales (dataset público).
    """
    require_kaggle_cli()

    out = DATA_DIR / "dataset_autenticarIA200.csv"
    tmp = DATA_DIR / "kaggle_tmp"
    tmp.mkdir(exist_ok=True)

    # 1) Intentar bajar sólo el archivo CSV deseado (-f)
    only_file_ok = True
    try:
        subprocess.check_call(
            ["kaggle", "datasets", "download", "-d", slug, "-p", str(tmp), "-q", "-f", csv_name]
        )
    except subprocess.CalledProcessError:
        # Algunos datasets no permiten -f; intentamos bajar todo el zip
        only_file_ok = False

    # 2) Si no soporta -f, bajar todo el dataset
    if not only_file_ok:
        try:
            subprocess.check_call(
                ["kaggle", "datasets", "download", "-d", slug, "-p", str(tmp), "-q"]
            )
        except subprocess.CalledProcessError as e:
            # Mensaje más explícito si Kaggle rechaza por cualquier motivo
            raise SystemExit(
                "Kaggle rechazó la descarga del dataset público.\n"
                f"Slug: {slug}\n"
                "Verificá que el dataset exista y sea público. "
                "Si el error persiste, probá iniciar sesión en la CLI de Kaggle o usar un token."
            ) from e

    # 3) Descomprimir todos los .zip descargados
    for z in tmp.glob("*.zip"):
        with zipfile.ZipFile(z, "r") as zf:
            zf.extractall(tmp)

    # 4) Buscar el CSV exacto; si no aparece, tomar el primero que haya
    candidates = list(tmp.rglob(csv_name))
    if not candidates:
        candidates = list(tmp.rglob("*.csv"))

    if not candidates:
        shutil.rmtree(tmp, ignore_errors=True)
        raise SystemExit("No se encontró ningún .csv dentro del dataset de Kaggle.")

    # 5) Copiar al nombre estándar que usa el resto del pipeline
    shutil.copy2(candidates[0], out)
    shutil.rmtree(tmp, ignore_errors=True)
    return out

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Descarga el CSV público de Kaggle a data/")
    ap.add_argument("--slug", default=DEFAULT_SLUG,
                    help=f"Slug de Kaggle (default: {DEFAULT_SLUG})")
    ap.add_argument("--csv-name", default=DEFAULT_CSV,
                    help=f"Nombre del CSV (default: {DEFAULT_CSV})")
    args = ap.parse_args()

    p = download_from_kaggle(args.slug, args.csv_name)
    print(f"Listo. Dataset en: {p}")
