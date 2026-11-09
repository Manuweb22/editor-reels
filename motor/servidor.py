"""Panel del editor: servidor local (solo 127.0.0.1) sin librerías externas.

Uso: python servidor.py [carpeta] [puerto]   (carpeta = la de la clienta, por defecto la actual)
El panel guarda los archivos que sube la clienta y su pedido en trabajo/peticion.json;
Claude, en el chat, lee ese pedido y hace la edición con editor.py.
"""
import json
import mimetypes
import os
import re
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

AQUI = os.path.dirname(os.path.abspath(__file__))
CARPETA = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.getcwd())
PUERTO = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
SUBIDAS = {"entrada", "recursos", "overlays"}
LEIBLES = {"entrada", "salida", "trabajo", "recursos", "overlays", "estilos"}
VIDEO = (".mp4", ".mov", ".m4v", ".webm", ".mkv")


def ruta_segura(rel):
    """Solo rutas dentro de la carpeta de la clienta y de sus subcarpetas permitidas."""
    rel = unquote(rel).replace("\\", "/").lstrip("/")
    destino = os.path.abspath(os.path.join(CARPETA, rel))
    if not destino.startswith(CARPETA + os.sep) or rel.split("/")[0] not in LEIBLES:
        return None
    return destino


def leer_json(rel, defecto=None):
    try:
        with open(os.path.join(CARPETA, rel), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return defecto


def listar(sub, ext=None):
    d = os.path.join(CARPETA, sub)
    if not os.path.isdir(d):
        return []
    out = [f for f in os.listdir(d) if not f.startswith(".") and (ext is None or f.lower().endswith(ext))]
    return sorted(out, key=lambda f: os.path.getmtime(os.path.join(d, f)))


def estado():
    pet = leer_json("trabajo/peticion.json", {})
    plan = leer_json(pet.get("plan", ""), {}) if pet.get("plan") else {}
    est = leer_json(plan.get("estilo", ""), {}) if plan.get("estilo") else {}
    ref = None
    for d in sorted(listar("trabajo")):
        r = os.path.join("trabajo", d, "referencia.json") if d.startswith("referencia") else None
        if r and os.path.exists(os.path.join(CARPETA, r)):
            ref = {"datos": leer_json(r, {}), "carpeta": f"trabajo/{d}",
                   "video": next((f"trabajo/{d}/{f}" for f in listar(f"trabajo/{d}", VIDEO)), None)}
    return {
        "progreso": leer_json("trabajo/estado.json", {}),
        "peticion": pet,
        "versiones": [f"salida/{f}" for f in listar("salida", VIDEO)],
        "marcas": {f"salida/{f}": int(os.path.getmtime(os.path.join(CARPETA, "salida", f)))
                   for f in listar("salida", VIDEO)},
        "referencia": ref,
        "estilo": {"archivo": plan.get("estilo"), "nombre": est.get("nombre"), "etiquetas": est.get("etiquetas", [])},
        "estilos": listar("estilos", ".json"),
        "archivos": {s: listar(s) for s in SUBIDAS},
    }


class Panel(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def enviar(self, codigo, cuerpo, tipo="application/json; charset=utf-8"):
        datos = cuerpo if isinstance(cuerpo, bytes) else json.dumps(cuerpo, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(datos)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            with open(os.path.join(AQUI, "panel.html"), "rb") as f:
                return self.enviar(200, f.read(), "text/html; charset=utf-8")
        if u.path == "/api/estado":
            return self.enviar(200, estado())
        if u.path == "/media":
            return self.media(parse_qs(u.query).get("ruta", [""])[0])
        self.enviar(404, {"error": "no existe"})

    def media(self, rel):
        ruta = ruta_segura(rel)
        if not ruta or not os.path.isfile(ruta):
            return self.enviar(404, {"error": "no existe"})
        tam = os.path.getsize(ruta)
        ini, fin = 0, tam - 1
        rango = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        if rango:
            ini = int(rango.group(1) or 0)
            fin = int(rango.group(2)) if rango.group(2) else min(tam - 1, ini + 8 * 1024 * 1024)
        self.send_response(206 if rango else 200)
        self.send_header("Content-Type", mimetypes.guess_type(ruta)[0] or "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(fin - ini + 1))
        if rango:
            self.send_header("Content-Range", f"bytes {ini}-{fin}/{tam}")
        self.end_headers()
        with open(ruta, "rb") as f:
            f.seek(ini)
            quedan = fin - ini + 1
            while quedan > 0:
                trozo = f.read(min(1024 * 1024, quedan))
                if not trozo:
                    break
                try:
                    self.wfile.write(trozo)
                except (BrokenPipeError, ConnectionResetError):
                    return
                quedan -= len(trozo)

    def do_PUT(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        sub, nombre = q.get("carpeta", [""])[0], os.path.basename(q.get("nombre", [""])[0])
        nombre = re.sub(r"[^\w.\- ]", "_", nombre).strip()
        if u.path != "/api/subir" or sub not in SUBIDAS or not nombre:
            return self.enviar(400, {"error": "subida no válida"})
        os.makedirs(os.path.join(CARPETA, sub), exist_ok=True)
        destino = os.path.join(CARPETA, sub, nombre)
        quedan = int(self.headers.get("Content-Length", 0))
        with open(destino, "wb") as f:
            while quedan > 0:
                trozo = self.rfile.read(min(1024 * 1024, quedan))
                if not trozo:
                    break
                f.write(trozo)
                quedan -= len(trozo)
        self.enviar(200, {"ok": True, "ruta": f"{sub}/{nombre}"})

    def do_POST(self):
        u = urlparse(self.path)
        largo = int(self.headers.get("Content-Length", 0))
        try:
            datos = json.loads(self.rfile.read(largo) or b"{}")
        except ValueError:
            return self.enviar(400, {"error": "json no válido"})
        if u.path == "/api/peticion":
            pet = {k: str(datos.get(k, ""))[:2000] for k in ("tipo", "enlace", "video", "nota", "cambio", "estilo")}
            pet.update({"hora": time.strftime("%Y-%m-%d %H:%M:%S"), "estado": "pendiente"})
            anterior = leer_json("trabajo/peticion.json", {})
            if pet["tipo"] == "cambio" and anterior.get("plan"):
                pet["plan"] = anterior["plan"]
            os.makedirs(os.path.join(CARPETA, "trabajo"), exist_ok=True)
            with open(os.path.join(CARPETA, "trabajo", "peticion.json"), "w", encoding="utf-8") as f:
                json.dump(pet, f, ensure_ascii=False, indent=1)
            return self.enviar(200, {"ok": True})
        if u.path == "/api/abrir":
            d = os.path.join(CARPETA, "salida")
            os.makedirs(d, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(d)  # noqa: S606 (abre el Explorador en su carpeta)
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", d])
            return self.enviar(200, {"ok": True})
        self.enviar(404, {"error": "no existe"})


if __name__ == "__main__":
    for s in ("entrada", "salida", "recursos", "overlays", "estilos", "trabajo"):
        os.makedirs(os.path.join(CARPETA, s), exist_ok=True)
    print(f"Panel en http://127.0.0.1:{PUERTO} (carpeta {CARPETA})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PUERTO), Panel).serve_forever()
