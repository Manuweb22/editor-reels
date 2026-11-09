# Editor de reels

Pegas el enlace de un reel que te guste, subes tu vídeo y Claude te lo edita con ese estilo: cortes de silencios y muletillas, subtítulos, título, zooms, overlays, logo, música y CTA. Todo se hace en tu ordenador, con un panel visual al lado del chat de Claude.

Funciona en Windows y en Mac, con la app de escritorio de Claude (pestaña **Code**) y un plan Pro o Max.

## Instalarlo (una vez)

1. Crea una carpeta para tus reels, por ejemplo `Documentos/EditorReels`, y ábrela en la pestaña **Code** de Claude.
2. Pulsa **+** junto a la caja de texto → **Plugins** → **Add marketplace** y escribe `Manuweb22/editor-reels` → **Add plugin** → `editor-reels`.
3. Escribe en el chat: **abre el editor**. La primera vez Claude instala lo que falta (Python, ffmpeg y el modelo de transcripción: unos minutos y ~2 GB) y te pedirá permiso para cada cosa.

Desde una terminal también vale: `claude plugin install editor-reels --marketplace Manuweb22/editor-reels`.

## Usarlo

1. Escribe **abre el editor**: el panel se abre a la derecha.
2. Pega el enlace del reel que quieres copiar, sube tu vídeo y, si quieres, tu logo, tu música y tus overlays.
3. Pulsa **Crear reel** y escribe **hazlo** en el chat.
4. Para retocar: escribe el cambio en el panel, pulsa **Editar** y luego **hazlo**.

Tus reels quedan en la carpeta `salida/`. Los estilos que copias se guardan en `estilos/` para reutilizarlos.
