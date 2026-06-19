import io

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer
)
from reportlab.lib.styles import getSampleStyleSheet


def generate_pdf_report(data):

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(buffer)

    styles = getSampleStyleSheet()

    story = []

    story.append(
    Paragraph(
        "Certificate Verification Report",
        styles["Title"]
    )
)

    story.append(Spacer(1, 20))

    story.append(
        Paragraph(
            f"<b>Decision:</b> {data['final_decision']}",
            styles["Normal"]
        )
    )

    story.append(
        Paragraph(
            f"<b>Confidence Score:</b> {data['confidence_score']}%",
            styles["Normal"]
        )
    )

    story.append(Spacer(1, 10))

    meta = data["extracted_metadata"]

    story.append(
        Paragraph(
            "<b>OCR Extracted Metadata</b>",
            styles["Heading2"]
        )
    )

    story.append(
        Paragraph(
            f"Roll Number: {meta.get('roll_no','N/A')}",
            styles["Normal"]
        )
    )

    story.append(
        Paragraph(
            f"Register Number: {meta.get('reg_no','N/A')}",
            styles["Normal"]
        )
    )

    story.append(
        Paragraph(
            f"Institution: {meta.get('institution','N/A')}",
            styles["Normal"]
        )
    )

    story.append(Spacer(1, 10))

    qr = data["qr_verification"]

    story.append(
        Paragraph(
            "<b>QR Verification</b>",
            styles["Heading2"]
        )
    )

    story.append(
        Paragraph(
            f"Status: {qr.get('status')}",
            styles["Normal"]
        )
    )

    story.append(
        Paragraph(
            f"Domain: {qr.get('domain')}",
            styles["Normal"]
        )
    )

    story.append(
        Paragraph(
            f"Secure HTTPS: {qr.get('is_secure')}",
            styles["Normal"]
        )
    )

    story.append(Spacer(1, 10))

    story.append(
        Paragraph(
            "<b>AI Analysis</b>",
            styles["Heading2"]
        )
    )

    story.append(
        Paragraph(
            f"AI Match Score: {data.get('ai_match_score')}",
            styles["Normal"]
        )
    )

    story.append(
        Paragraph(
            f"Tamper Probability: {data.get('tamper_probability')}",
            styles["Normal"]
        )
    )
    
    doc.build(story)

    buffer.seek(0)

    print("PDF SIZE =", len(buffer.getvalue()))

    return buffer