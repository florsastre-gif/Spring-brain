# app.py
import os
import json
import re
from datetime import datetime
import streamlit as st
import google.generativeai as genai

APP_TITLE = "SPRING OS — Direction Engine™"
APP_TAGLINE = "Elegí. Instalá. Ejecutá."
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
    if capacity == "2/semana":
        return 8
    if capacity == "3/semana":
        return 12
    return 25

# -----------------------------
# Prompt
# -----------------------------
def _build_prompt(inputs: dict, previous: dict | None) -> str:
    project = inputs["project"]
    movement = inputs["movement"]
    capacity = inputs["capacity"]
    audience = inputs["audience"]
    energy = inputs["energy"]
    mode = inputs["mode"]
    rows = _calendar_target_rows(capacity)

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

    schema = {
        "project_name": "string",
        "summary_60s": {
            "north_star": "string (1 línea)",
            "direction": "string (máx 3 líneas)",
            "first_move": "string (1 línea)",
            "stop_doing": "string (1 línea)"
        },
        "what_to_do_now": [
            "string (acción #1)",
            "string (acción #2)",
            "string (acción #3)",
            "string (acción #4)",
            "string (acción #5)"
        ],
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
        "exports": {"blueprint_json": "string", "calendar_csv": "string"}
    }

    return f"""
Eres SPRING OS — Direction Engine™.
Tu trabajo: instalar dirección clara y ejecutable (no motivar, no marear).
Escribí como Flor: directo, cálido con autoridad, rioplatense elegante.
Prohibido: promesas mágicas, exageraciones, "viral", "sin esfuerzo", "garantizado".

{prev}

ENTRADA:
- Proyecto: {project}
- Prioridad del mes: {movement}
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
1) "summary_60s" primero: dirección en 60 segundos.
2) "what_to_do_now": 5 acciones concretas, en orden, para que el usuario no se pierda.
3) "calendar" ~ {rows} entradas (ajustado a {capacity}). No lo infles.
4) Paleta HEX válida #RRGGBB.
5) "whisper" máximo 2 líneas.
6) Devuelve SOLO JSON válido. Sin markdown. Sin texto extra.
7) exports.calendar_csv y exports.blueprint_json completos.

ESQUEMA:
{json.dumps(schema, ensure_ascii=False)}
""".strip()

def _build_fix_prompt(model_output: str, issues: list) -> str:
    return f"""
Arreglá el JSON para que sea válido y cumpla reglas. Devolvé SOLO JSON.

Problemas:
- {chr(10).join([f"* {i}" for i in issues])}

Salida anterior:
{model_output}

Recordá: HEX #RRGGBB, 3 pilares exactos, whisper corto, calendar ajustado, what_to_do_now (5 acciones).
""".strip()

def _validate(bp: dict) -> list:
    issues = []
    if not isinstance(bp, dict):
        return ["No es JSON objeto."]

    required = ["project_name","summary_60s","what_to_do_now","coherence_score","whisper","reality_check",
                "brand_quick_kit","pillars","weekly_plan","calendar","starter_pack","exports"]
    for k in required:
        if k not in bp:
            issues.append(f"Falta: {k}")

    wtdn = bp.get("what_to_do_now")
    if not isinstance(wtdn, list) or len(wtdn) != 5:
        issues.append("what_to_do_now debe tener 5 acciones exactas")

    try:
        pal = bp["brand_quick_kit"]["visual"]["palette"]
        for rk in ["primary","secondary","accent","background","text"]:
            if not _hex_ok(pal.get(rk)):
                issues.append(f"palette.{rk} inválido (#RRGGBB)")
    except Exception:
        issues.append("brand_quick_kit.visual.palette incompleto")

    if not isinstance(bp.get("pillars"), list) or len(bp["pillars"]) != 3:
        issues.append("pillars debe tener 3 elementos exactos")

    if not isinstance(bp.get("whisper"), str) or len(bp["whisper"].strip()) == 0:
        issues.append("whisper vacío")
    if isinstance(bp.get("whisper"), str) and len(bp["whisper"]) > 220:
        issues.append("whisper demasiado largo")

    try:
        s = int(bp.get("coherence_score"))
        if s < 0 or s > 100:
            issues.append("coherence_score fuera de 0-100")
    except Exception:
        issues.append("coherence_score no numérico")

    ex = bp.get("exports", {})
    if not isinstance(ex, dict) or "calendar_csv" not in ex or "blueprint_json" not in ex:
        issues.append("exports incompleto (calendar_csv, blueprint_json)")

    return issues

