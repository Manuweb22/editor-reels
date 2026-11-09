---
name: editor-reels
description: Editor de reels con panel visual. Úsala cuando la persona quiera editar un vídeo copiando el estilo de un reel de ejemplo, diga "hazlo", "crea mi reel", "edita mi vídeo", "copia este estilo", "abre el editor", "cambia el reel", o pida instalar o abrir el editor de reels.
---

# Editor de reels

La persona pega el enlace de un reel de ejemplo en el panel, sube su vídeo, sus recursos y sus overlays, y te escribe "hazlo". Tú copias el estilo del ejemplo y montas su reel vertical con `motor/editor.py`. Háblale en español, corto y cercano: no es técnica. Nunca le enseñes comandos ni JSON salvo que lo pida.

## Rutas

- Raíz del plugin = dos carpetas por encima de la de esta skill (la "Base directory" que te da el sistema). Ahí están `instalar.py`, `motor/editor.py`, `motor/servidor.py` y `fuentes/`.
- Carpeta de trabajo = la carpeta abierta en esta sesión. Todo lo de la persona vive ahí: `entrada/` (sus brutos), `recursos/` (logo, música), `overlays/` (b-roll), `estilos/`, `salida/` (reels), `trabajo/` (temporales).
- Python del editor: Windows `%USERPROFILE%\.editor-reels\venv\Scripts\python.exe`; Mac `~/.editor-reels/venv/bin/python`. Lánzalo siempre con ese Python y desde la carpeta de trabajo: `<python> "<raíz>/motor/editor.py" <orden> …`.

## Primera vez (si no existe `~/.editor-reels/config.json` o `.claude/launch.json` en la carpeta)

1. Dile que vas a preparar el editor una sola vez (unos minutos, se baja ~2 GB).
2. Ejecuta `python "<raíz>/instalar.py" "<carpeta de trabajo>"` (en Windows prueba `py -3.12`, luego `python`).
   - Si sale `NECESITA_PYTHON_312`: en Windows `winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements`; en Mac `brew install python@3.12`. Después usa la ruta completa del Python nuevo (Windows: `%LOCALAPPDATA%\Programs\Python\Python312\python.exe`).
   - Si sale `NECESITA_FFMPEG`: Windows `winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements`; Mac `brew install ffmpeg`. Vuelve a lanzar el instalador (encuentra ffmpeg aunque el PATH no se haya refrescado).
   - Si no hay `winget` o `brew`, o algo pide contraseña de administrador, explícale en una frase qué tiene que hacer ella y espera.
3. Abre el panel (siguiente apartado).

## Abrir el panel

Llama a `preview_start` con `name: "editor-reels"` (lo crea el instalador en `.claude/launch.json`). Así el panel se queda a la derecha del chat. Si la persona dice "abre el editor", haz solo esto y dile que pegue el enlace, suba su vídeo y te escriba "hazlo".

## Cuando dice "hazlo": lee `trabajo/peticion.json`

Si `estado` no es `pendiente` y no ha pedido nada en el chat, pregúntale qué quiere. Pon `estado: "en curso"` al empezar y `estado: "hecho"` al terminar (el panel lo lee). Guarda en `plan` la ruta del plan.

### tipo "crear"

1. `editor.py referencia "<enlace>" trabajo/referencia_<n>` (n = siguiente número libre). Si Instagram no deja bajarlo, pídele que suba el reel de ejemplo como archivo a `entrada/` y pasa esa ruta en lugar del enlace.
2. Mira SOLO `hoja_general.jpg`, `hoja_animacion.jpg` y `gancho.jpg` de esa carpeta y lee `referencia.json` (ritmo, palabras por segundo, si hay música). Fíjate en: posición, tamaño, tipo de letra (gruesa/fina/serif), mayúsculas, cuántas palabras salen a la vez, cómo entran (golpe, fundido, palabra a palabra), color de la palabra activa o clave, caja o borde, título fijo arriba, b-roll, color de la imagen, zooms.
3. Escribe `estilos/<nombre-corto>.json` (esquema abajo) con 4-6 `etiquetas` cortas que lo describan ("Subtítulos amarillos", "Zoom en cortes"…).
4. `editor.py transcribir "<video>" trabajo/<nombre_video>` (tarda ~la mitad de lo que dura el vídeo; avísale). Lee `lineas.txt` y mira `hoja.jpg` para ver el encuadre. No leas `palabras.json` entero.
5. Escribe `trabajo/<nombre_video>/plan.json` (esquema abajo). Reglas de montaje:
   - Gancho: la primera palabra suena en el segundo 0. Si la mejor frase está en medio, súbela al principio (1-4 s) y luego sigue el orden.
   - Quita arranques fallidos, tomas repetidas (deja siempre la última buena), frases que se corrigen y muletillas ("o sea", "bueno" al empezar, "¿vale?"). Nunca quites contenido que aporta.
   - Duración: la que pida en `nota`; si no, 30-75 s.
   - `claves`: 1 palabra fuerte cada 5-8 s. `zooms`: 2-4 momentos de golpe.
   - `corregir`: nombres, marcas y cifras mal transcritos.
   - Recursos: si hay `.png` en `recursos/` con "logo" en el nombre → `logo`. Si hay audio en `recursos/` y el ejemplo tiene música → `musica`. Fuentes propias aún no se usan: díselo si sube alguna.
   - Overlays: usa solo archivos de `overlays/`. Ponlos donde la frase hable de lo que se ve (1,5-3 s, `ventana` o `completo` según el ejemplo). Nunca bajes b-roll de internet.
   - CTA de la `nota` → `cierre` (ej. "COMENTA SESIÓN").
