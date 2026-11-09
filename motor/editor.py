"""Editor de reels: motor que usa la skill. Funciona igual en Windows y en Mac.

Subcomandos (siempre con el python del entorno: ver instalar.py):
  comprobar                          dice si falta algo (ffmpeg, librerías)
  referencia <enlace|archivo> <dir>  baja el reel de ejemplo y saca hojas de fotogramas + datos de ritmo
  transcribir <video> <dir>          palabras con su tiempo (palabras.json) + lineas.txt para elegir tramos
  render <plan.json>                 monta el reel vertical 1080x1920
  hoja <video> <salida.jpg>          hoja de 8 fotogramas para revisar un vídeo
"""
import json
import math
import os
import re
import shutil
import subprocess
import sys
import wave

AQUI = os.path.dirname(os.path.abspath(__file__))
FUENTES = os.path.join(os.path.dirname(AQUI), "fuentes")
W, H, FPS = 1080, 1920, 30
CONFIG = os.path.join(os.path.expanduser("~"), ".editor-reels", "config.json")
if os.path.exists(CONFIG):  # ffmpeg recién instalado con winget aún no está en el PATH de esta consola
    with open(CONFIG, encoding="utf-8") as _f:
        _dir = json.load(_f).get("ffmpeg_dir")
    if _dir and _dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _dir + os.pathsep + os.environ.get("PATH", "")
MULETILLAS = {"eh", "ehh", "ehm", "em", "emm", "mm", "mmm", "hmm", "ah", "uh", "um"}
PISTA = "Eh, em, mmm... o sea, bueno, este, vale, ¿no?, ¿vale?, en plan, tipo, digamos, pues, ¿sabes?"


def progreso(paso, detalle=""):
    """Deja el estado en trabajo/estado.json (lo lee el panel) y lo imprime."""
    print(f"[{paso}] {detalle}", flush=True)
    try:
        os.makedirs("trabajo", exist_ok=True)
        with open(os.path.join("trabajo", "estado.json"), "w", encoding="utf-8") as f:
            json.dump({"paso": paso, "detalle": detalle}, f, ensure_ascii=False)
    except OSError:
        pass


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
    if r.returncode != 0:
        sys.exit(f"Falló: {' '.join(cmd[:4])}…\n{r.stderr[-2500:]}")
    return r


def sonda(video):
    r = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", video])
    d = json.loads(r.stdout)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    w, h = int(v["width"]), int(v["height"])
    rot = 0
    for sd in v.get("side_data_list", []):
        rot = int(sd.get("rotation", 0) or 0)
    if abs(rot) in (90, 270):
        w, h = h, w
    return {"ancho": w, "alto": h, "duracion": float(d["format"]["duration"]),
            "audio": any(s["codec_type"] == "audio" for s in d["streams"])}


# ---------------------------------------------------------------- comprobar

def comprobar():
    falta = []
    for prog in ("ffmpeg", "ffprobe"):
        if not shutil.which(prog):
            falta.append(prog)
    for mod in ("faster_whisper", "PIL", "yt_dlp", "numpy"):
        try:
            __import__(mod)
        except ImportError:
            falta.append(mod)
    print(json.dumps({"ok": not falta, "falta": falta}))


# ---------------------------------------------------------------- audio

def leer_audio(video, sr=16000):
    """Audio mono 16 kHz como array de numpy (para medir dónde hay voz)."""
    import numpy as np
    tmp = os.path.join("trabajo", "_audio.wav")
    os.makedirs("trabajo", exist_ok=True)
    run(["ffmpeg", "-y", "-v", "error", "-i", video, "-vn", "-ac", "1", "-ar", str(sr), tmp])
    with wave.open(tmp, "rb") as f:
        a = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    os.remove(tmp)
    return a, sr


def db_ventanas(a, sr, ventana=0.01):
    import numpy as np
    n = int(sr * ventana)
    m = len(a) // n
    rms = np.sqrt(np.mean(a[: m * n].reshape(m, n) ** 2, axis=1) + 1e-12)
    return 20 * np.log10(rms)


# ---------------------------------------------------------------- transcribir