# -----------------------------
# UI (Brújula)
# -----------------------------
st.set_page_config(page_title=APP_TITLE, page_icon="🧠", layout="centered")

if "step" not in st.session_state:
    st.session_state["step"] = 1

# Sidebar minimal
with st.sidebar:
    st.markdown("### Acceso")
    api_key = st.text_input("Google API Key", type="password", placeholder="Pegá tu key acá")
    model_name = st.selectbox("Modelo", ["gemini-1.5-flash", "gemini-1.5-pro"], index=0)

    loaded_memory = None
    with st.expander("Avanzado", expanded=False):
        memories = _list_memories()
        mem_labels = ["(sin memoria)"] + [k for k, _ in memories]
        selected_mem = st.selectbox("Memoria", mem_labels, index=0)
        if selected_mem != "(sin memoria)":
            for k, data in memories:
                if k == selected_mem:
                    loaded_memory = data
                    break

st.title(APP_TITLE)
st.caption(APP_TAGLINE)

steps = {1: "1) Elegí", 2: "2) Instalá", 3: "3) Ejecutá"}
st.markdown(f"**Paso actual:** {steps.get(st.session_state['step'])}")

# STEP 1
if st.session_state["step"] == 1:
    st.markdown("### Arrancá por acá")
    st.info("Elegí una prioridad. Calibrá capacidad. Listo. No te pido más para darte dirección.")

    # ✅ reemplazo de segmented_control por radio (compatible)
    mode = st.radio("Modo", ["Rápido", "Pro"], index=0, horizontal=True)
    st.session_state["mode"] = mode

    c1, c2 = st.columns(2)
    with c1:
        project = st.text_input("Proyecto", value="SPRING")
        movement = st.selectbox("Prioridad del mes (una)", ["Venta", "Autoridad", "Validación", "Comunidad"], index=0)
        audience = st.radio("Nivel del público", ["Básico","Intermedio","Técnico"], index=0, horizontal=True)
    with c2:
        cap_int = st.slider("Capacidad real", 1, 3, 1, help="1: 2/semana · 2: 3/semana · 3: diario")
        capacity = _capacity_label(cap_int)
        energy = st.selectbox("Energía", ["Precisión","Sofisticación","Cercanía","Ambición","Minimal"], index=0)

    st.session_state["project"] = project.strip()
    st.session_state["movement"] = movement
    st.session_state["audience"] = audience
    st.session_state["capacity"] = capacity
    st.session_state["energy"] = energy

    if mode == "Pro":
        with st.expander("Brief Pro (opcional)", expanded=False):
            st.session_state["sector"] = st.text_input("Rubro", value="")
            st.session_state["offer"] = st.text_area("Oferta (1 línea)", value="", height=55)
            st.session_state["target"] = st.text_area("Target (1 línea)", value="", height=55)
            st.session_state["anti"] = st.text_input("Anti-marca", value="")
            st.session_state["constraints"] = st.text_area("Restricciones", value="", height=55)
    else:
        st.session_state["sector"] = ""
        st.session_state["offer"] = ""
        st.session_state["target"] = ""
        st.session_state["anti"] = ""
        st.session_state["constraints"] = ""

    colA, colB = st.columns(2)
    with colA:
        if st.button("Siguiente →", use_container_width=True):
            st.session_state["step"] = 2
            st.rerun()
    with colB:
        st.caption("Tip: si dudás, poné capacidad baja. Cumplir > fantasear.")

