import streamlit as st, pandas as pd, google.generativeai as genai, os, json, datetime, traceback, matplotlib.pyplot as plt
import numpy as np

try:
    import seaborn as sns
except Exception:
    sns = None

try:
    import gseapy as gp
except Exception:
    gp = None
import interface as ui # Import your UI file
from modules.data_utils import profile_dataframe, read_table
from modules.exec_utils import run_user_code
from modules.llm_utils import build_system_prompt, parse_llm_response, pick_gemini_model, list_generate_content_models
from modules.viz_defaults import apply_publication_style

# --- CONFIG ---
st.set_page_config(page_title="Chatalyse Agent", layout="wide")
D = "projects"
if not os.path.exists(D): os.makedirs(D)
df_schema = {"history":[], "vars":{}, "inv_title":"Untitled Project", "m_c":"", "r_c":"", "d_c":"", "v_h":[]}
for k, v in df_schema.items():
    if k not in st.session_state: st.session_state[k] = v

# --- UTILS ---
def save():
    n = st.session_state.inv_title.strip().replace(' ','_') or "Untitled"
    data = {k: st.session_state[k] for k in ["history", "inv_title", "m_c", "r_c", "d_c", "v_h"]}
    with open(os.path.join(D, f"{n}.json"), "w") as f: json.dump(data, f)

def snap():
    s = {"ts": datetime.datetime.now().strftime("%d %b, %H:%M"), 
         "db": {k: st.session_state[k] for k in ["history", "inv_title", "m_c", "r_c", "d_c"]}}
    st.session_state.v_h.append(s)


def undo():
    if not st.session_state.v_h:
        return
    last = st.session_state.v_h.pop()
    for k, val in last["db"].items():
        st.session_state[k] = val
    save()

# --- RUN UI ---
ui.init_ui_styles()
ui.render_sidebar(D, df_schema, save, undo, snap)

# --- ENGINE ---
try:
    with open("api_key.txt", "r") as f: genai.configure(api_key=f.read().strip())
    # Model names change often; auto-pick a supported one.
    if "gemini_model_name" not in st.session_state.vars:
        st.session_state.vars["gemini_model_name"] = pick_gemini_model(genai)
    m = genai.GenerativeModel(st.session_state.vars["gemini_model_name"])
except Exception as e: st.error(f"API Error: {e}")

apply_publication_style()
if sns is not None:
    try:
        sns.set_theme(style="whitegrid", context="talk", palette="deep")
    except Exception:
        pass

with st.sidebar:
    with st.expander("🤖 Gemini status", expanded=False):
        st.caption(f"Selected model: `{st.session_state.vars.get('gemini_model_name', 'unknown')}`")
        if st.button("Refresh available models", use_container_width=True):
            try:
                st.session_state.vars["gemini_models_generate_content"] = list_generate_content_models(genai)
                st.session_state.vars["gemini_model_name"] = pick_gemini_model(genai)
                save()
                st.rerun()
            except Exception as e:
                st.error(f"Model refresh failed: {e}")

        try:
            if "gemini_models_generate_content" not in st.session_state.vars:
                st.session_state.vars["gemini_models_generate_content"] = list_generate_content_models(genai)
            models = st.session_state.vars.get("gemini_models_generate_content", [])
            if models:
                st.caption("Models supporting `generateContent`:")
                st.code("\n".join(models))
        except Exception as e:
            st.caption(f"Could not list models: {e}")

f_up = st.file_uploader("Data", type=['csv', 'xlsx'], label_visibility="collapsed")
if f_up:
    try:
        st.session_state.vars['df'] = read_table(f_up)
    except Exception as e: st.error(f"File Error: {e}")

df_loaded = st.session_state.vars.get("df")
if isinstance(df_loaded, pd.DataFrame) and not df_loaded.empty:
    prof = profile_dataframe(df_loaded)
    with st.expander("📄 Data preview", expanded=False):
        st.caption(f"Rows: {prof.n_rows:,} | Columns: {prof.n_cols:,}")
        if prof.gene_col_guess:
            st.caption(f"Gene column guess: `{prof.gene_col_guess}`")
        st.dataframe(df_loaded.head(50), use_container_width=True)

t_in = st.text_input("T", value=st.session_state.inv_title, label_visibility="collapsed")
if t_in != st.session_state.inv_title:
    st.session_state.inv_title = t_in; save(); st.rerun()

