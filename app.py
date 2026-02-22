# app.py
import os
import json
import re
from datetime import datetime

import streamlit as st
import google.generativeai as genai

APP_TITLE = "SPRING OS — Direction Engine™"
APP_TAGLINE = "Un sistema simple para decidir qué hacer este mes."
MEM_DIR = "spring_memory"
os.makedirs(MEM_DIR, exist_ok=True)

MODEL_NAME = "gemini-2.5-flash"  # llamada directa (simple)


# -----------------------------
# Helpers
# -----------------------------
def _now_id():
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")


def _slugify(text):
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9áéíóúñü\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    return text[:60] or "spring"


def _safe_json_loads(s):
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


def _hex_ok(v):
    return bool(re.fullmatch(r"#([A-Fa-f0-9]{6})", (v or "").strip()))


def _save_memory(key, data):
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


def _frequency_label(x):
    return {1: "2/semana", 2: "3/semana", 3: "diario"}.get(int(x), "2/semana")


def _calendar_target_rows(freq):
    if freq == "2/semana":
        return 8
    if freq == "3/semana":
        return 12
    return 25


def _format_calendar_csv(rows):
    cols = ["día", "formato", "intención", "título", "cta"]
    out = [",".join(cols)]
    for r in rows or []:
        row = [
            str(r.get("day", "")),
            str(r.get("format", "")),
            str(r.get("intent", "")),
            str(r.get("title", "")),
            str(r.get("cta", "")),
        ]
        row = ['"{}"'.format(x.replace('"', '""')) for x in row]
        out.append(",".join(row))
    return "\n".join(out)


# -----------------------------
# Gemini direct call (simple)
# -----------------------------
def _generate(api_key, prompt, temperature=0.5, max_output_tokens=3072):
    genai.configure(api_key=api_key)

    # En algunos entornos puede requerir "models/gemini-2.5-flash"
    # Si te da NotFound, cambiá a: model = genai.GenerativeModel("models/gemini-2.5-flash")
    model = genai.GenerativeModel(MODEL_NAME)

    resp = model.generate_content(
        prompt,
        generation_config={
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
        },
    )
    return getattr(resp, "text", "") or ""


# -----------------------------
# Prompt (IMPORTANTE: esta es la función que te faltaba)
# -----------------------------
def _build_prompt(inputs, previous):
    project = inputs["project"]
    priority = inputs["priority"]
    frequency = inputs["frequency"]
    tone = inputs["tone"]
    mode = inputs["mode"]

    rows = _calendar_target_rows(frequency)

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
        "whisper": "string (máx 2 líneas, consejo accionable)",
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
Tu trabajo: instalar dirección clara y ejecutable (sin hype, sin tono autoritario).
Idioma: español neutro.
Prohibido: promesas mágicas, exageraciones, "viral", "sin esfuerzo", "garantizado".

{prev}

ENTRADA:
- Proyecto: {project}
- Prioridad del mes (una): {priority}
- Frecuencia real de posteo: {frequency}
- Tono de mensajes: {tone}
- Modo: {mode}

BRIEF PRO (si existe, úsalo; si no, no lo inventes):
- Rubro: {sector}
- Oferta: {offer}
- Target: {target}
- Anti-marca: {anti}
- Restricciones: {constraints}

REGLAS:
1) summary_60s primero: dirección en 60 segundos.
2) what_to_do_now: 5 próximos pasos, en orden, claros.
3) calendar: ~{rows} entradas (ajustado a {frequency}). No lo infles.
4) palette: HEX válido #RRGGBB.
5) whisper: máximo 2 líneas, mentor al oído (sin retar).
6) Devuelve SOLO JSON válido. Sin markdown. Sin texto extra.
7) exports.calendar_csv y exports.blueprint_json completos.

ESQUEMA:
{json.dumps(schema, ensure_ascii=False)}
""".strip()


def _build_fix_prompt(model_output, issues):
    return f"""
