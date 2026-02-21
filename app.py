# app.py
import os
import json
import re
from datetime import datetime
import streamlit as st
import google.generativeai as genai

APP_TITLE = "SPRING OS — Direction Engine™"
APP_TAGLINE = "Dirección primero. Output después."
MEM_DIR = "spring_memory"
os.makedirs(MEM_DIR, exist_ok=True)

# -----------------------------
# Helpers
# -----------------------------
def _now_id() -> str:
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")

def _slugify(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9áéíóúñü\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    return text[:60] or "spring"

def _safe_json_loads(s: str):
    s = (s or "").strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    m = re.search(r"(\{.*\})", s, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    return None

def _hex_ok(v: str) -> bool:
    return bool(re.fullmatch(r"#([A-Fa-f0-9]{6})", (v or "").strip()))

def _make_model(api_key: str, model_name: str):
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(model_name)

def _generate(model, prompt: str, temperature: float = 0.5, max_output_tokens: int = 3072) -> str:
    resp = model.generate_content(
        prompt,
        generation_config={"temperature": temperature, "max_output_tokens": max_output_tokens},
    )
    return getattr(resp, "text", "") or ""

def _save_memory(key: str, data: dict):
    path = os.path.join(MEM_DIR, f"{key}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path

def _list_memories():
    items = []
    for fn in sorted(os.listdir(MEM_DIR)):
        if fn.endswith(".json"):
            path = os.path.join(MEM_DIR, fn)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                items.append((fn[:-5], data))
            except Exception:
                continue
    return items

def _capacity_label(x: int) -> str:
    return {1: "2/semana", 2: "3/semana", 3: "diario"}.get(x, "2/semana")

def _calendar_target_rows(capacity: str) -> int:
    # approx number of entries to generate
    if capacity == "2/semana":
        return 8
    if capacity == "3/semana":
        return 12
    return 25

# -----------------------------
# Prompt (Spring voice: clara, directa, rioplatense elegante)
# -----------------------------
def _build_prompt(inputs: dict, previous: dict | None) -> str:
    # Inputs
    project = inputs["project"]
    movement = inputs["movement"]
    capacity = inputs["capacity"]
    audience = inputs["audience"]
    energy = inputs["energy"]
    mode = inputs["mode"]
    rows = _calendar_target_rows(capacity)

    # Optional pro brief
    sector = inputs.get("sector", "")
    offer = inputs.get("offer", "")
    target = inputs.get("target", "")
    anti = inputs.get("anti", "")
    constraints = inputs.get("constraints", "")

    prev = ""
    if previous:
        prev = (
            "MEMORIA (blueprint anterior):\n"
            + json.dumps(previous, ensure_ascii=False)
            + "\n\n"
            "Usa esto para NO repetir lo obvio. Ajusta con precisión.\n\n"
        )

    # Contract: keep outputs usable + not massive
    schema = {
        "project_name": "string",
        "summary_60s": {
            "north_star": "string (1 línea)",
            "direction": "string (máx 3 líneas)",
            "first_move": "string (qué hacer primero, 1 línea)",
            "stop_doing": "string (qué cortar este mes, 1 línea)"
        },
        "coherence_score": 0,
        "whisper": "string (máx 2 líneas, consejo filoso y accionable)",
        "reality_check": {
            "primary_risk": "string",
            "one_adjustment": "string (una sola corrección que más impacta)"
        },
        "brand_quick_kit": {
            "voice": {
                "tono": "string (2-3 adjetivos)",
                "regla_1": "string",
                "regla_2": "string",
                "prohibido": ["string", "string", "string"]
            },
            "visual": {
                "palette": {
                    "primary": "#RRGGBB",
                    "secondary": "#RRGGBB",
                    "accent": "#RRGGBB",
                    "background": "#RRGGBB",
                    "text": "#RRGGBB"
                },
                "typography": {"headlines": "string", "body": "string"},
                "3_rules": ["string", "string", "string"]
            }
        },
        "pillars": [
            {"name": "string", "promise": "string (1 línea)"},
            {"name": "string", "promise": "string (1 línea)"},
            {"name": "string", "promise": "string (1 línea)"}
        ],
        "weekly_plan": [
            {"week": 1, "focus": "string", "posts": ["string", "string", "string"]},
            {"week": 2, "focus": "string", "posts": ["string", "string", "string"]}
        ],
        "calendar": [
            {"day": 1, "format": "Reel|Carrusel|Story", "intent": "educar|probar|vender|conectar", "title": "string", "cta": "string"}
        ],
        "starter_pack": {
            "5_posts": [{"title": "string", "copy": "string (máx 60 palabras)", "cta": "string"}],
            "3_stories": [{"title": "string", "frames": ["string", "string", "string"], "cta": "string"}]
        },
        "exports": {
            "blueprint_json": "string",
            "calendar_csv": "string"
        }
    }

    return f"""
Eres SPRING OS — Direction Engine™.
Tu trabajo: instalar dirección clara y ejecutable (no motivar, no marear).
Estilo: directo, cálido con autoridad, cero humo. Rioplatense elegante.
No uses español neutro: escribe natural (vos), simple, profesional.
Prohibido: promesas mágicas, exageraciones, "viral", "sin esfuerzo", "garantizado".

{prev}

ENTRADA:
- Proyecto: {project}
- Movimiento del mes (prioridad única): {movement}
- Capacidad real: {capacity}
- Nivel del público: {audience}
- Energía: {energy}
- Modo: {mode}

BRIEF PRO (si existe, úsalo; si no, no lo inventes):
- Rubro: {sector}
- Oferta: {offer}
- Target: {target}
- Anti-marca: {anti}
- Restricciones: {constraints}

REGLAS:
1) Entrega primero "summary_60s": dirección en 60 segundos.
2) "calendar" debe tener aprox {rows} entradas (ajustado a {capacity}). No lo infles.
3) Paleta con HEX válidos #RRGGBB y coherente con la energía.
4) "whisper" máximo 2 líneas, accionable.
5) Calcula coherence_score 0-100 con criterio (claridad + ejecutabilidad).
6) Devuelve SOLO JSON válido. Sin markdown. Sin texto extra.
7) Completa exports.calendar_csv (CSV simple) y exports.blueprint_json (el JSON completo serializado).

ESQUEMA:
{json.dumps(schema, ensure_ascii=False)}
""".strip()

def _build_fix_prompt(model_output: str, issues: list) -> str:
    return f"""
Arregla el JSON para que sea válido y cumpla reglas. Devuelve SOLO JSON.

Problemas:
- {chr(10).join([f"* {i}" for i in issues])}

Salida anterior:
{model_output}

Recuerda: HEX #RRGGBB, 3 pillars exactos, whisper corto, calendar con tamaño ajustado.
""".strip()

def _validate(bp: dict) -> list:
    issues = []
    if not isinstance(bp, dict):
        return ["No es JSON objeto."]

    # minimal required
    for k in ["project_name", "summary_60s", "coherence_score", "whisper", "reality_check",
              "brand_quick_kit", "pillars", "weekly_plan", "calendar", "starter_pack", "exports"]:
        if k not in bp:
            issues.append(f"Falta: {k}")

    # palette hex
    try:
        pal = bp["brand_quick_kit"]["visual"]["palette"]
        for rk in ["primary", "secondary", "accent", "background", "text"]:
            if not _hex_ok(pal.get(rk)):
                issues.append(f"palette.{rk} inválido (usa #RRGGBB)")
    except Exception:
        issues.append("brand_quick_kit.visual.palette incompleto")

    # pillars length
    if not isinstance(bp.get("pillars"), list) or len(bp["pillars"]) != 3:
        issues.append("pillars debe tener 3 elementos exactos")

    # calendar sizing
    if not isinstance(bp.get("calendar"), list) or len(bp["calendar"]) < 6:
        issues.append("calendar demasiado corto (mínimo 6)")

    # whisper length
    if not isinstance(bp.get("whisper"), str) or len(bp["whisper"].strip()) == 0:
        issues.append("whisper vacío")
    if isinstance(bp.get("whisper"), str) and len(bp["whisper"]) > 220:
        issues.append("whisper demasiado largo")

    # score range
    try:
        s = int(bp.get("coherence_score"))
        if s < 0 or s > 100:
            issues.append("coherence_score fuera de rango 0-100")
    except Exception:
        issues.append("coherence_score no numérico")

    # exports
    ex = bp.get("exports", {})
    if not isinstance(ex, dict) or "calendar_csv" not in ex or "blueprint_json" not in ex:
        issues.append("exports incompleto (calendar_csv, blueprint_json)")

    return issues

# -----------------------------
# UI
# -----------------------------
st.set_page_config(page_title=APP_TITLE, page_icon="🧠", layout="centered")

# Sidebar: minimal
with st.sidebar:
    st.markdown("### Acceso")
    api_key = st.text_input("Google API Key", type="password", placeholder="Pegá tu key acá")
    model_name = st.selectbox("Modelo", ["gemini-1.5-flash", "gemini-1.5-pro"], index=0)

    with st.expander("Avanzado", expanded=False):
        st.caption("Memoria (opcional). Si no la usás, mejor.")
        memories = _list_memories()
        mem_labels = ["(sin memoria)"] + [k for k, _ in memories]
        selected_mem = st.selectbox("Cargar blueprint", mem_labels, index=0)
        loaded_memory = None
        if selected_mem != "(sin memoria)":
            for k, data in memories:
                if k == selected_mem:
                    loaded_memory = data
                    break
    # default if not set in expander
    if "loaded_memory" not in locals():
        loaded_memory = None

# Header minimal (no refranes)
st.title(APP_TITLE)
st.caption(APP_TAGLINE)

# Mode
mode = st.segmented_control(
    "Modo",
    options=["Rápido", "Pro"],
    default="Rápido",
    help="Rápido = 3 decisiones y listo. Pro = brief opcional."
)

st.markdown("#### Elegí tu configuración (1 minuto)")
c1, c2 = st.columns(2)

with c1:
    project = st.text_input("Proyecto", value="SPRING")
    movement = st.selectbox(
        "Prioridad del mes (una)",
        ["Venta", "Autoridad", "Validación", "Comunidad"],
        index=0
    )
    audience = st.radio("Nivel del público", ["Básico", "Intermedio", "Técnico"], index=0, horizontal=True)

with c2:
    cap_int = st.slider("Capacidad real", 1, 3, 1, help="1: 2/semana · 2: 3/semana · 3: diario")
    capacity = _capacity_label(cap_int)
    energy = st.selectbox(
        "Energía",
        ["Precisión", "Sofisticación", "Cercanía", "Ambición", "Minimal"],
        index=0
    )

# Pro brief (collapsed, optional)
sector = offer = target = anti = constraints = ""
if mode == "Pro":
    with st.expander("Brief Pro (opcional)", expanded=False):
        sector = st.text_input("Rubro", value="")
        offer = st.text_area("Oferta", value="", height=60)
        target = st.text_area("Target", value="", height=60)
        anti = st.text_input("Anti-marca", value="")
        constraints = st.text_area("Restricciones", value="", height=60)

# CTA
st.markdown("---")
install = st.button("INSTALAR DIRECCIÓN", type="primary", use_container_width=True)

if install:
    if not api_key:
        st.error("Te falta la API key.")
        st.stop()

    inputs = {
        "project": project.strip(),
        "movement": movement,
        "capacity": capacity,
        "audience": audience,
        "energy": energy,
        "mode": mode,
        "sector": sector.strip(),
        "offer": offer.strip(),
        "target": target.strip(),
        "anti": anti.strip(),
        "constraints": constraints.strip(),
    }

    model = _make_model(api_key, model_name)
    prompt = _build_prompt(inputs, loaded_memory)

    with st.spinner("Instalando dirección…"):
        raw = _generate(model, prompt, temperature=0.5, max_output_tokens=3072)

    bp = _safe_json_loads(raw)
    issues = _validate(bp) if bp is not None else ["No pude parsear JSON."]

    # one repair pass
    if issues:
        fix_prompt = _build_fix_prompt(raw, issues)
        with st.spinner("Ajustando (1 pasada)…"):
            raw2 = _generate(model, fix_prompt, temperature=0.3, max_output_tokens=3072)
        bp2 = _safe_json_loads(raw2)
        issues2 = _validate(bp2) if bp2 is not None else ["No pude parsear JSON tras corrección."]
        if not issues2:
            bp, raw, issues = bp2, raw2, []
        else:
            st.error("Salió inválido. Motivos:")
            for i in issues2:
                st.write(f"- {i}")
            st.stop()

    # ensure blueprint_json export
    bp["exports"]["blueprint_json"] = json.dumps(bp, ensure_ascii=False, indent=2)
    st.session_state["bp"] = bp

# -----------------------------
# Output (Resumen primero)
# -----------------------------
bp = st.session_state.get("bp")
if bp:
    st.markdown("## Dirección en 60 segundos")
    s = bp.get("summary_60s", {})
    st.success(s.get("direction", ""))
    a, b = st.columns(2)
    with a:
        st.write(f"**North Star:** {s.get('north_star','')}")
        st.write(f"**Primer paso:** {s.get('first_move','')}")
    with b:
        st.write(f"**Cortá esto:** {s.get('stop_doing','')}")
        st.metric("Coherence Score", f"{bp.get('coherence_score')}%")

    st.info(f"**Whisper:** {bp.get('whisper','')}")

    st.markdown("### Plan semanal (simple)")
    for w in (bp.get("weekly_plan") or [])[:4]:
        st.write(f"**Semana {w.get('week')} — {w.get('focus')}**")
        for p in (w.get("posts") or [])[:5]:
            st.write(f"- {p}")

    st.markdown("### 5 piezas listas")
    posts = (bp.get("starter_pack", {}).get("5_posts") or [])[:5]
    for p in posts:
        st.write(f"**{p.get('title','')}**")
        st.write(p.get("copy",""))
        st.caption(f"CTA: {p.get('cta','')}")

    with st.expander("Ver kit visual (paleta + reglas)", expanded=False):
        visual = (bp.get("brand_quick_kit", {}).get("visual") or {})
        pal = visual.get("palette", {})
        cols = st.columns(5)
        keys = [("primary","Primario"),("secondary","Secundario"),("accent","Acento"),("background","Fondo"),("text","Texto")]
        for i,(k,label) in enumerate(keys):
            with cols[i]:
                st.caption(label)
                st.code(pal.get(k,""), language="text")
        typo = visual.get("typography", {})
        st.write(f"**Tipografías:** {typo.get('headlines','')} / {typo.get('body','')}")
        st.write("**3 reglas visuales:**")
        for r in (visual.get("3_rules") or []):
            st.write(f"- {r}")

    with st.expander("Calendario (detalle)", expanded=False):
        st.dataframe(bp.get("calendar", []), use_container_width=True)

    with st.expander("Reality Check™", expanded=False):
        rc = bp.get("reality_check", {})
        st.write(f"**Riesgo principal:** {rc.get('primary_risk','')}")
        st.write(f"**Ajuste único:** {rc.get('one_adjustment','')}")

    with st.expander("Export", expanded=False):
        export_cols = st.columns(3)
        mem_key = f"{_slugify(bp.get('project_name','spring'))}_{_now_id()}"

        with export_cols[0]:
            st.download_button(
                "Descargar blueprint.json",
                data=bp["exports"]["blueprint_json"].encode("utf-8"),
                file_name="blueprint.json",
                mime="application/json",
                use_container_width=True,
            )
        with export_cols[1]:
            st.download_button(
                "Descargar calendar.csv",
                data=(bp["exports"].get("calendar_csv","") or "").encode("utf-8"),
                file_name="calendar.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with export_cols[2]:
            if st.button("Guardar en memoria", use_container_width=True):
                _save_memory(mem_key, bp)
                st.success(f"Guardado: {mem_key}")
