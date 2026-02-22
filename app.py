import io
import re
import zipfile
import time
from datetime import datetime

import streamlit as st
from PIL import Image

from google import genai
from google.genai import types

# ----------------------------
# Configuración y Constantes
# ----------------------------
APP_TITLE = "SPRING OS — Direction → Visual Pack™"
APP_TAGLINE = "Dirección primero. Piezas después."
# Usamos gemini-2.0-flash para mayor estabilidad en generación
MODEL_IMAGE = "gemini-2.0-flash" 
MAX_IMAGES_PER_RUN = 18

# ----------------------------
# Helpers Técnicos
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

# ----------------------------
# Motor de Generación con Resiliencia
# ----------------------------
def _generate_image_bytes(api_key: str, prompt: str, aspect_ratio: str, retries=2) -> bytes:
    """
    Gestiona la generación de imagen con backoff exponencial para evitar el error 429.
    """
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
            
            # Validación de seguridad y contenido
            if not resp.candidates or not resp.candidates[0].content.parts:
                raise RuntimeError("La IA bloqueó la imagen por filtros de seguridad.")

            for part in resp.candidates[0].content.parts:
                img = part.as_image()
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                return buf.getvalue()
                
        except Exception as e:
            # Captura el error de cuota excedida detectado en la captura
            if "429" in str(e) and attempt < retries:
                wait_time = (attempt + 1) * 15 
                st.warning(f"Límite de cuota (429). Reintentando en {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise e
                
    raise RuntimeError("No se pudo completar la generación tras los reintentos.")

# ----------------------------
# Prompt Engine (Oculto)
# ----------------------------
def _hidden_prompt_for_piece(data: dict, piece_type: str, piece_idx: int, aspect_ratio: str) -> str:
    return f"""
Genera UNA imagen publicitaria profesional.
Proyecto: {data['project']}
Estilo Visual: {data['visual_style']}
Paleta: {data['palette_hint']}
Objetivo: {data['priority']}
Tipo de pieza: {piece_type}
Variación: {piece_idx}
Formato: {aspect_ratio}
Reglas: Fotografía de alta gama, evitar plantillas, texto máximo 5 palabras.
""".strip()

# ----------------------------
# Interfaz de Usuario (UI)
# ----------------------------
st.set_page_config(page_title=APP_TITLE, page_icon="🎛️", layout="centered")
st.title(APP_TITLE)
st.caption(APP_TAGLINE)

if "step" not in st.session_state:
    st.session_state.step = 1

with st.sidebar:
    st.markdown("### Acceso")
    api_key = st.text_input("Google API Key", type="password")
    st.caption("Obtén tu key en Google AI Studio.")

# PASO 1 — Dirección
if st.session_state.step == 1:
    st.markdown("## 1) Dirección Estratégica")
    project = st.text_input("Nombre del Proyecto", value="SPRING")
    priority = st.selectbox("Prioridad del Mes", ["Venta", "Branding", "Comunidad"])
    freq = st.selectbox("Frecuencia", ["2/semana", "3/semana", "diario"])
    tone = st.text_input("Tono", value="Sofisticado y minimalista")
    
    st.markdown("#### Dirección Visual")
    visual_style = st.selectbox("Estilo", ["Tech claro", "Minimalista premium", "Moderno disruptivo"])
    palette_hint = st.text_input("Paleta de colores", value="Verde bosque + Beige")
    must_include = st.text_input("Incluir", value="Producto en primer plano")
    avoid = st.text_input("Evitar", value="Colores chillones, mucho texto")

    if st.button("Configurar Piezas →", type="primary", use_container_width=True):
        st.session_state.data = {
            "project": project, "priority": priority, "freq": freq, "tone": tone,
            "visual_style": visual_style, "palette_hint": palette_hint,
            "must_include": must_include, "avoid": avoid
        }
        st.session_state.step = 2
        st.rerun()

# PASO 2 — Configuración del Pack
if st.session_state.step == 2:
    st.markdown("## 2) Configuración del Pack")
    pieces = st.multiselect("Tipos de piezas", ["Post promo", "Post educativo", "Story gancho"], default=["Post promo"])
    # Recomendamos 1 solo formato para no saturar la cuota
    formats = st.multiselect("Formatos", ["Reel/Story (9:16)", "Post (1:1)", "Horizontal (16:9)"], default=["Post (1:1)"])

    c1, c2 = st.columns(2)
    with c1:
        if st.button("← Volver"):
            st.session_state.step = 1
            st.rerun()
    with c2:
        if st.button("Siguiente →", type="primary"):
            st.session_state.data["pieces"] = pieces
            st.session_state.data["formats"] = formats
            st.session_state.step = 3
            st.rerun()

# PASO 3 — Generación Final
if st.session_state.step == 3:
    st.markdown("## 3) Generación del Visual Pack™")
    data = st.session_state.data
    
    if st.button("🚀 Generar Imágenes", type="primary", use_container_width=True):
        if not api_key:
            st.error("Por favor, introduce tu API Key en la barra lateral.")
            st.stop()
            
        outputs = []
        run_id = f"{_slug(data['project'])}_{_now()}"
        posts_per_week = _freq_to_posts_per_week(data["freq"])
        
        with st.spinner("Generando activos con IA..."):
            for i in range(1, posts_per_week + 1):
                for piece_type in data["pieces"]:
                    # Procesamos el formato principal seleccionado
                    fmt = data["formats"][0] if data["formats"] else "Post (1:1)"
                    aspect = _format_label_to_aspect(fmt)
                    prompt = _hidden_prompt_for_piece(data, piece_type, i, aspect)
                    
                    try:
                        img_bytes = _generate_image_bytes(api_key, prompt, aspect)
                        fn = f"{run_id}/{_slug(piece_type)}_v{i}.png"
                        outputs.append((fn, img_bytes))
                        # Pausa de seguridad para no saturar la API
                        time.sleep(2) 
                    except Exception as e:
                        st.error(f"Error en {piece_type}: {e}")
                        st.stop()
        
        st.session_state.outputs = outputs
        st.success("¡Pack visual generado con éxito!")

    if "outputs" in st.session_state:
        zip_data = _zip_images(st.session_state.outputs)
        st.download_button(
            label="⬇️ Descargar todo el Pack (.zip)",
            data=zip_data,
            file_name=f"spring_pack_{_now()}.zip",
            mime="application/zip",
            use_container_width=True
        )
