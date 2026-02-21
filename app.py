# app.py
import os
import json
import time
import re
from datetime import datetime
import streamlit as st

# Direct Google GenAI call (no LangChain / no Graph)
import google.generativeai as genai

APP_TITLE = "SPRING OS — Direction Engine™"
APP_SUBTITLE = "Donde la IA no improvisa, aquí se instala dirección."
MEM_DIR = "spring_memory"  # local folder (Streamlit Cloud will keep during runtime; may reset on redeploy)
os.makedirs(MEM_DIR, exist_ok=True)


# -----------------------------
# Utilities
# -----------------------------
def _slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9áéíóúñü\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    return text[:60] or "marca"


def _now_id() -> str:
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")


def _safe_json_loads(s: str):
    """
    Best-effort JSON extraction. Model sometimes wraps JSON with text.
    """
    s = s.strip()
    # Try direct
    try:
        return json.loads(s)
    except Exception:
        pass

    # Try find first {...} or [...]
    m = re.search(r"(\{.*\})", s, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass

    m = re.search(r"(\[.*\])", s, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass

    return None


def _hex_ok(v: str) -> bool:
    return bool(re.fullmatch(r"#([A-Fa-f0-9]{6})", (v or "").strip()))


def _clamp_words(s: str, max_words: int) -> str:
    words = (s or "").strip().split()
    return " ".join(words[:max_words])


def _validate_blueprint(bp: dict) -> list:
    """
    Returns list of issues. Empty list = OK.
    """
    issues = []

    if not isinstance(bp, dict):
        return ["Blueprint no es un objeto JSON."]

    required_top = [
        "project_name",
        "movement_of_month",
        "energy",
        "execution_capacity",
        "audience_level",
        "positioning",
        "core_message",
        "anti_goals",
        "pillars",
        "brand_voice",
        "visual_identity",
        "content_system",
        "spring_whispers",
        "coherence_score",
        "reality_check",
        "exports",
    ]
    for k in required_top:
        if k not in bp:
            issues.append(f"Falta el campo obligatorio: {k}")

    # Pillars
    pillars = bp.get("pillars")
    if not isinstance(pillars, list) or len(pillars) != 3:
        issues.append("pillars debe ser una lista de 3 elementos.")
    else:
        for i, p in enumerate(pillars, 1):
            if not isinstance(p, dict):
                issues.append(f"pillar {i} no es objeto.")
                continue
            for rk in ["name", "promise", "content_types", "proof_assets"]:
                if rk not in p:
                    issues.append(f"pillar {i} falta {rk}")

    # Brand voice
    voice = bp.get("brand_voice", {})
    if isinstance(voice, dict):
        for rk in ["tone", "do", "dont", "signature_phrases"]:
            if rk not in voice:
                issues.append(f"brand_voice falta {rk}")
    else:
        issues.append("brand_voice debe ser objeto.")

    # Visual identity
    vi = bp.get("visual_identity", {})
    if isinstance(vi, dict):
        pal = vi.get("palette", {})
        if not isinstance(pal, dict):
            issues.append("visual_identity.palette debe ser objeto.")
        else:
            for rk in ["primary", "secondary", "accent", "background", "text"]:
                v = pal.get(rk)
                if not _hex_ok(v):
                    issues.append(f"palette.{rk} debe ser HEX #RRGGBB (recibido: {v})")
        for rk in ["typography", "style_rules", "avoid_list"]:
            if rk not in vi:
                issues.append(f"visual_identity falta {rk}")
    else:
        issues.append("visual_identity debe ser objeto.")

    # Content system
    cs = bp.get("content_system", {})
    if not isinstance(cs, dict):
        issues.append("content_system debe ser objeto.")
    else:
        for rk in ["frequency_plan", "calendar_30_days", "starter_pack", "cta_bank", "metrics"]:
            if rk not in cs:
                issues.append(f"content_system falta {rk}")
        cal = cs.get("calendar_30_days")
        if not isinstance(cal, list) or len(cal) < 12:
            issues.append("calendar_30_days debe ser lista (ideal >= 12 entradas).")

    # Whispers
    whispers = bp.get("spring_whispers")
    if not isinstance(whispers, list) or len(whispers) < 4:
        issues.append("spring_whispers debe ser lista (mínimo 4).")
    else:
        for w in whispers:
            if not isinstance(w, str) or len(w.strip()) == 0:
                issues.append("spring_whispers contiene un elemento inválido.")
            if len((w or "")) > 220:
                issues.append("spring_whispers: un whisper es demasiado largo (máx ~220 caracteres).")

    # Score
    score = bp.get("coherence_score")
    try:
        score_int = int(score)
        if score_int < 0 or score_int > 100:
            issues.append("coherence_score debe estar entre 0 y 100.")
    except Exception:
        issues.append("coherence_score debe ser número entero 0-100.")

    # Reality check
    rc = bp.get("reality_check", {})
    if not isinstance(rc, dict):
        issues.append("reality_check debe ser objeto.")
    else:
        for rk in ["primary_risk", "contradictions", "one_adjustment"]:
            if rk not in rc:
                issues.append(f"reality_check falta {rk}")

    # Exports
    ex = bp.get("exports", {})
    if not isinstance(ex, dict):
        issues.append("exports debe ser objeto.")
    else:
        for rk in ["brand_kit_md", "calendar_csv", "copies_txt", "stories_txt", "blueprint_json"]:
            if rk not in ex:
                issues.append(f"exports falta {rk}")

    return issues


def _capacity_to_frequency_label(cap: str) -> str:
    # cap values: "Pantuflas (1-2 piezas)", "Ritmo (3 piezas)", "Modo ejecución (diario)"
    if "Pantuflas" in cap:
        return "2 por semana"
    if "Ritmo" in cap:
        return "3 por semana"
    return "Diario"


def _make_model(api_key: str, model_name: str):
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(model_name)


def _generate_text(model, prompt: str, temperature: float = 0.6, max_output_tokens: int = 4096):
    # Gemini SDK will accept generation_config dict
    resp = model.generate_content(
        prompt,
        generation_config={
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
        },
    )
    # Some SDK versions: resp.text may raise if blocked
    return getattr(resp, "text", "") or ""


def _format_calendar_csv(calendar_rows: list) -> str:
    # Expected rows: list of dict with keys: day, format, pillar, intent, title, hook, cta
    cols = ["día", "formato", "pilar", "intención", "título", "hook", "cta"]
    lines = [",".join(cols)]
    for r in calendar_rows:
        row = [
            str(r.get("day", "")),
            str(r.get("format", "")),
            str(r.get("pillar", "")),
            str(r.get("intent", "")),
            str(r.get("title", "")),
            str(r.get("hook", "")),
            str(r.get("cta", "")),
        ]
        # Basic CSV escaping
        row = ['"{}"'.format(x.replace('"', '""')) for x in row]
        lines.append(",".join(row))
    return "\n".join(lines)


def _save_memory(memory_key: str, data: dict):
    path = os.path.join(MEM_DIR, f"{memory_key}.json")
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


# -----------------------------
# Prompt Engine (SPRING OS)
# -----------------------------
def _build_blueprint_prompt(inputs: dict, previous_blueprint: dict | None):
    # Keep it tight, decisive, professional, close
    project_name = inputs["project_name"]
    movement = inputs["movement"]
    energy = inputs["energy"]
    capacity = inputs["capacity"]
    audience_level = inputs["audience_level"]
    sector = inputs["sector"]
    offer = inputs["offer"]
    target = inputs["target"]
    no_go = inputs["no_go"]
    constraints = inputs["constraints"]

    prev = ""
    if previous_blueprint:
        prev = (
            "\n\nCONTEXTO (memoria previa):\n"
            + json.dumps(previous_blueprint, ensure_ascii=False)
            + "\n\n"
            "Usa esta memoria para NO repetir diagnósticos básicos. Ajusta solo lo que cambie.\n"
        )

    freq = _capacity_to_frequency_label(capacity)

    schema = {
        "project_name": "string",
        "movement_of_month": "string",
        "energy": "string",
        "execution_capacity": "string",
        "audience_level": "string",
        "positioning": "string (1-2 frases, directo, sin humo)",
        "core_message": "string (mensaje central en 1 frase)",
        "anti_goals": ["string", "string", "string"],
        "pillars": [
            {
                "name": "string",
                "promise": "string",
                "content_types": ["string", "string", "string"],
                "proof_assets": ["string", "string"],
            }
        ],
        "brand_voice": {
            "tone": "string",
            "do": ["string", "string", "string"],
            "dont": ["string", "string", "string"],
            "signature_phrases": ["string", "string", "string"],
        },
        "visual_identity": {
            "palette": {
                "primary": "#RRGGBB",
                "secondary": "#RRGGBB",
                "accent": "#RRGGBB",
                "background": "#RRGGBB",
                "text": "#RRGGBB",
            },
            "typography": {
                "headlines": "string (nombre de familia tipográfica sugerida)",
                "body": "string (nombre de familia tipográfica sugerida)",
                "notes": "string (por qué calza con la marca, 1-2 frases)",
            },
            "style_rules": ["string", "string", "string", "string"],
            "avoid_list": ["string", "string", "string"],
        },
        "content_system": {
            "frequency_plan": "string (ej: 2 por semana / 3 por semana / diario + lógica)",
            "calendar_30_days": [
                {
                    "day": 1,
                    "format": "Reel|Carrusel|Story",
                    "pillar": "nombre del pilar",
                    "intent": "educar|probar|vender|conectar",
                    "title": "string",
                    "hook": "string (<= 12 palabras)",
                    "cta": "string (1 línea)",
                }
            ],
            "starter_pack": {
                "copies": [
                    {"type": "post", "text": "string (máx 70 palabras)", "cta": "string"}
                ],
                "stories": [
                    {
                        "sequence_title": "string",
                        "frames": ["string (<= 9 palabras)", "string", "string"],
                        "cta": "string",
                    }
                ],
            },
            "cta_bank": ["string", "string", "string", "string", "string"],
            "metrics": {
                "north_star": "string",
                "weekly_check": ["string", "string", "string"],
            },
        },
        "spring_whispers": [
            "string (máx 2 líneas, directo, estilo mentor invisible)",
            "string",
            "string",
            "string",
        ],
        "coherence_score": 0,
        "reality_check": {
            "primary_risk": "string",
            "contradictions": ["string", "string"],
            "one_adjustment": "string (una sola corrección que más impacta)",
        },
        "exports": {
            "brand_kit_md": "string (markdown corto, usable)",
            "calendar_csv": "string (CSV en texto)",
            "copies_txt": "string (texto)",
            "stories_txt": "string (texto)",
            "blueprint_json": "string (el JSON completo serializado)",
        },
    }

    prompt = f"""
Eres SPRING OS — Direction Engine™.
Actúas como estratega senior con mentalidad de producto (nivel big-tech) y sensibilidad humana.
Tu trabajo NO es motivar: es instalar dirección clara y ejecutable.
Tono: profesional, cercano, directo, sin frases vacías ni hype.
Idioma: español neutro.
Prohibido: promesas mágicas, exageraciones, "garantizado", "viral", "sin esfuerzo", "millones", "hazte rico".
Obligatorio: coherencia entre intención, energía, capacidad y outputs.

{prev}

BRIEF (entrada del usuario):
- Proyecto: {project_name}
- Rubro/sector: {sector}
- Oferta (qué vendes / qué servicio das): {offer}
- Target (quién compra y por qué): {target}
- Movimiento del mes (prioridad única): {movement}
- Energía dominante: {energy}
- Capacidad real: {capacity} (plan de frecuencia objetivo: {freq})
- Sofisticación del público: {audience_level}
- Lo que NO queremos (anti-marca): {no_go}
- Restricciones (tiempo, recursos, exposición, etc.): {constraints}

INSTRUCCIONES:
1) Genera un BLUEPRINT de marca+contenido (sistema) alineado al brief.
2) calendar_30_days debe ajustarse a la capacidad real. Si es "2 por semana", entrega ~8-10 entradas (no 30 reales).
   Si es "3 por semana", ~12-14 entradas. Si es diario, 25-30 entradas.
3) La paleta debe ser coherente con la energía. Entrega HEX válidos.
4) Incluye SPRING WHISPERS: tips como mentor invisible, máximo 2 líneas cada uno, accionables.
5) Calcula coherence_score (0-100) basado en consistencia, ejecutabilidad y claridad.
6) reality_check: señala el riesgo principal y 1 ajuste que más mejora todo.
7) exports:
   - brand_kit_md: guía corta (máx 250-350 palabras) con paleta, tipografías y reglas.
   - calendar_csv: CSV en texto con las filas del calendario.
   - copies_txt: lista breve de copies (del starter_pack + 2 extra).
   - stories_txt: guiones de stories (del starter_pack) en formato fácil de copiar.
   - blueprint_json: el JSON completo serializado.

FORMATO DE SALIDA:
Devuelve SOLAMENTE un JSON válido (sin markdown, sin comentarios, sin texto extra).
Respeta este esquema (orientativo) y llénalo con contenido real:
{json.dumps(schema, ensure_ascii=False)}
""".strip()

    return prompt


def _build_fix_prompt(original_prompt: str, model_output: str, issues: list):
    return f"""
Corrige el JSON para que sea válido y cumpla el esquema y restricciones.
Devuelve SOLAMENTE el JSON válido, sin texto extra.

Problemas detectados:
- {chr(10).join([f"* {i}" for i in issues])}

Salida anterior (posiblemente inválida):
{model_output}

Recuerda:
- HEX #RRGGBB
- 3 pilares exactos
- whispers cortos
- calendario ajustado a capacidad
""".strip()


# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title=APP_TITLE, page_icon="🧠", layout="wide")

with st.sidebar:
    st.title("🔐 Acceso SPRING")
    api_key = st.text_input("Ingresa tu Google API Key:", type="password")
    model_name = st.selectbox(
        "Modelo",
        options=[
            "gemini-1.5-flash",
            "gemini-1.5-pro",
        ],
        index=0,
    )
    st.caption("Este es el motor de instalación estratégica. Sin humo, con rima y razón.")

    st.divider()
    st.subheader("Memoria")
    memories = _list_memories()
    mem_labels = ["(sin memoria)"] + [f"{k}" for k, _ in memories]
    selected_mem_key = st.selectbox("Cargar blueprint guardado", mem_labels, index=0)
    loaded_memory = None
    if selected_mem_key != "(sin memoria)":
        for k, data in memories:
            if k == selected_mem_key:
                loaded_memory = data
                break
    if loaded_memory:
        st.success("Memoria cargada.")
        if st.button("Olvidar (solo en esta sesión)"):
            loaded_memory = None
            st.rerun()

st.markdown("🚀 *Al que madruga, Dios lo ayuda; pero el que tiene estrategia, no se queda en la duda.*")
st.title(APP_TITLE)
st.markdown(f"### {APP_SUBTITLE}")

colL, colR = st.columns([1.2, 1])

with colL:
    st.markdown("#### Instalación")
    project_name = st.text_input("Nombre del proyecto", value="SPRING")
    sector = st.text_input("Rubro / sector", value="Servicios profesionales")
    offer = st.text_area("Oferta (qué vendes)", value="Consultoría / servicio / producto digital", height=70)
    target = st.text_area("Target (quién compra y por qué)", value="Personas que quieren claridad y ejecución sin dispersión.", height=70)
    no_go = st.text_input("Anti-marca (lo que NO quieres transmitir)", value="Humo, promesas vacías, estética genérica, improvisación.")
    constraints = st.text_area("Restricciones reales (tiempo, exposición, recursos)", value="Poco tiempo. Quiero consistencia sin quemarme.", height=70)

    movement = st.selectbox(
        "Movimiento prioritario del mes",
        [
            "Venta directa (plata en mano)",
            "Instalación de autoridad",
            "Validación de propuesta",
            "Construcción de comunidad",
        ],
        index=0,
    )

    energy = st.selectbox(
        "Energía dominante",
        [
            "Precisión estratégica (bisturí en mano)",
            "Sofisticación (lujo silencioso)",
            "Cercanía clara (amable, no blanda)",
            "Ambición ejecutiva (sin hype)",
            "Minimalismo (menos pero mejor)",
        ],
        index=0,
    )

with colR:
    st.markdown("#### Calibración")
    cap = st.slider(
        "Capacidad real de ejecución",
        min_value=1,
        max_value=3,
        value=1,
        help="1 = Pantuflas (1-2 piezas) · 2 = Ritmo (3 piezas) · 3 = Modo ejecución (diario)",
    )
    if cap == 1:
        capacity = "Pantuflas (1-2 piezas)"
    elif cap == 2:
        capacity = "Ritmo (3 piezas)"
    else:
        capacity = "Modo ejecución (diario)"

    audience_level = st.radio("Sofisticación del público", ["Básico", "Intermedio", "Técnico"], index=0, horizontal=True)

    st.markdown("---")
    whisper_preview = st.empty()
    coherence_preview = st.empty()

install = st.button("🧠 INSTALAR DIRECCIÓN", type="primary", use_container_width=False)

if install:
    if not api_key:
        st.error("Falta la Google API Key.")
        st.stop()

    # Build input bundle
    inputs = {
        "project_name": project_name.strip(),
        "sector": sector.strip(),
        "offer": offer.strip(),
        "target": target.strip(),
        "no_go": no_go.strip(),
        "constraints": constraints.strip(),
        "movement": movement,
        "energy": energy,
        "capacity": capacity,
        "audience_level": audience_level,
    }

    # Model
    model = _make_model(api_key, model_name)

    # Phase 1: blueprint generation
    prompt = _build_blueprint_prompt(inputs, loaded_memory)

    with st.spinner("Instalando dirección…"):
        raw = _generate_text(model, prompt, temperature=0.55, max_output_tokens=4096)

    bp = _safe_json_loads(raw)
    issues = _validate_blueprint(bp) if bp is not None else ["No se pudo parsear JSON desde la respuesta del modelo."]

    # One repair attempt if issues exist
    if issues:
        fix_prompt = _build_fix_prompt(prompt, raw, issues)
        with st.spinner("Ajustando coherencia…"):
            raw2 = _generate_text(model, fix_prompt, temperature=0.35, max_output_tokens=4096)
        bp2 = _safe_json_loads(raw2)
        issues2 = _validate_blueprint(bp2) if bp2 is not None else ["No se pudo parsear JSON tras la corrección."]
        if not issues2:
            bp = bp2
            raw = raw2
            issues = []
        else:
            bp = bp2 if bp2 is not None else bp
            issues = issues2

    if issues:
        st.error("No pude generar un blueprint válido. Motivos:")
        for i in issues:
            st.write(f"- {i}")
        st.caption("Tip: prueba con otro modelo (gemini-1.5-pro) o simplifica inputs.")
        st.stop()

    # Build exports if model didn't
    calendar_csv = bp["exports"].get("calendar_csv", "")
    if not calendar_csv.strip():
        calendar_csv = _format_calendar_csv(bp.get("content_system", {}).get("calendar_30_days", []))
        bp["exports"]["calendar_csv"] = calendar_csv

    # Ensure blueprint_json export
    bp["exports"]["blueprint_json"] = json.dumps(bp, ensure_ascii=False, indent=2)

    # Session state
    st.session_state["spring_blueprint"] = bp
    st.session_state["spring_raw"] = raw

    # Quick preview
    whispers = bp.get("spring_whispers", [])
    if whispers:
        whisper_preview.info("👂 " + _clamp_words(whispers[0], 28))
    coherence_preview.success(f"Coherence Score: {bp.get('coherence_score')}%")

# Render result
bp = st.session_state.get("spring_blueprint")
if bp:
    st.divider()

    topL, topR = st.columns([1.3, 1])

    with topL:
        st.markdown("## Blueprint instalado")
        st.markdown(f"**Proyecto:** {bp.get('project_name')}")
        st.markdown(f"**Movimiento del mes:** {bp.get('movement_of_month')}")
        st.markdown(f"**Energía:** {bp.get('energy')}")
        st.markdown(f"**Capacidad:** {bp.get('execution_capacity')}")
        st.markdown(f"**Público:** {bp.get('audience_level')}")
        st.markdown("---")
        st.markdown("### Posicionamiento")
        st.write(bp.get("positioning"))
        st.markdown("### Mensaje central")
        st.write(bp.get("core_message"))

    with topR:
        st.markdown("## Reality Check™")
        rc = bp.get("reality_check", {})
        st.write(f"**Riesgo principal:** {rc.get('primary_risk')}")
        contrad = rc.get("contradictions", [])
        if contrad:
            st.write("**Contradicciones detectadas:**")
            for c in contrad:
                st.write(f"- {c}")
        st.write(f"**1 ajuste que más impacta:** {rc.get('one_adjustment')}")
        st.markdown("---")
        st.metric("Coherence Score", f"{bp.get('coherence_score')}%")

    st.markdown("## Pilares")
    pillars = bp.get("pillars", [])
    cols = st.columns(3)
    for idx, p in enumerate(pillars[:3]):
        with cols[idx]:
            st.markdown(f"**{p.get('name')}**")
            st.write(p.get("promise"))
            st.caption("Formatos:")
            for ct in (p.get("content_types") or [])[:4]:
                st.write(f"- {ct}")
            st.caption("Pruebas:")
            for pa in (p.get("proof_assets") or [])[:3]:
                st.write(f"- {pa}")

    st.markdown("## Identidad visual")
    vi = bp.get("visual_identity", {})
    pal = (vi.get("palette") or {})
    pal_cols = st.columns(5)
    pal_keys = [("primary", "Primario"), ("secondary", "Secundario"), ("accent", "Acento"), ("background", "Fondo"), ("text", "Texto")]
    for i, (k, label) in enumerate(pal_keys):
        with pal_cols[i]:
            st.caption(label)
            st.code(pal.get(k, ""), language="text")

    typo = vi.get("typography", {})
    st.markdown("**Tipografías sugeridas**")
    st.write(f"Títulos: {typo.get('headlines')}")
    st.write(f"Cuerpo: {typo.get('body')}")
    if typo.get("notes"):
        st.caption(typo.get("notes"))

    st.markdown("**Reglas de estilo**")
    for r in (vi.get("style_rules") or []):
        st.write(f"- {r}")

    st.markdown("**Evitar**")
    for r in (vi.get("avoid_list") or []):
        st.write(f"- {r}")

    st.markdown("## Sistema de contenido")
    cs = bp.get("content_system", {})
    st.write(f"**Frecuencia:** {cs.get('frequency_plan')}")

    st.markdown("### Calendario (propuesto)")
    cal = cs.get("calendar_30_days", [])
    if cal:
        st.dataframe(cal, use_container_width=True)
    else:
        st.info("No hay calendario disponible.")

    st.markdown("### Starter Pack")
    sp = cs.get("starter_pack", {})
    copies = (sp.get("copies") or [])
    stories = (sp.get("stories") or [])

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Copies**")
        for c in copies[:8]:
            st.write(f"- {c.get('text')}")
            if c.get("cta"):
                st.caption(f"CTA: {c.get('cta')}")

    with c2:
        st.markdown("**Stories (secuencias)**")
        for s in stories[:5]:
            st.write(f"- {s.get('sequence_title')}")
            frames = s.get("frames") or []
            for f in frames[:6]:
                st.caption(f"• {f}")
            if s.get("cta"):
                st.caption(f"CTA: {s.get('cta')}")

    st.markdown("## SPRING Whisper™")
    for w in (bp.get("spring_whispers") or [])[:8]:
        st.info(w)

    st.markdown("## Export")
    exports = bp.get("exports", {})

    export_cols = st.columns(5)
    # Files
    mem_key = f"{_slugify(bp.get('project_name','spring'))}_{_now_id()}"

    # Save memory
    save_col = st.columns([1, 2, 1])[1]
    with save_col:
        if st.button("Guardar blueprint en memoria", type="secondary"):
            _save_memory(mem_key, bp)
            st.success(f"Guardado como: {mem_key}")

    # Downloads
    export_items = [
        ("brand_kit.md", exports.get("brand_kit_md", "")),
        ("calendar.csv", exports.get("calendar_csv", "")),
        ("copies.txt", exports.get("copies_txt", "")),
        ("stories.txt", exports.get("stories_txt", "")),
        ("blueprint.json", exports.get("blueprint_json", "")),
    ]

    for i, (fn, content) in enumerate(export_items):
        with export_cols[i]:
            st.download_button(
                label=f"Descargar {fn}",
                data=content.encode("utf-8"),
                file_name=fn,
                mime="text/plain",
                use_container_width=True,
            )