Arreglá el JSON para que sea válido y cumpla reglas. Devolvé SOLO JSON.

Problemas:
- {chr(10).join([f"* {i}" for i in issues])}

Salida anterior:
{model_output}

Recordá: HEX #RRGGBB, 3 pilares exactos, whisper corto, calendar ajustado, what_to_do_now (5 acciones).
""".strip()


def _validate(bp):
    issues = []
    if not isinstance(bp, dict):
        return ["No es JSON objeto."]

    required = [
        "project_name", "summary_60s", "what_to_do_now", "coherence_score", "whisper",
        "reality_check", "brand_quick_kit", "pillars", "weekly_plan", "calendar",
        "starter_pack", "exports"
    ]
    for k in required:
        if k not in bp:
            issues.append(f"Falta: {k}")

    wtdn = bp.get("what_to_do_now")
    if not isinstance(wtdn, list) or len(wtdn) != 5:
        issues.append("what_to_do_now debe tener 5 acciones exactas")

    if not isinstance(bp.get("pillars"), list) or len(bp["pillars"]) != 3:
        issues.append("pillars debe tener 3 elementos exactos")

    whisper = bp.get("whisper")
    if not isinstance(whisper, str) or len(whisper.strip()) == 0:
        issues.append("whisper vacío")
    if isinstance(whisper, str) and len(whisper) > 220:
        issues.append("whisper demasiado largo")

    try:
        s = int(bp.get("coherence_score"))
        if s < 0 or s > 100:
            issues.append("coherence_score fuera de 0-100")
    except Exception:
        issues.append("coherence_score no numérico")

    try:
        pal = bp["brand_quick_kit"]["visual"]["palette"]
        for rk in ["primary", "secondary", "accent", "background", "text"]:
            if not _hex_ok(pal.get(rk)):
                issues.append(f"palette.{rk} inválido (#RRGGBB)")
    except Exception:
        issues.append("brand_quick_kit.visual.palette incompleto")

    ex = bp.get("exports", {})
    if not isinstance(ex, dict) or "calendar_csv" not in ex or "blueprint_json" not in ex:
        issues.append("exports incompleto (calendar_csv, blueprint_json)")

    return issues


# -----------------------------
# UI
# -----------------------------
st.set_page_config(page_title=APP_TITLE, page_icon="🧠", layout="centered")

if "step" not in st.session_state:
    st.session_state["step"] = 1

with st.sidebar:
    st.markdown("### Acceso")
    api_key = st.text_input("Google API Key", type="password", placeholder="Pegá tu key acá")

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

# STEP 1
if st.session_state["step"] == 1:
    st.markdown("### Punto de partida")
    st.info("Definamos una prioridad (una sola). Con esto alcanza para darte un plan claro. Si querés, después afinamos.")

    mode = st.radio("Modo", ["Rápido", "Pro"], index=0, horizontal=True)
    st.session_state["mode"] = mode

    c1, c2 = st.columns(2)
    with c1:
        project = st.text_input("Proyecto", value="SPRING")
        priority = st.selectbox(
            "Prioridad del mes (una)",
            ["Venta", "Promo puntual", "Branding (marca)", "Comunidad (interacción y vínculo)"],
            index=0,
        )
    with c2:
        freq_int = st.slider("Frecuencia real de posteo", 1, 3, 1, help="1: 2/semana · 2: 3/semana · 3: diario")
        frequency = _frequency_label(freq_int)
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

    st.session_state["project"] = project.strip()
    st.session_state["priority"] = priority
    st.session_state["frequency"] = frequency
    st.session_state["tone"] = tone

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

    if st.button("Siguiente →", use_container_width=True):
        st.session_state["step"] = 2
        st.rerun()

# STEP 2
if st.session_state["step"] == 2:
    st.markdown("### Generaremos un plan")
    st.info("Un click y te devuelvo un plan ordenado, listo para usar.")

    st.write(f"**Proyecto:** {st.session_state['project']}")
    st.write(
        f"**Prioridad:** {st.session_state['priority']} · "
        f"**Frecuencia:** {st.session_state['frequency']} · "
        f"**Tono:** {st.session_state['tone']}"
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("← Volver", use_container_width=True):
            st.session_state["step"] = 1
            st.rerun()

    with c2:
        if st.button("Generar plan", type="primary", use_container_width=True):
            if not api_key:
                st.error("Te falta la API key.")
                st.stop()

            inputs = {
                "project": st.session_state["project"],
                "priority": st.session_state["priority"],
                "frequency": st.session_state["frequency"],
                "tone": st.session_state["tone"],
                "mode": st.session_state["mode"],
                "sector": st.session_state.get("sector", ""),
                "offer": st.session_state.get("offer", ""),
                "target": st.session_state.get("target", ""),
                "anti": st.session_state.get("anti", ""),
                "constraints": st.session_state.get("constraints", ""),
            }

            prompt = _build_prompt(inputs, loaded_memory)

            try:
                with st.spinner("Generando…"):
                    raw = _generate(api_key, prompt, temperature=0.5, max_output_tokens=3072)
            except Exception as e:
                st.error(f"Error al generar ({MODEL_NAME}): {type(e).__name__}: {e}")
                st.stop()

            bp = _safe_json_loads(raw)
            issues = _validate(bp) if bp is not None else ["No pude parsear JSON."]

            if issues:
                fix = _build_fix_prompt(raw, issues)
                try:
                    with st.spinner("Ajustando (1 pasada)…"):
                        raw2 = _generate(api_key, fix, temperature=0.3, max_output_tokens=3072)
                except Exception as e:
                    st.error(f"Error al corregir: {type(e).__name__}: {e}")
                    st.stop()

                bp2 = _safe_json_loads(raw2)
                issues2 = _validate(bp2) if bp2 is not None else ["No pude parsear JSON tras corrección."]

                if issues2:
                    st.error("Salida inválida:")
                    for i in issues2:
                        st.write(f"- {i}")
                    st.stop()

                bp = bp2

            bp.setdefault("exports", {})
            bp["exports"]["blueprint_json"] = json.dumps(bp, ensure_ascii=False, indent=2)

            if not (bp["exports"].get("calendar_csv") or "").strip():
                bp["exports"]["calendar_csv"] = _format_calendar_csv(bp.get("calendar", []))

            st.session_state["bp"] = bp
            st.session_state["step"] = 3
            st.rerun()

# STEP 3
if st.session_state["step"] == 3:
    bp = st.session_state.get("bp")
    if not bp:
        st.session_state["step"] = 1
        st.rerun()

    st.markdown("### Tu plan listo (sin enredos)")
    s = bp.get("summary_60s", {})
    st.success(s.get("direction", ""))
    st.caption(f"North Star: {s.get('north_star','')}")
    st.info(f"**Whisper:** {bp.get('whisper','')}")
    st.metric("Coherence Score", f"{bp.get('coherence_score')}%")

    st.markdown("#### Siguiente mejor paso (en orden)")
    for i, action in enumerate(bp.get("what_to_do_now", []), start=1):
        st.write(f"{i}. {action}")

    st.markdown("#### 5 piezas listas")
    posts = (bp.get("starter_pack", {}).get("5_posts") or [])[:5]
    for p in posts:
        st.write(f"**{p.get('title','')}**")
        st.write(p.get("copy", ""))
        st.caption(f"CTA: {p.get('cta', '')}")

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
        mem_key = f"{_slugify(bp.get('project_name', 'spring'))}_{_now_id()}"
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
            data=(bp["exports"].get("calendar_csv", "") or "").encode("utf-8"),
            file_name="calendar.csv",
            mime="text/csv",
            use_container_width=True,
        )