# --- BRAINSTORMING & SECTIONS ---
with st.container(border=True):
    st.markdown('<div class="header-style">Chat</div>', unsafe_allow_html=True)
    with st.container(height=450, border=False):
        for msg in st.session_state.history:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])
                if "code" in msg:
                    with st.expander("Technical Log"): st.code(msg["code"])

    with st.form(key="chat_final", clear_on_submit=True):
        u_in = st.text_area(
            "In",
            placeholder="What would you like to analyse today?",
            height=100,
            label_visibility="collapsed",
        )
        if st.form_submit_button("Run Analysis"):
            # Show the user message immediately, then process on next rerun.
            st.session_state.history.append({"role": "user", "content": u_in})
            st.session_state.vars["pending_user_input"] = u_in
            st.session_state.vars["pending_run"] = True
            snap()
            save()
            st.rerun()


# Process pending run outside the form so the user's message renders immediately.
if st.session_state.vars.get("pending_run"):
    u_in = st.session_state.vars.get("pending_user_input", "")
    st.session_state.vars["pending_run"] = False
    st.session_state.vars["pending_user_input"] = ""
    save()

    df_snap = st.session_state.vars.get("df", pd.DataFrame())
    sys_context = build_system_prompt([str(c) for c in df_snap.columns.tolist()])

    try:
        with st.spinner("Processing..."):
            res_text = m.generate_content(sys_context + "\n\nUSER:\n" + u_in).text
            parsed = parse_llm_response(res_text)
            code = parsed.code

            if code.strip():
                if gp is None and ("gseapy" in code or "gp." in code):
                    raise ModuleNotFoundError(
                        "gseapy is not installed/available. Add it to requirements.txt (gseapy) and reinstall the venv."
                    )
                if sns is None and ("seaborn" in code or "sns." in code):
                    raise ModuleNotFoundError(
                        "seaborn is not installed/available. Add it to requirements.txt (seaborn) and reinstall the venv."
                    )
                exec_locals = {"df": df_snap, "st": st, "plt": plt, "pd": pd, "np": np, "sns": sns, "gp": gp}
                exec_result = run_user_code(code, globals_dict=globals(), locals_dict=exec_locals)
                if not exec_result.ok:
                    combined = "\n".join(
                        s
                        for s in [
                            exec_result.stdout.strip() and ("STDOUT:\n" + exec_result.stdout.strip()),
                            exec_result.stderr.strip() and ("STDERR:\n" + exec_result.stderr.strip()),
                            "TRACEBACK:\n" + exec_result.traceback,
                        ]
                        if s
                    )
                    st.session_state.history.append(
                        {
                            "role": "assistant",
                            "content": "Execution error while running the analysis code. Open 'Technical Log' for details.",
                            "code": combined,
                        }
                    )
                    save()
                    st.rerun()

                if exec_result.stdout.strip() or exec_result.stderr.strip():
                    combined = "\n".join(
                        s
                        for s in [
                            exec_result.stdout.strip() and ("STDOUT:\n" + exec_result.stdout.strip()),
                            exec_result.stderr.strip() and ("STDERR:\n" + exec_result.stderr.strip()),
                        ]
                        if s
                    )
                    st.session_state.history.append(
                        {
                            "role": "assistant",
                            "content": "Run log (from executed code). Open 'Technical Log' to view.",
                            "code": combined,
                        }
                    )
                    save()

            if parsed.methods:
                st.session_state.m_c += "\n" + parsed.methods
            if parsed.results:
                st.session_state.r_c += "\n" + parsed.results
            if parsed.discussion:
                st.session_state.d_c += "\n" + parsed.discussion

            # Show a polished chat reply (prefer narrative sections over dumping raw JSON)
            reply_parts = [p for p in [parsed.results, parsed.discussion] if p.strip()]
            reply = "\n\n".join(reply_parts) if reply_parts else parsed.raw_text
            st.session_state.history.append({"role": "assistant", "content": reply, "code": code})
            save()
    except Exception:
        tb = traceback.format_exc()
        st.session_state.history.append(
            {"role": "assistant", "content": "Error while processing your request. Open 'Technical Log' for details.", "code": tb}
        )
        save()
        st.rerun()

# Scientific Output Text Areas
with st.expander("🧪 Methods", expanded=True):
    st.session_state.m_c = st.text_area("MC", value=st.session_state.m_c, height=200, label_visibility="collapsed", on_change=save)
with st.expander("📈 Results", expanded=True):
    st.session_state.r_c = st.text_area("RC", value=st.session_state.r_c, height=200, label_visibility="collapsed", on_change=save)
with st.expander("📝 Discussion", expanded=True):
    st.session_state.d_c = st.text_area("DC", value=st.session_state.d_c, height=200, label_visibility="collapsed", on_change=save)