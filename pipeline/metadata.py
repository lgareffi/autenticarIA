import json, subprocess

def read_metadata_exiftool(path: str) -> dict:
    # -j salida JSON, -n valores sin formatear
    try:
        out = subprocess.check_output(["exiftool", "-j", "-n", path], text=True)
        arr = json.loads(out)
        return arr[0] if arr else {}
    except Exception:
        return {}
