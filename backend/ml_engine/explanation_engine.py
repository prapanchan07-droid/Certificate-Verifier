"""
Turns the verification result (verdict, confidence, ML feature contributions,
official-record checks) into a short plain-English explanation using Gemini.

This is the XAI layer: instead of the frontend just showing "SUSPICIOUS 62%",
it shows a sentence like "The QR code and roll number matched the official
record, but the candidate's name did not, and the tamper score was elevated."

Falls back to a template-based (non-LLM) explanation if GEMINI_API_KEY is
missing or the API call fails, so this NEVER breaks the /api/verify endpoint.

Set the API key as an environment variable, never hardcode it:
    export GEMINI_API_KEY="your-key-here"

Model names in this space change often (Gemini 2.0 Flash was retired in
2026) — check https://ai.google.dev/gemini-api/docs/models for the current
recommended fast/cheap model and update GEMINI_MODEL below if needed.
"""

import os
import json
import requests

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)

_FIELD_LABELS = {
    "roll_no_match": "roll number",
    "reg_no_match": "register number",
    "candidate_name_match": "candidate name",
    "total_marks_match": "total marks",
    "institution_match": "institution name",
}


def _template_explanation(verdict: str, checks: dict, qr_authentic: bool,
                           tamper_score: float, top_factors: list) -> str:
    """Non-LLM fallback: builds a readable sentence from raw signals directly."""
    matched = [label for key, label in _FIELD_LABELS.items() if checks.get(key)]
    mismatched = [label for key, label in _FIELD_LABELS.items()
                  if key in checks and not checks.get(key)]

    parts = []
    if matched:
        parts.append(f"{', '.join(matched)} matched the official record")
    if mismatched:
        parts.append(f"{', '.join(mismatched)} did not match")
    if qr_authentic:
        parts.append("the QR code pointed to a valid government domain")
    else:
        parts.append("the QR code could not be verified against a government domain")
    if tamper_score > 0.5:
        parts.append("the image showed an elevated tamper score")

    body = "; ".join(parts) if parts else "insufficient signal was available to compare"
    return f"Result: {verdict}. {body.capitalize()}."


def explain_verdict(
    verdict: str,
    confidence: int,
    checks: dict,
    qr_authentic: bool,
    tamper_score: float,
    top_factors: list,
    ocr_results: dict,
) -> dict:
    """
    Returns {"explanation": str, "source": "gemini" | "template"}.
    Never raises — always returns something usable by the frontend.
    """
    fallback = _template_explanation(verdict, checks, qr_authentic, tamper_score, top_factors)

    if not GEMINI_API_KEY:
        return {"explanation": fallback, "source": "template"}

    factor_lines = "\n".join(
        f"- {f['feature']}: value={f['value']}, model_importance={f['importance']}"
        for f in top_factors
    )
    checks_lines = "\n".join(
        f"- {_FIELD_LABELS.get(k, k)}: {'matched' if v else 'did not match'}"
        for k, v in checks.items() if k in _FIELD_LABELS
    )

    prompt = f"""You are explaining an automated certificate-verification result to a
non-technical user. Use ONLY the facts given below — do not invent details,
names, or numbers that aren't listed. Write 2-3 plain sentences, no bullet
points, no markdown, professional and neutral tone. Do not use the word
"I" or refer to yourself.

Verdict: {verdict}
Confidence: {confidence}%
QR code from a valid government domain: {qr_authentic}
Tamper score (0=clean, 1=heavily altered): {round(tamper_score, 2)}

Field comparison against the official record:
{checks_lines or '(no official record was available to compare)'}

Top contributing factors from the model (higher importance = more influence
on the decision):
{factor_lines or '(not available)'}
"""

    try:
        resp = requests.post(
            f"{GEMINI_URL}?key={GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": 300,
                    "temperature": 0.3,
                    "thinkingConfig": {"thinkingBudget": 0},
                },
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        if text:
            return {"explanation": text, "source": "gemini"}
    except Exception as e:
        print("Gemini explanation failed, using template fallback:", e)

    return {"explanation": fallback, "source": "template"}