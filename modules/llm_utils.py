from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LLMParsed:
    raw_text: str
    code: str
    methods: str
    results: str
    discussion: str


def _extract_first_code_block(text: str) -> str:
    if "```" not in text:
        return ""
    # Prefer python blocks but accept plain fenced code.
    if "```python" in text:
        try:
            return text.split("```python", 1)[1].split("```", 1)[0].strip()
        except Exception:
            return ""
    try:
        return text.split("```", 1)[1].split("```", 1)[0].strip()
    except Exception:
        return ""


def _parse_tagged_sections(text: str) -> tuple[str, str, str]:
    def section(tag: str) -> str:
        key = f"[{tag}]"
        if key not in text:
            return ""
        try:
            after = text.split(key, 1)[1]
            # Next tag or end.
            nxt = after.find("[")
            return (after[:nxt] if nxt != -1 else after).strip()
        except Exception:
            return ""

    return section("METHODS"), section("RESULTS"), section("DISCUSSION")


def _try_parse_json_payload(text: str) -> Optional[dict]:
    """
    Accepts either raw JSON or JSON fenced in ```json.
    """
    t = text.strip()
    if "```json" in t:
        try:
            t = t.split("```json", 1)[1].split("```", 1)[0].strip()
        except Exception:
            return None
    if not (t.startswith("{") and t.endswith("}")):
        return None
    try:
        return json.loads(t)
    except Exception:
        return None


def parse_llm_response(text: str) -> LLMParsed:
    """
    Supports either:
    - JSON payload: {"methods": "...", "results": "...", "discussion": "...", "code": "..."}
    - Tagged payload: [METHODS] ... [RESULTS] ... [DISCUSSION] ... plus optional ```python code block
    """
    payload = _try_parse_json_payload(text)
    if isinstance(payload, dict):
        def norm(v) -> str:
            if v is None:
                return ""
            if isinstance(v, str):
                return v.strip()
            # Gemini sometimes returns nested objects; make them readable.
            try:
                return json.dumps(v, indent=2, ensure_ascii=False).strip()
            except Exception:
                return str(v).strip()

        code = norm(payload.get("code"))
        methods = norm(payload.get("methods"))
        results = norm(payload.get("results"))
        discussion = norm(payload.get("discussion"))
        return LLMParsed(raw_text=text, code=code, methods=methods, results=results, discussion=discussion)

    code = _extract_first_code_block(text)
    methods, results, discussion = _parse_tagged_sections(text)
    return LLMParsed(raw_text=text, code=code, methods=methods, results=results, discussion=discussion)


def build_system_prompt(df_columns: list[str]) -> str:
    cols = ", ".join(df_columns[:80])
    if len(df_columns) > 80:
        cols += ", ..."
    return (
        "You are Chatalyse, a Lead Bioinformatics Scientist. "
        "Experimental groups: VEH, NAM (calcilytic), TGF (tgfb), TGFNAM (TGF + calcilytic). "
        "You MUST respond as JSON with keys: methods, results, discussion, code. "
        "The 'code' field MUST be Python code only (no backticks). "
        "The code runs locally with access to: df (pandas DataFrame), st, pd, np, plt, sns, gp (gseapy). "
        "Write in a polished, publication-ready style. Use short sections, bullet points where helpful, and avoid raw JSON in results. "
        "If required columns are missing, do not guess silently—write code that inspects df and prints a clear error "
        "via st.error explaining what columns are needed.\n\n"
        "For GSEA with gseapy, use supported Enrichr library names such as: "
        "'KEGG_2021_Human', 'GO_Biological_Process_2023', 'Reactome_2022'. Do NOT use 'GO_BP_2023'. "
        "If many duplicated ranks occur, break ties by adding tiny random jitter.\n\n"
        f"DataFrame columns: {cols}"
    )


def pick_gemini_model(genai_module) -> str:
    """
    Pick the best available Gemini model that supports generateContent.
    We prefer Flash models first, then Pro.
    """
    preferred_substrings = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-2.5-pro",
        "gemini-2.0-pro",
        "gemini-1.5-pro",
        "gemini",
    ]

    models = list(genai_module.list_models())
    supported = []
    for mdl in models:
        name = getattr(mdl, "name", "") or ""
        methods = getattr(mdl, "supported_generation_methods", None) or []
        if "generateContent" in methods:
            supported.append(name)

    if not supported:
        raise RuntimeError("No Gemini models available that support generateContent. Check API key and API access.")

    # Rank by preferred substring order, then name length (shorter tends to be canonical)
    def score(n: str) -> tuple[int, int]:
        n_low = n.lower()
        for i, sub in enumerate(preferred_substrings):
            if sub in n_low:
                return (i, len(n))
        return (len(preferred_substrings), len(n))

    supported.sort(key=score)
    return supported[0]


def list_generate_content_models(genai_module) -> list[str]:
    """
    Return model names that support generateContent.
    """
    models = list(genai_module.list_models())
    supported = []
    for mdl in models:
        name = getattr(mdl, "name", "") or ""
        methods = getattr(mdl, "supported_generation_methods", None) or []
        if name and ("generateContent" in methods):
            supported.append(name)
    return sorted(set(supported))

