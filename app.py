import io
import re
import zipfile
import time
from datetime import datetime

import streamlit as st
from PIL import Image

from google import genai
from google.genai import types

# Configuración y constantes
APP_TITLE = "SPRING OS — Direction → Visual Pack™"
APP_TAGLINE = "Dirección primero. Piezas después."
MODEL_IMAGE = "gemini-2.5-flash-image"
MAX_IMAGES_PER_RUN = 18

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
    return {"2/semana": 2, "3/semana": 3, "diario": 5}.get(freq, 2)

def _format_label_to_aspect(label: str) -> str:
    return {
        "Reel/Story (9:16)": "9:16",
        "Post (1:1)": "1:1",
        "Horizontal (16:9)": "16:9",
    }.get(label, "1:1")

def _zip_images(images: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for fn, b in images:
            z.writestr(fn, b)
    return buf.getvalue()

# Función de generación con Reintentos y Backoff
def _generate_image_bytes(api_key: str, prompt: str, aspect_ratio: str, retries=2) -> bytes:
    client = genai.Client(api_key=api_key)
    
    for attempt in range(retries + 1):
        try:
            resp = client.models.generate_content(
                model=MODEL_IMAGE,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
                ),
            )
            
            # Validación de candidatos
            if not resp.candidates or not resp.candidates[0].content.parts:
                raise RuntimeError("La IA bloqueó la imagen o devolvió una respuesta vacía.")

            for part in resp.candidates[0].content.parts:
                try:
                    img = part.as_image()
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    return buf.getvalue()
                except Exception:
                    continue
                    
        except Exception as e:
            # Manejo del error de cuota 429
            if "429" in str(e) and attempt < retries:
                wait_time = (attempt + 1) * 12 
                st.warning(f"Cuota agotada. Reintentando en {wait_time}s... (Intento {attempt + 1}/{retries})")
                time.sleep(wait_time)
            else:
                raise e
                
    raise RuntimeError("No se pudo generar la imagen tras los reintentos.")

# ----------------------------
# Prompt Engine
# ----------------------------
def _build_direction_summary(data: dict) -> str:
    return (
        f"Proyecto: {data['project']} · Prioridad: {data['priority']} · Tono: {data['tone']}\n"
        f"Oferta: {data['offer']}"
    )

def _hidden_prompt_for_piece(data: dict, piece_type: str, piece_idx: int, aspect_ratio: str) -> str:
    return f"""
Genera UNA imagen profesional para redes sociales. 
Proyecto: {data['project']}. Tono: {data['tone']}. Estilo: {data['visual_style']}.
Paleta: {data['palette_hint']}. Formato: {aspect_ratio}.
Tipo: {piece_type}. Variación: {piece_idx}.
Evitar: {data['avoid']}. Incluir: {data['must_include']}.
Máximo 6 palabras de texto si es necesario.
""".strip()

# ----------------------------
# UI Streamlit
# ----------------------------
st.set_page_config(page_title=APP_TITLE, page_icon="🎛️", layout="centered")
st.title(APP_TITLE)
st.caption(APP_TAGLINE)

if "step" not in st.session_state:
    st.session_state.step = 1

with st.sidebar:
    st.markdown("### Acceso")
    api_key = st.text_input("Google API Key", type="password")

# PASO 1: DIRECCIÓN
if st.session_state.step == 1:
    st.markdown("## 1) Dirección")
    project = st.text_input("Proyecto", value="SPRING")
    priority = st.selectbox("Prioridad", ["Venta", "Promo", "Branding", "Comunidad"])
    freq = st.selectbox("Frecuencia", ["2/semana", "3/semana", "diario"], index=0)
    tone = st.text_input("Tono", value="Estratégico y claro")
    offer = st.text_input("Oferta", value="Servicio Digital")
    
    st.markdown("#### Estética")
    visual_style = st.selectbox("Estilo", ["Tech claro", "Minimalista premium", "Vibrante pro"])
    palette_hint = st.text_input("Paleta", value="rosa suave + verde oscuro")
    must_include = st.text_input("Incluir", value="nombre de marca")
    avoid = st.text_input("Evitar", value="exceso de texto")

    if st.button("Siguiente →", type="primary", use_container_width=True):
        st.session_state.data = {
            "project": project, "priority": priority, "freq": freq, "tone": tone,
            "offer": offer, "visual_style": visual_style, "palette_hint": palette_hint,
            "must_include": must_include, "avoid": avoid
        }
        st.session_state.step = 2
        st.rerun()

# PASO 2: PIEZAS Y FORMATO
if st.session_state.step == 2:
    st.markdown("## 2) Configuración del Pack")
    pieces = st.multiselect("Piezas", ["Post promo", "Post educativo", "Story CTA"], default=["Post promo"])
    formats = st.multiselect("Formatos (Elegir 1 recomendado)", ["Reel/Story (9:16)", "Post (1:1)", "Horizontal (16:9)"], default=["Post (1:1)"])

    if st.button("Siguiente →", type="primary"):
        st.session_state.data["pieces"] = pieces
        st.session_state.data["formats"] = formats
        st.session_state.step = 3
        st.rerun()

# PASO 3: GENERACIÓN
if st.session_state.step == 3:
    data = st.session_state.data
    st.markdown("## 3) Generando Visual Pack™")
    
    if st.button("Generar imágenes", type="primary"):
        if not api_key:
            st.error("Falta API Key.")
            st.stop()
            
        outputs = []
        run_id = f"{_slug(data['project'])}_{_now()}"
        posts_per_week = _freq_to_posts_per_week(data["freq"])
        
        with st.spinner("Procesando con IA..."):
            for i in range(1, posts_per_week + 1):
                for piece in data["pieces"]:
                    # Forzamos formato único para estabilidad
                    fmt = data["formats"][0] if data["formats"] else "Post (1:1)"
                    aspect = _format_label_to_aspect(fmt)
                    prompt = _hidden_prompt_for_piece(data, piece, i, aspect)
                    
                    try:
                        img_bytes = _generate_image_bytes(api_key, prompt, aspect)
                        fn = f"{run_id}/{_slug(piece)}_var{i}.png"
                        outputs.append((fn, img_bytes))
                        time.sleep(2) # Pausa de cortesía para la API
                    except Exception as e:
                        st.error(f"Fallo crítico: {e}")
                        st.stop()
        
        st.session_state.outputs = outputs
        st.success("¡Pack listo!")

    if "outputs" in st.session_state:
        zip_data = _zip_images(st.session_state.outputs)
        st.download_button("Descargar Pack (.zip)", data=zip_data, file_name="spring_pack.zip", mime="application/zip")