6. `editor.py render trabajo/<nombre_video>/plan.json`. Salida `salida/<nombre_video>_v1.mp4`.
7. Mira el `revision.jpg` que devuelve y lee el texto final. Si algo está mal (texto tapando la cara, frase cortada, subtítulo fuera de pantalla), corrige y renderiza otra vez antes de entregar.
8. Dile en 2-3 frases qué has copiado del ejemplo y que ya lo tiene en el panel.

### tipo "cambio"

Lee el campo `cambio`, ajusta el `plan.json` y/o el estilo (si cambias el estilo, guárdalo con otro nombre para no romper reels anteriores), sube el número de versión en `salida` (`_v2`, `_v3`…) y renderiza. No vuelvas a analizar la referencia ni a transcribir.

### Peticiones por el chat

Si pide algo directamente en el chat (sin panel), haz lo mismo con lo que te diga. Si quiere reutilizar un estilo guardado, usa `estilos/<x>.json` y sáltate la referencia.

## Ahorro (muchas personas usan el plan Pro)

- Una sola mirada a las 3 imágenes de la referencia y otra a `revision.jpg`. No abras vídeos ni fotogramas sueltos salvo para corregir un fallo concreto.
- Respuestas cortas. Nada de explicar el proceso paso a paso.

## Esquema del estilo (`estilos/*.json`)

```json
{
 "nombre": "Podcast oscuro, palabra a palabra",
 "etiquetas": ["Palabra a palabra", "Claves en negrita", "Color de cine", "Zoom en cortes"],
 "subtitulos": {
  "activo": true,
  "fuente": "montserrat | anton | playfair",
  "peso": 800, "tam": 80, "mayusculas": true,
  "palabras": 3, "y": 0.68, "ancho": 0.84,
  "color": "#FFFFFF", "color_activa": "#FFE600", "resaltar_activa": true,
  "inactivas_tenues": false, "color_inactiva": "#FFFFFF99",
  "color_clave": "#FF3B30", "fuente_clave": "playfair", "peso_clave": 700,
  "borde": 6, "color_borde": "#000000", "sombra": true, "caja": null,
  "animacion": "pop | palabra | fundido | subida | ninguna",
  "quitar_puntuacion": true
 },
 "titulo": {"activo": true, "fuente": "montserrat", "peso": 900, "tam": 58, "y": 0.13,
            "color": "#000000", "caja": "#FFFFFF", "duracion": "todo"},
 "encuadre": {"modo": "recorte | desenfocado | negro", "centro_x": 0.5},
 "zoom": {"alterno": 1.07, "golpe": 1.15},
 "flash_cortes": false,
 "color": {"brillo": 0.0, "contraste": 1.05, "saturacion": 1.0, "temperatura": 6500},
 "musica": {"volumen": 0.08},
 "logo": {"pos": "arriba_der | arriba_izq | abajo_der | abajo_izq", "ancho": 170},
 "cierre": {"fuente": "montserrat", "tam": 110, "color": "#FFFFFF", "caja": null, "y": 0.74}
}
```

Notas: `mayusculas` puede ser `true`, `false` o `"titulo"` (Cada Palabra Así). `y` es la altura (0 arriba, 1 abajo); deja los subtítulos fuera de la cara. `animacion: "palabra"` = van apareciendo palabra a palabra dentro del bloque. `caja` es un color con transparencia (`"#000000B0"`) o `null`. `encuadre.modo` solo cuenta si su vídeo es horizontal: `recorte` corta al centro (ajusta `centro_x` si la persona no está centrada), `desenfocado` pone el vídeo entero sobre fondo borroso. `color.temperatura` en kelvin (menos = más cálido).

## Esquema del plan (`trabajo/<video>/plan.json`)

```json
{
 "video": "entrada/mi_video.mp4",
 "palabras": "trabajo/mi_video/palabras.json",
 "estilo": "estilos/podcast_oscuro.json",
 "salida": "salida/mi_video_v1.mp4",
 "tramos": [[86, 101], [0, 10], [17, 41]],
 "claves": [3, 67], "zooms": [3],
 "corregir": {"139": "lastre"},
 "titulo": "POR QUÉ NO VENDES\nTU SESIÓN",
 "cierre": "COMENTA SESIÓN",
 "logo": "recursos/logo.png",
 "musica": "recursos/musica.mp3",
 "overlays": [{"archivo": "overlays/gym.mp4", "en": 113, "dur": 2.2, "modo": "ventana"}],
 "quitar_muletillas": true,
 "pausa_max": 0.22
}
```

`tramos` son rangos de índices de palabra (los de `lineas.txt`, ambos incluidos) en el orden en que salen. Dentro de cada tramo el motor ya quita los silencios largos y las muletillas tipo "eh/mmm". `claves`, `zooms`, `corregir` y `overlays.en` usan índices de palabra del vídeo original. `titulo` y `cierre` solo si el estilo los tiene o ella los pide; vacío o ausente = no sale.

## Límites (dilo si lo pide)

- Copia el estilo, no el contenido ni la música del reel de ejemplo.
- No publica en redes; el reel queda en `salida/`.
- Fuentes propias, emojis animados y efectos 3D aún no están.