# STEP 2
if st.session_state["step"] == 2:
    st.markdown("### Instalación")
    st.info("Un click. Te devuelvo orden.")

    st.write(f"**Proyecto:** {st.session_state['project']}")
    st.write(f"**Prioridad:** {st.session_state['movement']} · **Capacidad:** {st.session_state['capacity']} · **Público:** {st.session_state['audience']}")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("← Volver", use_container_width=True):
            st.session_state["step"] = 1
            st.rerun()
    with c2:
        if st.button("INSTALAR DIRECCIÓN", type="primary", use_container_width=True):
            if not api_key:
                st.error("Te falta la API key.")
                st.stop()

            inputs = {
                "project": st.session_state["project"],
                "movement": st.session_state["movement"],
                "capacity": st.session_state["capacity"],
                "audience": st.session_state["audience"],
                "energy": st.session_state["energy"],
                "mode": st.session_state["mode"],
                "sector": st.session_state["sector"],
                "offer": st.session_state["offer"],
                "target": st.session_state["target"],
                "anti": st.session_state["anti"],
                "constraints": st.session_state["constraints"],
            }

            model = _make_model(api_key, model_name)
            prompt = _build_prompt(inputs, loaded_memory)

            with st.spinner("Instalando dirección…"):
                raw = _generate(model, prompt, temperature=0.5, max_output_tokens=3072)

            bp = _safe_json_loads(raw)
            issues = _validate(bp) if bp is not None else ["No pude parsear JSON."]

            if issues:
                fix = _build_fix_prompt(raw, issues)
                with st.spinner("Ajustando (1 pasada)…"):
                    raw2 = _generate(model, fix, temperature=0.3, max_output_tokens=3072)
                bp2 = _safe_json_loads(raw2)
                issues2 = _validate(bp2) if bp2 is not None else ["No pude parsear JSON tras corrección."]
                if issues2:
                    st.error("Salida inválida:")
                    for i in issues2:
                        st.write(f"- {i}")
                    st.stop()
                bp = bp2

            bp["exports"]["blueprint_json"] = json.dumps(bp, ensure_ascii=False, indent=2)
            st.session_state["bp"] = bp
            st.session_state["step"] = 3
            st.rerun()

# STEP 3
if st.session_state["step"] == 3:
    bp = st.session_state.get("bp")
    if not bp:
        st.session_state["step"] = 1
        st.rerun()

    st.markdown("### Ejecutá (sin perderte)")
    s = bp.get("summary_60s", {})
    st.success(s.get("direction", ""))
    st.caption(f"North Star: {s.get('north_star','')}")
    st.info(f"**Whisper:** {bp.get('whisper','')}")
    st.metric("Coherence Score", f"{bp.get('coherence_score')}%")

    st.markdown("#### Tu brújula (en orden)")
    for i, action in enumerate(bp.get("what_to_do_now", []), start=1):
        st.write(f"{i}. {action}")

    st.markdown("#### 5 piezas listas")
    posts = (bp.get("starter_pack", {}).get("5_posts") or [])[:5]
    for p in posts:
        st.write(f"**{p.get('title','')}**")
        st.write(p.get("copy",""))
        st.caption(f"CTA: {p.get('cta','')}")

    with st.expander("Calendario (detalle)", expanded=False):
        st.dataframe(bp.get("calendar", []), use_container_width=True)

    st.markdown("---")
    a, b, c = st.columns(3)
    with a:
        if st.button("← Ajustar decisiones", use_container_width=True):
            st.session_state["step"] = 1
            st.rerun()
    with b:
        if st.button("Regenerar", use_container_width=True):
            st.session_state["step"] = 2
            st.rerun()
    with c:
        mem_key = f"{_slugify(bp.get('project_name','spring'))}_{_now_id()}"
        if st.button("Guardar memoria", use_container_width=True):
            _save_memory(mem_key, bp)
            st.success(f"Guardado: {mem_key}")

    with st.expander("Export", expanded=False):
        st.download_button(
            "Descargar blueprint.json",
            data=bp["exports"]["blueprint_json"].encode("utf-8"),
            file_name="blueprint.json",
            mime="application/json",
            use_container_width=True,
        )
        st.download_button(
            "Descargar calendar.csv",
            data=(bp["exports"].get("calendar_csv","") or "").encode("utf-8"),
            file_name="calendar.csv",
            mime="text/csv",
            use_container_width=True,
        )
