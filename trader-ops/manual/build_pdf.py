"""Genera MANUAL_COMPLETO.html y MANUAL_COMPLETO.pdf a partir de las partes.

Solo libreria estandar. Usa Edge o Chrome en modo headless para imprimir a PDF.

    python trader-ops/manual/build_pdf.py
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
OPS = AQUI.parent
HTML = OPS / "MANUAL_COMPLETO.html"
PDF = OPS / "MANUAL_COMPLETO.pdf"
PARTES = ["parte1.html", "parte2.html", "parte3.html", "parte4.html", "parte5.html"]


def _navegador():
    candidatos = [
        os.environ.get("EDGE_PATH"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for c in candidatos:
        if c and Path(c).exists():
            return c
    for name in ("msedge", "chrome", "google-chrome"):
        p = shutil.which(name)
        if p:
            return p
    return None


def main():
    trozos = []
    for nombre in PARTES:
        p = AQUI / nombre
        if not p.exists():
            print("Falta %s" % p)
            return 2
        trozos.append(p.read_text(encoding="utf-8"))
    html = "\n".join(trozos)
    HTML.write_text(html, encoding="utf-8")
    print("HTML: %s (%d KB)" % (HTML, len(html.encode('utf-8')) // 1024))

    nav = _navegador()
    if not nav:
        print("No encuentro Edge ni Chrome. Abre el HTML y imprime a PDF a mano.")
        return 1
    pdf_viejo = PDF
    if pdf_viejo.exists():
        pdf_viejo.unlink()
    cmd = [
        nav,
        "--headless=new",
        "--disable-gpu",
        "--allow-file-access-from-files",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=15000",
        "--no-pdf-header-footer",
        "--print-to-pdf=%s" % PDF,
        HTML.as_uri(),
    ]
    print("Imprimiendo con %s" % nav)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if not PDF.exists():
        print("No se genero el PDF. Codigo %s" % r.returncode)
        print((r.stderr or r.stdout or "")[-2000:])
        return 1
    print("PDF: %s (%.1f MB)" % (PDF, PDF.stat().st_size / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
