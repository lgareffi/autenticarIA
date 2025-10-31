import os, re, mimetypes, tempfile, shutil, subprocess
from typing import List, Tuple
import requests

HTTP_RE = re.compile(r"^https?://", re.IGNORECASE)

def sniff_ext(path: str) -> str:
    path_low = path.lower()
    for ext in [".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".html", ".htm"]:
        if path_low.endswith(ext):
            return ext
    guess = mimetypes.guess_extension(mimetypes.guess_type(path)[0] or "")
    return guess or ".bin"


def ensure_local_file(path_or_url: str, workdir: str) -> Tuple[str, str]:
    """
    Devuelve (local_path, temp_dir). Si descargó, temp_dir es la carpeta que creó.
    """
    if HTTP_RE.match(path_or_url):
        temp_dir = tempfile.mkdtemp(dir=workdir)
        local_path = os.path.join(temp_dir, f"download{sniff_ext(path_or_url)}")
        with requests.get(path_or_url, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(local_path, "wb") as f:
                shutil.copyfileobj(r.raw, f)
        return local_path, temp_dir
    else:
        return os.path.abspath(path_or_url), None

def pdf_to_images(pdf_path: str, out_dir: str, dpi: int = 300) -> List[str]:
    os.makedirs(out_dir, exist_ok=True)
    out_prefix = os.path.join(out_dir, "page")
    cmd = ["pdftoppm", "-png", "-r", str(dpi), pdf_path, out_prefix]
    subprocess.run(cmd, check=True)
    imgs = sorted([os.path.join(out_dir, f) for f in os.listdir(out_dir) if f.startswith("page") and f.endswith(".png")])
    return imgs


def html_to_text(html_path: str) -> str:
    from bs4 import BeautifulSoup
    with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ")

    text = " ".join(text.split())
    return text