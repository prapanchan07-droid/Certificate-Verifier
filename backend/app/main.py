from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

import cv2
import numpy as np
import os

from pdf2image import convert_from_bytes

from app.core.ai_engine import AIVerificationEngine
from app.core.ocr_engine import OCREngine
from app.core.qr_engine import QREngine
from app.core.official_verifier import OfficialVerifier
from app.core.report_generator import generate_pdf_report

app = FastAPI(title="CertifyX — Certificate Verification API")

@app.get("/")
def health():
    return {"status": "ok", "service": "CertifyX"}

ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:5173"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ai_engine = AIVerificationEngine()
ocr_engine = OCREngine()
qr_engine = QREngine()
official_verifier = OfficialVerifier()

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB

# Resolve template path relative to this file so it works regardless of cwd
_HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(_HERE, "..", "templates", "tn_10th_template.png")


@app.post("/api/verify")
async def verify_certificate(file: UploadFile = File(...)):

    print("API CALLED — file:", file.filename)

    contents = await file.read()

    # ==========================
    # FILE SIZE GUARD
    # ==========================
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 20 MB).")

    # Initialise so the error block can always reference them safely
    official_data: dict = {}
    comparison = None
    official_score = 0.0
    official_unavailable = False

    try:

        # ===============================
        # PDF → IMAGE
        # ===============================
        if file.filename.lower().endswith(".pdf"):
            # poppler_path=None works on Linux where poppler-utils is on PATH
            poppler_path = os.environ.get("POPPLER_PATH")
            pages = convert_from_bytes(contents, dpi=250, poppler_path=poppler_path)
            print("PDF CONVERTED — pages:", len(pages))
            page = np.array(pages[0])
            img = cv2.cvtColor(page, cv2.COLOR_RGB2BGR)

        # ===============================
        # IMAGE
        # ===============================
        else:
            nparr = np.frombuffer(contents, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise HTTPException(status_code=400, detail="Invalid or unreadable file.")

        # ===============================
        # DESKEW / ANGLE CORRECTION
        # ===============================
        img = ai_engine.deskew(img)

        # ===============================
        # CNN ENHANCEMENT
        # ===============================
        img = ai_engine.enhance(img)

        # ==========================
        # QR SCAN
        # ==========================
        qr_results = qr_engine.scan_and_verify(img)

        # ==========================
        # OCR
        # ==========================
        success, encoded = cv2.imencode(".png", img)
        if not success:
            raise RuntimeError("Failed to encode image for OCR")

        ocr_results = ocr_engine.extract_details(encoded.tobytes())
        print("OCR RESULTS:", ocr_results)

        # ==========================
        # OFFICIAL RECORD
        # ==========================
        if qr_results.get("data") and qr_results.get("domain_authenticity"):
            print("QR URL =", qr_results["data"])
            official_data = official_verifier.extract_official_data(qr_results["data"])
            print("OFFICIAL DATA =", official_data)

            if official_data.get("success"):
                try:
                    comparison = official_verifier.compare_records(ocr_results, official_data)
                    print("COMPARISON =", comparison)
                    official_score = comparison["score"] / 100.0
                except Exception as e:
                    print("COMPARE ERROR:", e)
                    official_unavailable = True
            else:
                official_unavailable = True

        # ==========================
        # AI TAMPER ANALYSIS
        # ==========================
        template = cv2.imread(TEMPLATE_PATH)
        print("TEMPLATE LOADED:", template is not None)

        if template is not None:
            ai_score, tamper_score = ai_engine.calculate_tamper_score(img, template)
        else:
            ai_score, tamper_score = 0.5, 0.5

        print("AI SCORE:", ai_score, "| TAMPER:", tamper_score)

        # ==========================
        # QR AUTHENTICITY
        # ==========================
        qr_authentic = qr_results.get("domain_authenticity", False)

        # ==========================
        # CONFIDENCE
        # ==========================
        if official_unavailable:
            confidence = int((
                ai_score * 0.30
                + (1 - tamper_score) * 0.30
                + (1.0 if qr_authentic else 0.0) * 0.40
            ) * 100)
        else:
            confidence = int((
                ai_score * 0.10
                + (1 - tamper_score) * 0.10
                + (1.0 if qr_authentic else 0.0) * 0.20
                + official_score * 0.60
            ) * 100)

            if comparison and comparison["score"] == 100:
                confidence = 95

        # ==========================
        # FINAL DECISION
        # ==========================
        if official_unavailable:
            final_verdict = "UNVERIFIED"
        elif official_score >= 0.8 and qr_authentic:
            final_verdict = "GENUINE"
        elif confidence < 50:
            final_verdict = "FAKE"
        else:
            final_verdict = "SUSPICIOUS"

        # ==========================
        # RESPONSE
        # ==========================
        return {
            "final_decision": final_verdict,
            "confidence_score": confidence,
            "ai_match_score": round(ai_score, 2),
            "tamper_probability": round(tamper_score, 2),
            "extracted_metadata": ocr_results,
            "qr_verification": qr_results,
            "official_verification": {
                "score": comparison["score"] if comparison else 0,
                "checks": comparison["checks"] if comparison else {},
                "status": (
                    "UNAVAILABLE" if official_unavailable
                    else "MATCHED" if comparison
                    else "NOT_CHECKED"
                ),
                "error": official_data.get("error") if official_unavailable else None,
            },
        }

    except HTTPException:
        raise

    except Exception as e:
        import traceback
        print("FULL ERROR:")
        traceback.print_exc()
        return {
            "final_decision": "ERROR",
            "confidence_score": 0,
            "ai_match_score": 0,
            "tamper_probability": 0,
            "extracted_metadata": {
                "candidate_name": None,
                "roll_no": None,
                "reg_no": None,
                "total_marks": None,
                "institution": None,
                "error": str(e),
            },
            "qr_verification": {
                "status": "NOT_FOUND",
                "is_secure": False,
                "data": None,
                "domain": None,
                "domain_authenticity": False,
            },
        }


@app.post("/api/report")
async def download_report(data: dict = Body(...)):
    try:
        pdf_buffer = generate_pdf_report(data)
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=verification_report.pdf"
            },
        )
    except Exception as e:
        print("REPORT ERROR:", e)
        raise HTTPException(status_code=500, detail=str(e))
