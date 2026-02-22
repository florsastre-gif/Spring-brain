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
# 1. Configuración y Modelo
# ----------------------------
# Cambiamos a 'gemini-2.0-flash' que es la versión estable para generación multimedia
APP_TITLE = "SPRING OS — Visual Pack™"
MODEL_IMAGE = "gemini-2.0-flash" 

# ----------------------------
# 2. Helpers Técnicos
# ----------------------------
def _slug(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9áéíóúñü\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    return s[:60] or "spring"

def _zip_images(images: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for fn, b in images:
            z.writestr(fn, b)
    return buf.getvalue()

# ----------------------------
# 3. Motor de Generación con Resiliencia
# ----------------------------
def _generate_image_bytes(api_key: str, prompt: str, aspect_ratio: str, retries=2) -> bytes:
    """
    Gestiona la generación con soporte para reintentos ante cuota agotada.
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
            
            if not resp.candidates or not resp.candidates[0].content.parts:
                raise RuntimeError("La IA no devolvió contenido visual válido.")

            for part in resp.candidates[0].content.parts:
                img = part.as_image()
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                return buf.getvalue()
                
        except Exception as e:
            # Manejo de error de cuota 429
            if "429" in str(e) and attempt < retries:
                wait_time = 30 
                st.warning(f"Límite alcanzado. Esperando {wait_time}s para reintentar...")
                time.sleep(wait_time)
            else:
                raise e
    raise RuntimeError("Error de conexión o cuota con Google AI Studio.")

# ----------------------------
# 4. Interfaz de Usuario (UI)
# ----------------------------
st.set_page_config(page_title=APP_TITLE, page_icon="🎛️")
st.title(APP_TITLE)

if "step" not in st.session_state: 
    st.session_state.step = 1

with st.sidebar:
    st.header("🔑 Configuración")
    api_key = st.text_input("Google API Key", type="password")

# PASO 1: DIRECCIÓN
if st.session_state.step == 1:
    st.subheader("1) Dirección Estratégica")
    project = st.text_input("Proyecto", value="SPRING")
    style = st.selectbox("Estilo Visual", ["Minimalista Premium", "Tech Moderno", "Vibrante"])
    
    if st.button("Siguiente →", type="primary", use_container_width=True):
        st.session_state.data = {"project": project, "style": style}
        st.session_state.step = 2
        st.rerun()

# PASO 2: CONFIGURACIÓN (Límite de 3 imágenes)
if st.session_state.step == 2:
    st.subheader("2) Configuración del Pack")
    st.info("Máximo 3 imágenes para asegurar estabilidad en el tier gratuito.")
    
    num_imgs = st.slider("Cantidad de variaciones", 1, 3, 1)
    fmt = st.selectbox("Formato", ["Post (1:1)", "Story (9:16)"])

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Volver"):
            st.session_state.step = 1
            st.rerun()
    with col2:
        if st.button("🚀 Generar Pack", type="primary"):
            st.session_state.data["num_imgs"] = num_imgs
            st.session_state.data["fmt"] = fmt
            st.session_state.step = 3
            st.rerun()

# PASO 3: GENERACIÓN FINAL
if st.session_state.step == 3:
    st.subheader("3) Tu Visual Pack™")
    data = st.session_state.data
    
    if st.button("Iniciar Generación", type="primary", use_container_width=True):
        if not api_key: 
            st.error("Falta la API Key en la barra lateral.")
            st.stop()
        
        outputs = []
        progress_bar = st.progress(0)
        
        with st.spinner("Generando piezas con IA..."):
            for i in range(data["num_imgs"]):
                try:
                    aspect = "1:1" if "1:1" in data["fmt"] else "9:16"
                    prompt = f"Professional {data['style']} brand visual for {data['project']}. High quality."
                    
                    img_bytes = _generate_image_bytes(api_key, prompt, aspect)
                    outputs.append((f"v{i+1}_{_slug(data['project'])}.png", img_bytes))
                    
                    progress_bar.progress((i + 1) / data["num_imgs"])
                    
                    # Pausa de seguridad de 10s para proteger la cuota
                    if i < data["num_imgs"] - 1:
                        st.info(f"Imagen {i+1} completada. Pausa de 10s por seguridad...")
                        time.sleep(10) 
                        
                except Exception as e:
                    st.error(f"Fallo técnico: {e}")
                    break
        
        st.session_state.outputs = outputs

    if "outputs" in st.session_state and st.session_state.outputs:
        st.success("¡Pack generado con éxito!")
        zip_data = _zip_images(st.session_state.outputs)
        st.download_button(
            "⬇️ Descargar Pack (.zip)",
            data=zip_data,
            file_name=f"pack_{_slug(data['project'])}.zip",
            mime="application/zip",
            use_container_width=True
        )