def _transcribir(video, modelo):
    from faster_whisper import WhisperModel
    m = WhisperModel(modelo, device="cpu", compute_type="int8")
    audio, _ = leer_audio(video)  # con ffmpeg: no depende de la versión de PyAV
    segs, info = m.transcribe(audio, word_timestamps=True, initial_prompt=PISTA,
                              condition_on_previous_text=False, vad_filter=False)
    palabras = []
    for s in segs:
        for w in s.words or []:
            t = w.word.strip()
            if t:
                palabras.append({"w": t, "s": round(w.start, 3), "e": round(max(w.end, w.start + 0.08), 3)})
    return palabras, info.language


def lineas(palabras, pausa=0.3, maximo=22):
    """Agrupa por pausas y frases: cada línea es un trozo que se puede quedar o quitar entero."""
    out, ini = [], 0
    for i in range(1, len(palabras) + 1):
        corte = (i == len(palabras) or palabras[i]["s"] - palabras[i - 1]["e"] > pausa
                 or palabras[i - 1]["w"].endswith((".", "?", "!", ",")) and i - ini >= 8 or i - ini >= maximo)
        if corte:
            texto = " ".join(p["w"] for p in palabras[ini:i])
            out.append(f"[{ini}-{i - 1}] ({palabras[ini]['s']:.1f}s) {texto}")
            ini = i
    return out


def transcribir(video, carpeta, modelo="large-v3-turbo"):
    os.makedirs(carpeta, exist_ok=True)
    progreso("transcribir", f"Escuchando {os.path.basename(video)}")
    palabras, idioma = _transcribir(video, modelo)
    with open(os.path.join(carpeta, "palabras.json"), "w", encoding="utf-8") as f:
        json.dump({"video": video, "idioma": idioma, "palabras": palabras}, f, ensure_ascii=False)
    ls = lineas(palabras)
    with open(os.path.join(carpeta, "lineas.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(ls))
    hoja(video, os.path.join(carpeta, "hoja.jpg"))
    info = sonda(video)
    print(json.dumps({"palabras": len(palabras), "lineas": len(ls), "idioma": idioma, **info}))


# ---------------------------------------------------------------- hojas de fotogramas

def fotograma(video, t, ancho):
    from PIL import Image
    import io
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1",
                        "-vf", f"scale={ancho}:-2", "-f", "image2pipe", "-vcodec", "png", "-"],
                       capture_output=True)
    if not r.stdout:
        return None
    return Image.open(io.BytesIO(r.stdout)).convert("RGB")


