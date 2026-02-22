import io
import re
import zipfile
from datetime import datetime

import streamlit as st
from PIL import Image

from google import genai
from google.genai import types

APP_TITLE = "SPRING OS — Direction → Visual Pack™"
APP_TAGLINE = "Dirección primero. Piezas después."
MODEL_IMAGE = "gemini-2.5-flash-image"

MAX_IMAGES_PER_RUN = 18  # guardrail para no quemar tokens/tiempo


# ----------------------------
# Helpers
# ----------------------------
def _slug(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9áéíóúñü\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    return s[:60] or "spring"


def _now() -> str:
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")


def _freq_to_posts_per_week(freq: str) -> int:
    # Realista para redes: diario = 5/semana (no 7)
    return {"2/semana": 2, "3/semana": 3, "diario": 5}.get(freq, 2)


def _format_label_to_aspect(label: str) -> str:
    return {
        "Reel/Story (9:16)": "9:16",
        "Post (1:1)": "1:1",
        "Horizontal (16:9)": "16:9",
    }[label]


def _zip_images(images: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for fn, b in images:
            z.writestr(fn, b)
    return buf.getvalue()


def _generate_image_bytes(api_key: str, prompt: str, aspect_ratio: str) -> bytes:
    client = genai.Client(api_key=api_key)

    resp = client.models.generate_content(
        model=MODEL_IMAGE,
        contents=[prompt],
        config=types.GenerateContentConfig(
            image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
        ),
    )

    for part in resp.candidates[0].content.parts:
        try:
            img = part.as_image()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception:
            continue

    raise RuntimeError("No se recibió imagen en la respuesta.")


# ----------------------------
# Prompt engine (oculto)
# ----------------------------
def _build_direction_summary(data: dict) -> str:
    """
    No llama a IA. Solo arma una "brújula" clara para que la usuaria entienda qué se va a generar.
    (En TP se ve más 'producto' y menos 'chat'.)
    """
    return (
        f"Proyecto: {data['project']} · Prioridad: {data['priority']} · Frecuencia: {data['freq']} · Tono: {data['tone']}\n"
        f"Oferta: {data['offer']}\n"
        f"Campaña/promo: {data['promo'] if data['promo'] else '—'}"
    )


def _hidden_prompt_for_piece(data: dict, piece_type: str, piece_idx: int, aspect_ratio: str) -> str:
    """
    Prompt interno. La usuaria NO escribe esto.
    """
    base = f"""
Genera UNA imagen lista para redes sociales (alta calidad, composición profesional).
Proyecto: {data['project']}
Objetivo del mes: {data['priority']}
Tono: {data['tone']}
Oferta: {data['offer']}
Campaña/promo: {data['promo']}

Dirección visual:
- Estilo: {data['visual_style']}
- Paleta de referencia: {data['palette_hint']}
- Formato/aspect ratio: {aspect_ratio}

Reglas:
- Evitar estética de plantilla barata.
- Si hay texto, que sea mínimo (máx 6 palabras) y legible.
- Evitar: {data['avoid']}
- Incluir si aplica: {data['must_include']}

Tipo de pieza: {piece_type}
Variación #{piece_idx}: distinta, pero coherente con la marca.
Devuelve SOLO la imagen.
""".strip()

    return base


# ----------------------------
# UI
# ----------------------------
st.set_page_config(page_title=APP_TITLE, page_icon="🎛️", layout="centered")
st.title(APP_TITLE)
st.caption(APP_TAGLINE)

if "step" not in st.session_state:
    st.session_state.step = 1

with st.sidebar:
    st.markdown("### Acceso")
    api_key = st.text_input("Google API Key", type="password", placeholder="Pegá tu key acá")
    st.caption("Tu key no se guarda. Se usa solo en esta sesión.")


# STEP 1 — Dirección (preguntas)
if st.session_state.step == 1:
    st.markdown("## 1) Dirección")
    st.info("Con esto alcanza para darte un rumbo y armar el pack. Después elegís piezas.")

    project = st.text_input("Proyecto", value="SPRING")

    priority = st.selectbox(
        "Prioridad del mes (una)",
        ["Venta", "Promo puntual", "Branding (marca)", "Comunidad (interacción y vínculo)"],
        index=1,
    )

    freq = st.selectbox("Frecuencia real", ["2/semana", "3/semana", "diario"], index=1)
    st.caption("Tip: si dudás, elegí la opción más baja. Cumplir > fantasear.")

    tone = st.selectbox(
        "Tono de mensajes",
        [
            "Estratégico y claro",
            "Cercano y didáctico",
            "Sofisticado y minimalista",
            "Directo y ejecutivo",
            "Inspirador pero realista",
        ],
        index=0,
    )

    offer = st.text_input("Oferta (1 línea)", value="Servicio / consultoría / producto digital")
    promo = st.text_input("Campaña/promo (si aplica)", value="")

    st.markdown("#### Dirección visual (rápida)")
    visual_style = st.selectbox(
        "Estilo",
        [
            "Tech claro (limpio, ordenado, UI-ish)",
            "Minimalista premium (aireado, editorial)",
            "Vibrante pro (energía con control)",
            "Cálido humano (simple, sin infantilizar)",
            "Moderno disruptivo (composición audaz)",
        ],
        index=0,
    )

    palette_hint = st.text_input("Paleta (referencia)", value="rosa suave + verde oscuro + beige (sofisticado)")
    must_include = st.text_input("Incluir (si aplica)", value="nombre de marca / precio / fecha")
    avoid = st.text_input("Evitar", value="exceso de texto, template barato, colores sin control")

    if st.button("Siguiente →", type="primary", use_container_width=True):
        st.session_state.data = {
            "project": project.strip(),
            "priority": priority,
            "freq": freq,
            "tone": tone,
            "offer": offer.strip(),
            "promo": promo.strip(),
            "visual_style": visual_style,
            "palette_hint": palette_hint.strip(),
            "must_include": must_include.strip(),
            "avoid": avoid.strip(),
        }
        st.session_state.step = 2
        st.rerun()


# STEP 2 — Qué gráficas querés
if st.session_state.step == 2:
    data = st.session_state.data

    st.markdown("## 2) ¿Qué piezas querés generar?")
    st.info("Elegí qué pack necesitás. Después generamos las imágenes.")

    st.code(_build_direction_summary(data), language="text")

    pieces = st.multiselect(
        "Tipos de piezas",
        [
            "Post promo (oferta / precio)",
            "Post educativo (tip rápido)",
            "Post prueba social (testimonio / resultado)",
            "Story 1 (gancho)",
            "Story 2 (explicación corta)",
            "Story 3 (CTA)",
            "Portada de highlight",
        ],
        default=["Post promo (oferta / precio)", "Post educativo (tip rápido)"],
    )

    formats = st.multiselect(
        "Formatos",
        ["Reel/Story (9:16)", "Post (1:1)", "Horizontal (16:9)"],
        default=["Reel/Story (9:16)", "Post (1:1)"],
    )

    posts_per_week = _freq_to_posts_per_week(data["freq"])
    n_types = max(1, len(pieces))
    n_formats = max(1, len(formats))

    total_images = posts_per_week * n_types * n_formats
    st.caption(
        f"Estimación: {posts_per_week} piezas/semana × {n_types} tipos × {n_formats} formatos = {total_images} imágenes."
    )

    if total_images > MAX_IMAGES_PER_RUN:
        st.warning("Está quedando grande para una sola corrida. Bajá tipos o formatos para hacerlo rápido.")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("← Volver", use_container_width=True):
            st.session_state.step = 1
            st.rerun()
    with c2:
        if st.button("Siguiente →", type="primary", use_container_width=True):
            st.session_state.data["pieces"] = pieces
            st.session_state.data["formats"] = formats
            st.session_state.step = 3
            st.rerun()


# STEP 3 — Generar imágenes
if st.session_state.step == 3:
    data = st.session_state.data

    st.markdown("## 3) Tu pack visual")
    st.info("Un click y aparecen las imágenes. Después podés descargarlas todas juntas.")

    pieces = data.get("pieces", [])
    formats = data.get("formats", [])

    if not pieces or not formats:
        st.error("Te falta elegir tipos de pieza y formatos.")
        st.stop()

    posts_per_week = _freq_to_posts_per_week(data["freq"])
    total_images = posts_per_week * len(pieces) * len(formats)

    st.write(
        f"**Pack:** {posts_per_week} variaciones × {len(pieces)} tipos × {len(formats)} formatos = **{total_images}** imágenes"
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("← Volver", use_container_width=True):
            st.session_state.step = 2
            st.rerun()
    with c2:
        generate = st.button("Generar imágenes", type="primary", use_container_width=True)

    if generate:
        if not api_key:
            st.error("Te falta la API key.")
            st.stop()

        if total_images > MAX_IMAGES_PER_RUN:
            st.error("Demasiadas imágenes para una sola corrida. Bajá tipos o formatos.")
            st.stop()

        run_id = f"{_slug(data['project'])}_{_now()}_{_slug(data['priority'])}"
        outputs: list[tuple[str, bytes]] = []

        with st.spinner("Generando…"):
            for i in range(1, posts_per_week + 1):
                for piece_type in pieces:
                    for fmt in formats:
                        aspect = _format_label_to_aspect(fmt)
                        prompt = _hidden_prompt_for_piece(data, piece_type, i, aspect)

                        try:
                            img_bytes = _generate_image_bytes(api_key, prompt, aspect_ratio=aspect)
                        except Exception as e:
                            st.error(f"Falló ({piece_type} · {fmt} · var {i}): {type(e).__name__}: {e}")
                            st.stop()

                        fn = f"{run_id}/{_slug(piece_type)}_var{i:02d}_{aspect.replace(':','x')}.png"
                        outputs.append((fn, img_bytes))

        st.session_state.outputs = outputs
        st.success("Listo. Pack generado.")

    outputs = st.session_state.get("outputs", [])
    if outputs:
        st.markdown("### Preview")
        # Mostrar una preview acotada (para no cargar UI)
        preview_count = min(6, len(outputs))
        cols = st.columns(3)
        for idx in range(preview_count):
            fn, b = outputs[idx]
            with cols[idx % 3]:
                st.image(b, caption=fn.split("/")[-1], use_container_width=True)

        zip_bytes = _zip_images(outputs)
        st.download_button(
            "Descargar todo (.zip)",
            data=zip_bytes,
            file_name=f"{st.session_state.get('run_id','spring_pack')}.zip",
            mime="application/zip",
            use_container_width=True,
        )
