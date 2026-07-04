import io
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors


_VERDICT_COLORS = {
    "GENUINE": colors.HexColor("#2F6B4F"),
    "SUSPICIOUS": colors.HexColor("#A87C2A"),
    "FAKE": colors.HexColor("#8C3A2E"),
    "UNVERIFIED": colors.HexColor("#6B6354"),
    "ERROR": colors.HexColor("#6B6354"),
}

_VERDICT_CAVEATS = {
    "GENUINE": None,
    "SUSPICIOUS": (
        "⚠ Some details extracted from this document did not match the "
        "official record. This result should be treated with caution and "
        "verified directly with the issuing board."
    ),
    "FAKE": (
        "✗ This document did not match the official record. Do not rely on "
        "it as proof of qualification. Report suspected forgeries to the "
        "appropriate authority."
    ),
    "UNVERIFIED": (
        "ℹ The official board record could not be reached during this check "
        "(network error or QR code absent). The result does not confirm or "
        "deny the document's authenticity. Verify directly with the board."
    ),
    "ERROR": (
        "ℹ An error occurred while processing this file. No conclusion about "
        "authenticity can be drawn."
    ),
}


def generate_pdf_report(data: dict) -> io.BytesIO:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
    )
    styles = getSampleStyleSheet()
    story = []

    verdict = data.get("final_decision", "ERROR")
    verdict_color = _VERDICT_COLORS.get(verdict, colors.gray)

    # --- Title ---
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        textColor=colors.HexColor("#1E2A44"),
        fontSize=20,
        spaceAfter=4,
    )
    story.append(Paragraph("CertifyX — Certificate Verification Report", title_style))
    story.append(Paragraph(
        f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        styles["Normal"],
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#DCD2B8"),
                            spaceAfter=12))

    # --- Verdict ---
    verdict_style = ParagraphStyle(
        "Verdict",
        parent=styles["Heading1"],
        textColor=verdict_color,
        fontSize=18,
        spaceAfter=4,
    )
    story.append(Paragraph(f"Result: {verdict}", verdict_style))
    story.append(Paragraph(
        f"<b>Confidence:</b> {data.get('confidence_score', 0)}%",
        styles["Normal"],
    ))

    caveat = _VERDICT_CAVEATS.get(verdict)
    if caveat:
        caveat_style = ParagraphStyle(
            "Caveat",
            parent=styles["Normal"],
            textColor=verdict_color,
            leftIndent=12,
            spaceBefore=6,
        )
        story.append(Paragraph(caveat, caveat_style))

    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=0.5,
                            color=colors.HexColor("#DCD2B8"), spaceAfter=10))

    # --- OCR Metadata ---
    story.append(Paragraph("<b>Extracted Details (OCR)</b>", styles["Heading2"]))
    meta = data.get("extracted_metadata", {})
    for label, key in [
        ("Candidate name", "candidate_name"),
        ("Roll number", "roll_no"),
        ("Register number", "reg_no"),
        ("Total marks", "total_marks"),
        ("Institution", "institution"),
    ]:
        val = meta.get(key) or "—"
        story.append(Paragraph(f"{label}: <b>{val}</b>", styles["Normal"]))
    story.append(Spacer(1, 10))

    # --- Official verification ---
    story.append(Paragraph("<b>Official Record Check</b>", styles["Heading2"]))
    ov = data.get("official_verification", {})
    ov_status = ov.get("status", "NOT_CHECKED")
    story.append(Paragraph(f"Status: <b>{ov_status}</b>", styles["Normal"]))
    if ov_status == "MATCHED":
        story.append(Paragraph(f"Score: <b>{ov.get('score', 0)}/100</b>", styles["Normal"]))
        checks = ov.get("checks", {})
        labels = {
            "roll_no_match": "Roll number",
            "reg_no_match": "Register number",
            "candidate_name_match": "Candidate name",
            "total_marks_match": "Total marks",
            "institution_match": "Institution",
        }
        for key, label in labels.items():
            tick = "✓" if checks.get(key) else "✗"
            color_tag = "#2F6B4F" if checks.get(key) else "#8C3A2E"
            story.append(Paragraph(
                f'<font color="{color_tag}">{tick}</font> {label}',
                styles["Normal"],
            ))
    story.append(Spacer(1, 10))

    # --- QR code ---
    story.append(Paragraph("<b>QR Code</b>", styles["Heading2"]))
    qr = data.get("qr_verification", {})
    story.append(Paragraph(f"Status: <b>{qr.get('status', 'N/A')}</b>", styles["Normal"]))
    if qr.get("domain"):
        story.append(Paragraph(f"Domain: <b>{qr['domain']}</b>", styles["Normal"]))
        story.append(Paragraph(
            f"Secure HTTPS: <b>{'Yes' if qr.get('is_secure') else 'No'}</b>",
            styles["Normal"],
        ))
        story.append(Paragraph(
            f"Official domain: <b>{'Yes' if qr.get('domain_authenticity') else 'No'}</b>",
            styles["Normal"],
        ))
    story.append(Spacer(1, 10))

    # --- AI analysis ---
    story.append(Paragraph("<b>AI / Image Analysis</b>", styles["Heading2"]))
    story.append(Paragraph(
        f"Layout match score: <b>{data.get('ai_match_score', 0)}</b>",
        styles["Normal"],
    ))
    story.append(Paragraph(
        f"Tamper probability: <b>{data.get('tamper_probability', 0)}</b>",
        styles["Normal"],
    ))

    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=0.5,
                            color=colors.HexColor("#DCD2B8"), spaceAfter=6))
    story.append(Paragraph(
        "This report is generated automatically by CertifyX and does not "
        "constitute a legal certificate of authenticity. Always verify "
        "directly with the Tamil Nadu State Board of School Examinations.",
        ParagraphStyle("Disclaimer", parent=styles["Normal"],
                       fontSize=8, textColor=colors.gray),
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer
