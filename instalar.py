"""Prepara el editor en el ordenador de la clienta (Windows o Mac). Se ejecuta una vez.

Uso: python instalar.py <carpeta_de_trabajo>
Crea ~/.editor-reels/venv con las librerías, busca ffmpeg, descarga el modelo de transcripción
y deja .claude/launch.json en la carpeta para que Claude abra el panel.
"""
import glob
import json
import os
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
CASA = os.path.join(os.path.expanduser("~"), ".editor-reels")
WIN = sys.platform == "win32"
VENV = os.path.join(CASA, "venv")
PY = os.path.join(VENV, "Scripts", "python.exe") if WIN else os.path.join(VENV, "bin", "python")
LIBRERIAS = ["faster-whisper", "pillow", "yt-dlp", "numpy"]


def paso(texto):
    print(f"→ {texto}", flush=True)


def buscar_ffmpeg():
    """En el PATH o donde lo deja winget (aún no visible sin reiniciar la consola)."""
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return os.path.dirname(shutil.which("ffmpeg"))
    candidatos = []
    if WIN:
        local = os.environ.get("LOCALAPPDATA", "")
        candidatos += [os.path.join(local, "Microsoft", "WinGet", "Links")]
        candidatos += glob.glob(os.path.join(local, "Microsoft", "WinGet", "Packages", "Gyan.FFmpeg*", "*", "bin"))
    else:
        candidatos += ["/opt/homebrew/bin", "/usr/local/bin"]
    exe = "ffmpeg.exe" if WIN else "ffmpeg"
    for c in candidatos:
        if os.path.exists(os.path.join(c, exe)):
            return c
    return None


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    carpeta = os.path.abspath(sys.argv[1])
    if sys.version_info < (3, 10) or sys.version_info >= (3, 14):
        sys.exit("NECESITA_PYTHON_312: instala Python 3.12 "
                 + ("(winget install -e --id Python.Python.3.12)" if WIN else "(brew install python@3.12)"))
    os.makedirs(CASA, exist_ok=True)

    ff = buscar_ffmpeg()
    if not ff:
        sys.exit("NECESITA_FFMPEG: " + ("winget install -e --id Gyan.FFmpeg" if WIN else "brew install ffmpeg"))
    paso(f"ffmpeg encontrado en {ff}")

    if not os.path.exists(PY):
        paso("Creando el entorno del editor")
        subprocess.check_call([sys.executable, "-m", "venv", VENV])
    paso("Instalando librerías (la primera vez tarda unos minutos)")
    subprocess.check_call([PY, "-m", "pip", "install", "-q", "--upgrade", "pip"])
    subprocess.check_call([PY, "-m", "pip", "install", "-q", "--upgrade"] + LIBRERIAS)

    paso("Descargando el modelo de transcripción (~1,6 GB, solo la primera vez)")
    subprocess.check_call([PY, "-c", "from faster_whisper import WhisperModel; "
                                     "WhisperModel('large-v3-turbo', device='cpu', compute_type='int8')"])

    with open(os.path.join(CASA, "config.json"), "w", encoding="utf-8") as f:
        json.dump({"ffmpeg_dir": ff, "python": PY, "motor": os.path.join(AQUI, "motor")}, f, indent=1)

    for s in ("entrada", "salida", "recursos", "overlays", "estilos", "trabajo"):
        os.makedirs(os.path.join(carpeta, s), exist_ok=True)
    lanzar = os.path.join(carpeta, ".claude", "launch.json")
    os.makedirs(os.path.dirname(lanzar), exist_ok=True)
    conf = {"version": "0.0.1", "configurations": []}
    if os.path.exists(lanzar):
        with open(lanzar, encoding="utf-8") as f:
            conf = json.load(f)
    conf["configurations"] = [c for c in conf.get("configurations", []) if c.get("name") != "editor-reels"]
    conf["configurations"].append({
        "name": "editor-reels", "runtimeExecutable": PY,
        "runtimeArgs": [os.path.join(AQUI, "motor", "servidor.py"), carpeta, "8765"], "port": 8765})
    with open(lanzar, "w", encoding="utf-8") as f:
        json.dump(conf, f, indent=2)

    print(json.dumps({"ok": True, "python": PY, "motor": os.path.join(AQUI, "motor", "editor.py"),
                      "carpeta": carpeta}, ensure_ascii=False))


if __name__ == "__main__":
    main()