def hoja(video, salida, tiempos=None, ancho=300, cols=4):
    """Hoja de fotogramas con su segundo encima (pocas imágenes = pocos tokens)."""
    from PIL import Image, ImageDraw
    dur = sonda(video)["duracion"]
    if tiempos is None:
        tiempos = [0.3 + (dur - 0.6) * k / 7 for k in range(8)]
    fotos = [(t, fotograma(video, t, ancho)) for t in tiempos]
    fotos = [(t, f) for t, f in fotos if f]
    if not fotos:
        return
    fw, fh = fotos[0][1].size
    filas = math.ceil(len(fotos) / cols)
    lienzo = Image.new("RGB", (fw * cols, (fh + 26) * filas), "white")
    d = ImageDraw.Draw(lienzo)
    for k, (t, f) in enumerate(fotos):
        x, y = (k % cols) * fw, (k // cols) * (fh + 26)
        d.text((x + 6, y + 6), f"{t:.1f}s", fill="black", font=fuente("montserrat", 600, 16))
        lienzo.paste(f.resize((fw, fh)), (x, y + 26))
    lienzo.save(salida, quality=82)


# ---------------------------------------------------------------- referencia

def bajar(enlace, carpeta):
    import yt_dlp
    destino = os.path.join(carpeta, "referencia.%(ext)s")
    opts = {"outtmpl": destino, "quiet": True, "no_warnings": True,
            "format": "bv*[height<=1920]+ba/b", "merge_output_format": "mp4"}
    with yt_dlp.YoutubeDL(opts) as y:
        y.download([enlace])
    for f in os.listdir(carpeta):
        if f.startswith("referencia.") and f.endswith((".mp4", ".mkv", ".webm", ".mov")):
            return os.path.join(carpeta, f)
    sys.exit("No se pudo bajar el reel. Pide al usuario que lo descargue y te pase el archivo.")


def cortes_de_plano(video):
    r = subprocess.run(["ffmpeg", "-i", video, "-vf", "select='gt(scene,0.3)',showinfo", "-an", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return [float(m) for m in re.findall(r"pts_time:([\d.]+)", r.stderr)]


def referencia(fuente_ref, carpeta):
    os.makedirs(carpeta, exist_ok=True)
    progreso("referencia", "Bajando el reel de ejemplo")
    video = fuente_ref if os.path.exists(fuente_ref) else bajar(fuente_ref, carpeta)
    info = sonda(video)
    dur = info["duracion"]
    progreso("referencia", "Mirando el estilo del ejemplo")
    hoja(video, os.path.join(carpeta, "hoja_general.jpg"))
    # 8 fotogramas seguidos (cada 0,1 s) para ver cómo entran los subtítulos
    t0 = max(0.5, dur * 0.3)
    hoja(video, os.path.join(carpeta, "hoja_animacion.jpg"), [t0 + 0.1 * k for k in range(8)], ancho=300)
    # primer fotograma grande: el gancho
    f = fotograma(video, 0.15, 540)
    if f:
        f.save(os.path.join(carpeta, "gancho.jpg"), quality=85)
    cortes = cortes_de_plano(video)
    datos = {"duracion": round(dur, 1), "ancho": info["ancho"], "alto": info["alto"],
             "cortes_de_plano": len(cortes), "segundos_por_plano": round(dur / (len(cortes) + 1), 2)}
    if info["audio"]:
        progreso("referencia", "Escuchando el ejemplo")
        palabras, idioma = _transcribir(video, "small")
        habla = sum(p["e"] - p["s"] for p in palabras)
        datos.update({"idioma": idioma, "palabras_por_segundo": round(len(palabras) / max(habla, 1), 2),
                      "texto": " ".join(p["w"] for p in palabras)[:1500]})
        datos["musica_de_fondo"] = hay_musica(video, palabras)
    with open(os.path.join(carpeta, "referencia.json"), "w", encoding="utf-8") as f2:
        json.dump(datos, f2, ensure_ascii=False, indent=1)
    print(json.dumps(datos, ensure_ascii=False))


def hay_musica(video, palabras):
    """Compara el volumen en los huecos sin voz: si no baja, hay música debajo."""
    import numpy as np
    a, sr = leer_audio(video)
    db = db_ventanas(a, sr)
    voz = np.zeros(len(db), bool)
    for p in palabras:
        voz[int(p["s"] * 100): int(p["e"] * 100) + 1] = True
    if voz.all() or not voz.any():
        return "no se sabe"
    hueco, con_voz = np.median(db[~voz]), np.median(db[voz])
    return "sí" if hueco > -42 and con_voz - hueco < 18 else "no"


# ---------------------------------------------------------------- fuentes y color

_CACHE_F = {}


def fuente(nombre, peso, tam):
    clave = (nombre, peso, int(tam))
    if clave in _CACHE_F:
        return _CACHE_F[clave]
    from PIL import ImageFont
    archivo = {"montserrat": "Montserrat-VF.ttf", "anton": "Anton-Regular.ttf",
               "playfair": "PlayfairDisplay-Italic-VF.ttf"}.get(nombre, "Montserrat-VF.ttf")
    f = ImageFont.truetype(os.path.join(FUENTES, archivo), int(tam))
    try:
        f.set_variation_by_axes([peso])
    except (OSError, AttributeError, ValueError):
        pass
    _CACHE_F[clave] = f
    return f


def color(hexa, defecto=(255, 255, 255, 255)):
    if not hexa:
        return defecto
    h = hexa.lstrip("#")
    if len(h) == 6:
        h += "FF"
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4, 6))


# ---------------------------------------------------------------- render: cortes

def calcular_cortes(palabras, plan, audio_db):
    """Convierte los tramos del plan en trozos de vídeo, quitando silencios y muletillas."""
    pausa = plan.get("pausa_max", 0.22)
    quitar = plan.get("quitar_muletillas", True)
    n = len(palabras)
    clips = []
    for a, b in plan["tramos"]:
        idx = [i for i in range(a, b + 1)
               if not (quitar and re.sub(r"[^\wáéíóúñ]", "", palabras[i]["w"].lower()) in MULETILLAS)]
        grupo = []
        for i in idx:
            if grupo and (i != grupo[-1] + 1 or palabras[i]["s"] - palabras[grupo[-1]]["e"] > pausa):
                clips.append(grupo)
                grupo = []
            grupo.append(i)
        if grupo:
            clips.append(grupo)
    out = []
    for g in clips:
        i0, i1 = g[0], g[-1]
        ant = palabras[i0 - 1]["e"] if i0 > 0 else 0
        sig = palabras[i1 + 1]["s"] if i1 + 1 < n else palabras[i1]["e"] + 0.5
        ini = max(palabras[i0]["s"] - 0.06, (ant + palabras[i0]["s"]) / 2)
        fin = alargar_voz(palabras[i1]["e"], min(sig - 0.02, palabras[i1]["e"] + 0.35), audio_db)
        out.append({"palabras": g, "ini": round(ini, 3), "fin": round(max(fin + 0.05, ini + 0.15), 3)})
    return out


def alargar_voz(fin, tope, db):
    """Whisper cierra las palabras antes de tiempo: alarga hasta que la voz cae."""
    k = int(fin * 100)
    while k < len(db) and k / 100 < tope and db[k] > -45:
        k += 1
    return min(max(fin, k / 100), max(tope, fin))


def filtro_encuadre(info, enc, z):
    modo = enc.get("modo", "recorte")
    cx = enc.get("centro_x", 0.5)
    vertical = info["alto"] >= info["ancho"]
    if vertical or modo == "recorte":
        return (f"scale={int(W * z)}:{int(H * z)}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H}:(iw-{W})*{cx}:(ih-{H})/2")
    fg = f"scale={int(W * z)}:-2,crop=min(iw\\,{W}):ih"
    if modo == "negro":
        return f"{fg},pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black"
    return (f"split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"gblur=sigma=40,eq=brightness=-0.12[fondo];[b]{fg}[frente];"
            f"[fondo][frente]overlay=(W-w)/2:(H-h)/2")


def filtro_color(c):
    if not c:
        return ""
    partes = [f"eq=brightness={c.get('brillo', 0)}:contrast={c.get('contraste', 1)}:saturation={c.get('saturacion', 1)}"]
    if c.get("temperatura") and int(c["temperatura"]) != 6500:
        partes.append(f"colortemperature=temperature={int(c['temperatura'])}")
    return "," + ",".join(partes)


# ---------------------------------------------------------------- render: textos

class Lienzo:
    """Dibuja el estado de los textos en un instante t (PNG transparente 1080x1920)."""

    def __init__(self, est, palabras_out, plan, total):
        self.e = est
        self.p = palabras_out
        self.plan = plan
        self.total = total
        s = est.get("subtitulos", {})
        self.s = s
        n = max(1, int(s.get("palabras", 3)))
        self.bloques = []
        if s.get("activo", True):
            grupo = []
            for k, w in enumerate(palabras_out):
                corta = grupo and (len(grupo) >= n or w["s"] - palabras_out[grupo[-1]]["e"] > 0.6
                                   or palabras_out[grupo[-1]]["w"].endswith((".", "?", "!")))
                if corta:
                    self.bloques.append(grupo)
                    grupo = []
                grupo.append(k)
            if grupo:
                self.bloques.append(grupo)

    def momentos(self):
        ts = {0.0, self.total}
        anim = [k / FPS for k in range(1, 6)]
        for b in self.bloques:
            ini = self.p[b[0]]["s"]
            ts.add(ini)
            ts.update(ini + a for a in anim)
            for k in b:
                ts.add(self.p[k]["s"])
                if self.s.get("animacion") == "palabra":
                    ts.update(self.p[k]["s"] + a for a in anim)
        for t in self.plan.get("_cortes_out", []):
            if self.e.get("flash_cortes"):
                ts.update({t, t + 2 / FPS})
        tit = self.e.get("titulo", {})
        if tit.get("activo") and self.plan.get("titulo"):
            d = tit.get("duracion", "todo")
            if d != "todo":
                ts.add(float(d))
        if self.plan.get("cierre"):
            t = max(0, self.total - 2.2)
            ts.update({t} | {t + a for a in anim})
        return sorted(t for t in ts if 0 <= t <= self.total)

    def bloque_en(self, t):
        for b in self.bloques:
            ini = self.p[b[0]]["s"]
            fin = self.p[b[-1]]["e"] + 0.25
            sig = [x for x in self.bloques if self.p[x[0]]["s"] > ini]
            if sig:
                fin = min(fin, self.p[sig[0][0]]["s"])
            if ini <= t < fin:
                return b
        return None

    def dibujar(self, t):
        from PIL import Image, ImageDraw
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        vacio = True
        tit = self.e.get("titulo", {})
        if tit.get("activo") and self.plan.get("titulo"):
            dur = tit.get("duracion", "todo")
            if dur == "todo" or t < float(dur):
                self.caja_texto(img, self.plan["titulo"], tit, tit.get("y", 0.12))
                vacio = False
        cierre = self.plan.get("cierre")
        if cierre and t >= self.total - 2.2:
            c = self.e.get("cierre", {})
            esc = self.escala(t - (self.total - 2.2), "pop")
            self.caja_texto(img, cierre, {"fuente": c.get("fuente", "montserrat"), "peso": 900,
                                          "tam": c.get("tam", 110) * esc, "color": c.get("color", "#FFFFFF"),
                                          "caja": c.get("caja"), "borde": 8}, c.get("y", 0.74))
            vacio = False
        elif (b := self.bloque_en(t)) is not None:
            self.subtitulo(d, b, t)
            vacio = False
        if self.e.get("flash_cortes") and any(0 <= t - c < 2 / FPS for c in self.plan.get("_cortes_out", [])[1:]):
            d.rectangle([0, 0, W, H], fill=(255, 255, 255, 90))
            vacio = False
        return None if vacio else img

    def escala(self, dt, anim):
        if anim in ("pop", "palabra"):
            pasos = [1.25, 1.15, 1.07, 1.02, 1.0]
            return pasos[min(int(dt * FPS + 1e-6), 4)]
        if anim == "subida":
            return 1.0
        return 1.0

    def alfa(self, dt, anim):
        if anim in ("fundido", "subida"):
            return min(1.0, (dt * FPS + 1) / 5)
        return 1.0

    def subtitulo(self, d, b, t):
        s = self.s
        anim = s.get("animacion", "pop")
        dt = t - self.p[b[0]]["s"]
        esc = self.escala(dt, anim) if anim != "palabra" else 1.0
        alfa = self.alfa(dt, anim)
        tam = s.get("tam", 80)
        claves = set(self.plan.get("_claves_out", []))
        visibles = [k for k in b if anim != "palabra" or self.p[k]["s"] <= t + 1e-6]
        trozos = []
        for k in visibles:
            txt = self.p[k]["w"].strip()
            if s.get("mayusculas", True) == "titulo":
                txt = txt[:1].upper() + txt[1:]
            elif s.get("mayusculas", True):
                txt = txt.upper()
            if s.get("quitar_puntuacion", True):
                txt = re.sub(r"[.,;:¿?¡!…]+", "", txt)
            if not txt:
                continue
            es_clave = k in claves
            activa = self.p[k]["s"] <= t < (self.p[k + 1]["s"] if k + 1 < len(self.p) else 1e9)
            col = s.get("color", "#FFFFFF")
            if es_clave and s.get("color_clave"):
                col = s["color_clave"]
            elif activa and s.get("resaltar_activa") and s.get("color_activa"):
                col = s["color_activa"]
            elif not activa and s.get("inactivas_tenues"):
                col = s.get("color_inactiva", "#FFFFFF99")
            e_k = esc * (1.12 if anim == "palabra" and self.p[k]["s"] > t - 3 / FPS else 1.0)
            if es_clave and s.get("fuente_clave"):
                f = fuente(s["fuente_clave"], s.get("peso_clave", 700), tam * 1.1 * e_k)
            else:
                f = fuente(s.get("fuente", "montserrat"), s.get("peso", 800), tam * e_k)
            trozos.append((txt, f, color(col)))
        if not trozos:
            return
        # reparto en líneas por ancho
        max_w = W * s.get("ancho", 0.84)
        lineas_, linea, ancho_l = [], [], 0
        esp = tam * 0.28
        for txt, f, c in trozos:
            wpx = d.textlength(txt, font=f)
            if linea and ancho_l + esp + wpx > max_w:
                lineas_.append((linea, ancho_l))
                linea, ancho_l = [], 0
            ancho_l += (esp if linea else 0) + wpx
            linea.append((txt, f, c, wpx))
        lineas_.append((linea, ancho_l))
        alto_l = tam * esc * 1.18
        y = H * s.get("y", 0.68) - alto_l * len(lineas_) / 2
        if anim == "subida":
            y += (1 - alfa) * 30
        borde = int(s.get("borde", 6))
        cb = color(s.get("color_borde", "#000000"))
        if s.get("caja"):
            cj = color(s["caja"])
            anchos = [a for _, a in lineas_]
            pad = tam * 0.3
            d.rounded_rectangle([W / 2 - max(anchos) / 2 - pad, y - pad * 0.6,
                                 W / 2 + max(anchos) / 2 + pad, y + alto_l * len(lineas_) + pad * 0.3],
                                radius=tam * 0.25, fill=cj[:3] + (int(cj[3] * alfa),))
            borde = 0
        for linea, ancho_l in lineas_:
            x = W / 2 - ancho_l / 2
            for txt, f, c, wpx in linea:
                ca = c[:3] + (int(c[3] * alfa),)
                if s.get("sombra"):
                    d.text((x + 4, y + 6), txt, font=f, fill=(0, 0, 0, int(110 * alfa)))
                d.text((x, y), txt, font=f, fill=ca, stroke_width=borde,
                       stroke_fill=cb[:3] + (int(cb[3] * alfa),))
                x += wpx + esp
            y += alto_l

    def caja_texto(self, img, texto, st, y_rel):
        from PIL import ImageDraw
        d = ImageDraw.Draw(img)
        tam = st.get("tam", 64)
        f = fuente(st.get("fuente", "montserrat"), st.get("peso", 900), tam)
        txt = texto.upper() if st.get("mayusculas", True) else texto
        # cada línea en su caja (estilo título de reel)
        filas = []
        for parte in txt.split("\n"):
            palabras = parte.split()
            fila = ""
            for p in palabras:
                prueba = (fila + " " + p).strip()
                if d.textlength(prueba, font=f) > W * 0.86 and fila:
                    filas.append(fila)
                    fila = p
                else:
                    fila = prueba
            if fila:
                filas.append(fila)
        alto = tam * 1.3
        y = H * y_rel - alto * len(filas) / 2
        for fila in filas:
            wpx = d.textlength(fila, font=f)
            if st.get("caja"):
                pad = tam * 0.3
                d.rounded_rectangle([W / 2 - wpx / 2 - pad, y - pad * 0.35, W / 2 + wpx / 2 + pad, y + tam * 1.12],
                                    radius=tam * 0.18, fill=color(st["caja"]))
            d.text((W / 2 - wpx / 2, y), fila, font=f, fill=color(st.get("color", "#000000")),
                   stroke_width=0 if st.get("caja") else int(st.get("borde", 6)),
                   stroke_fill=(0, 0, 0, 255))
            y += alto


# ---------------------------------------------------------------- render

def render(ruta_plan):
    import numpy as np
    with open(ruta_plan, encoding="utf-8") as f:
        plan = json.load(f)
    with open(plan["estilo"], encoding="utf-8") as f:
        est = json.load(f)
    with open(plan["palabras"], encoding="utf-8") as f:
        palabras = json.load(f)["palabras"]
    for k, v in plan.get("corregir", {}).items():
        palabras[int(k)]["w"] = v
    video = plan["video"]
    info = sonda(video)
    nombre = os.path.splitext(os.path.basename(plan["salida"]))[0]
    tmp = os.path.join("trabajo", "render_" + nombre)
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    os.makedirs(os.path.dirname(plan["salida"]) or ".", exist_ok=True)

    progreso("cortes", "Quitando silencios y muletillas")
    a, sr = leer_audio(video)
    clips = calcular_cortes(palabras, plan, db_ventanas(a, sr))
    del a

    # línea de tiempo de salida
    t_out, palabras_out, claves_out, cortes_out, mapa_out = 0.0, [], [], [], {}
    zoom_set = set(plan.get("zooms", []))
    claves = set(plan.get("claves", []))
    z_alt = est.get("zoom", {}).get("alterno", 1.0)
    z_golpe = est.get("zoom", {}).get("golpe", 1.15)
    for n, c in enumerate(clips):
        c["z"] = z_golpe if zoom_set & set(c["palabras"]) else (z_alt if n % 2 else 1.0)
        c["out"] = t_out
        cortes_out.append(round(t_out, 3))
        for i in c["palabras"]:
            p = palabras[i]
            mapa_out[i] = len(palabras_out)
            if i in claves:
                claves_out.append(len(palabras_out))
            palabras_out.append({"w": p["w"], "s": round(t_out + p["s"] - c["ini"], 3),
                                 "e": round(t_out + p["e"] - c["ini"], 3)})
        t_out += c["fin"] - c["ini"]
    total = round(t_out, 3)
    plan["_claves_out"], plan["_cortes_out"] = claves_out, cortes_out

    # 1) trozos de vídeo con encuadre, zoom y color
    col = filtro_color(est.get("color"))
    lista = []
    for n, c in enumerate(clips):
        progreso("montaje", f"Cortando trozo {n + 1} de {len(clips)}")
        dur = c["fin"] - c["ini"]
        vf = filtro_encuadre(info, est.get("encuadre", {}), c["z"]) + col + f",fps={FPS},format=yuv420p,setsar=1"
        af = f"afade=t=in:d=0.012,afade=t=out:st={max(0, dur - 0.015):.3f}:d=0.015,aresample=48000"
        out = os.path.join(tmp, f"c{n:04d}.mkv")
        cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{c['ini']:.3f}", "-i", video, "-t", f"{dur:.3f}",
               "-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]"]
        if info["audio"]:
            cmd += ["-map", "0:a:0", "-af", af, "-c:a", "pcm_s16le", "-ac", "2"]
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "16", out]
        run(cmd)
        lista.append(out)
    with open(os.path.join(tmp, "clips.txt"), "w", encoding="utf-8") as f:
        f.write("".join(f"file '{os.path.abspath(p)}'\n".replace("\\", "/") for p in lista))

    # 2) capa de textos: un PNG por cada cambio, encadenados con su duración
    progreso("textos", "Dibujando subtítulos y títulos")
    lz = Lienzo(est, palabras_out, plan, total)
    ts = lz.momentos()
    vacio = os.path.join(tmp, "vacio.png")
    from PIL import Image
    Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(vacio)
    capas = []
    for k in range(len(ts) - 1):
        t0, t1 = ts[k], ts[k + 1]
        if t1 - t0 < 0.5 / FPS:
            continue
        img = lz.dibujar(t0 + 0.001)
        ruta = vacio
        if img is not None:
            ruta = os.path.join(tmp, f"t{k:05d}.png")
            img.save(ruta, compress_level=1)
        capas.append((ruta, t1 - t0))
    with open(os.path.join(tmp, "textos.txt"), "w", encoding="utf-8") as f:
        f.write("ffconcat version 1.0\n")
        for ruta, dur in capas:
            f.write(f"file '{os.path.abspath(ruta)}'\nduration {dur:.4f}\n".replace("\\", "/"))
        f.write(f"file '{os.path.abspath(capas[-1][0] if capas else vacio)}'\n".replace("\\", "/"))

    # 3) montaje final: vídeo + overlays/b-roll + logo + textos + voz normalizada (+ música con ducking)
    progreso("render", "Renderizando el reel final")
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", os.path.join(tmp, "clips.txt"),
           "-f", "concat", "-safe", "0", "-i", os.path.join(tmp, "textos.txt")]
    n_in, fc, base = 2, [], "[0:v]"
    for k, ov in enumerate(plan.get("overlays", [])):
        if not os.path.exists(ov["archivo"]) or int(ov.get("en", -1)) not in mapa_out:
            print(f"Aviso: overlay saltado {ov}", file=sys.stderr)
            continue
        t0 = palabras_out[mapa_out[int(ov["en"])]]["s"]
        dur = min(float(ov.get("dur", 2.0)), total - t0)
        imagen = ov["archivo"].lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
        cmd += (["-loop", "1"] if imagen else []) + ["-t", f"{dur:.3f}", "-i", ov["archivo"]]
        if ov.get("modo", "completo") == "ventana":
            esc = "scale=760:760:force_original_aspect_ratio=decrease,pad=iw+12:ih+12:6:6:white"
            pos = "(W-w)/2:470"
        else:
            esc = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
            pos = "0:0"
        fc.append(f"[{n_in}:v]{esc},fps={FPS},format=yuva420p,setpts=PTS-STARTPTS+{t0:.3f}/TB[o{k}]")
        fc.append(f"{base}[o{k}]overlay={pos}:eof_action=pass:enable='between(t,{t0:.3f},{t0 + dur:.3f})'[b{k}]")
        base, n_in = f"[b{k}]", n_in + 1
    logo = plan.get("logo")
    if logo and os.path.exists(logo):
        lg = est.get("logo", {})
        cmd += ["-loop", "1", "-i", logo]
        pos = {"arriba_izq": "50:70", "abajo_der": "W-w-50:H-h-90", "abajo_izq": "50:H-h-90"}.get(
            lg.get("pos"), "W-w-50:70")
        fc.append(f"[{n_in}:v]scale={int(lg.get('ancho', 170))}:-1,format=rgba[lg]")
        fc.append(f"{base}[lg]overlay={pos}:shortest=1[bl]")
        base, n_in = "[bl]", n_in + 1
    fc.append(f"[1:v]format=rgba,fps={FPS}[tx];{base}[tx]overlay=0:0:eof_action=pass:format=auto,format=yuv420p[v]")
    musica = plan.get("musica")
    if info["audio"]:
        fc.append("[0:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[voz]")
        if musica and os.path.exists(musica):
            vol = est.get("musica", {}).get("volumen", 0.08)
            cmd += ["-stream_loop", "-1", "-i", musica]
            fc.append(f"[voz]asplit[v1][v2];[{n_in}:a]aresample=48000,volume={vol}[m];"
                      f"[m][v2]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=350[md];"
                      f"[v1][md]amix=inputs=2:duration=first:normalize=0[a]")
        else:
            fc.append("[voz]anull[a]")
    cmd += ["-filter_complex", ";".join(fc), "-map", "[v]"]
    if info["audio"]:
        cmd += ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
    cmd += ["-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-r", str(FPS), plan["salida"]]
    run(cmd)

    hoja(plan["salida"], os.path.join(tmp, "revision.jpg"))
    texto = " ".join(p["w"] for p in palabras_out)
    with open(os.path.join(tmp, "texto_final.txt"), "w", encoding="utf-8") as f:
        f.write(texto)
    shutil.copy(os.path.join(tmp, "revision.jpg"), os.path.join("trabajo", "ultima_revision.jpg"))
    for p in lista:
        os.remove(p)
    progreso("listo", plan["salida"])
    print(json.dumps({"salida": plan["salida"], "duracion": total, "trozos": len(clips),
                      "revision": os.path.join(tmp, "revision.jpg"), "texto": texto[:600]}, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    orden, args = sys.argv[1], sys.argv[2:]
    if orden == "comprobar":
        comprobar()
    elif orden == "referencia":
        referencia(args[0], args[1])
    elif orden == "transcribir":
        transcribir(args[0], args[1], *(args[2:3]))
    elif orden == "render":
        render(args[0])
    elif orden == "hoja":
        hoja(args[0], args[1])
    else:
        sys.exit(__doc__)
