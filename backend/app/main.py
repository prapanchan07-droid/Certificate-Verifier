from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

import cv2
import numpy as np
import os
import sys

from pdf2image import convert_from_bytes

from app.core.ai_engine import AIVerificationEngine
from app.core.ocr_engine import OCREngine
from app.core.qr_engine import QREngine
from app.core.official_verifier import OfficialVerifier
from app.core.report_generator import generate_pdf_report

# ==========================
# ML ADDON — CNN + RandomForest/XGBoost decision layer + Gemini explanation
# ==========================
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ml_engine"))
from ml_verifier import MLVerifier
from explanation_engine import explain_verdict

app = FastAPI(title="CertifyX — Certificate Verification API")

ALLOWED_ORIGINS = ["*"]

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

# .available is False if cnn_tamper_model.pt / tabular_model.joblib aren't
# found in ml_engine/ -- in that case the endpoint falls back to the
# original hand-weighted formula below, so this is safe to deploy even
# before/without training.
ml_verifier = MLVerifier()
print("ML VERIFIER AVAILABLE:", ml_verifier.available)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024

_HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(_HERE, "..", "templates", "tn_10th_template.png")


@app.get("/")
def health():
    return {"status": "ok", "service": "CertifyX", "ml_available": ml_verifier.available}


@app.post("/api/verify")
async def verify_certificate(file: UploadFile = File(...)):

    print("API CALLED — file:", file.filename)
    contents = await file.read()

    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 20 MB).")

    official_data: dict = {}
    comparison = None
    official_score = 0.0
    official_unavailable = False

    try:

        # ===============================
        # PDF → IMAGE
        # ===============================
        if file.filename.lower().endswith(".pdf"):
            poppler_path = os.environ.get("POPPLER_PATH")
            pages = convert_from_bytes(contents, dpi=150, poppler_path=poppler_path)
            print("PDF CONVERTED — pages:", len(pages))
            page = np.array(pages[0])
            img = cv2.cvtColor(page, cv2.COLOR_RGB2BGR)
            is_pdf = True

        # ===============================
        # IMAGE
        # ===============================
        else:
            nparr = np.frombuffer(contents, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            is_pdf = False

        if img is None:
            raise HTTPException(status_code=400, detail="Invalid or unreadable file.")

        print("IMAGE SIZE:", img.shape)

        # Only deskew images, not PDFs
        if not is_pdf:
            img = ai_engine.deskew(img)

        # Enhance — no upscale for PDFs
        img = ai_engine.enhance(img, is_pdf=is_pdf)

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
                    comparison = official_verifier.compare_records(
                        ocr_results, official_data
                    )
                    print("COMPARISON =", comparison)
                    official_score = comparison["score"] / 100.0
                except Exception as e:
                    print("COMPARE ERROR:", e)
                    official_unavailable = True
            else:
                official_unavailable = True

        # ==========================
        # DISPLAY METADATA — prefer the official government record (clean
        # HTML text, not an OCR'd photograph) whenever it's available.
        # Only fall back to OCR-extracted fields when there's no QR / no
        # reachable official record to compare against.
        # ==========================
        if official_data.get("success"):
            display_metadata = {
                "candidate_name": official_data.get("candidate_name") or ocr_results.get("candidate_name"),
                "roll_no": official_data.get("roll_no") or ocr_results.get("roll_no"),
                "reg_no": official_data.get("reg_no") or ocr_results.get("reg_no"),
                "total_marks": official_data.get("total_marks") or ocr_results.get("total_marks"),
                "institution": official_data.get("institution") or ocr_results.get("institution"),
                "source": "official_record",
            }
        else:
            display_metadata = {
                "candidate_name": ocr_results.get("candidate_name"),
                "roll_no": ocr_results.get("roll_no"),
                "reg_no": ocr_results.get("reg_no"),
                "total_marks": ocr_results.get("total_marks"),
                "institution": ocr_results.get("institution"),
                "source": "ocr_extraction",
            }
        
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

        qr_authentic = qr_results.get("domain_authenticity", False)

        # ==========================
        # CONFIDENCE (original hand-weighted formula — kept as the
        # fallback path if the trained ML models aren't available)
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
        # FINAL DECISION (original formula-based verdict — kept as the
        # fallback path if the trained ML models aren't available)
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
        # ML DECISION LAYER (CNN + RandomForest/XGBoost) — overrides the
        # formula-based verdict/confidence above when trained models are
        # available. Never breaks the endpoint if models are missing or
        # inference fails for any reason.
        # ==========================
        ml_block = None
        if ml_verifier.available:
            try:
                features = ml_verifier.build_features(
                    img, ai_score, tamper_score, qr_results, comparison, ocr_results
                )
                ml_verdict, ml_confidence, contributions = ml_verifier.predict(features)
                ml_block = {
                    "verdict": ml_verdict,
                    "confidence": round(ml_confidence * 100),
                    "top_factors": contributions,
                }

                # Trained model's raw output, before any override — kept
                # for transparency/debugging.
                ml_block["raw_verdict"] = ml_verdict
                ml_block["raw_confidence"] = ml_block["confidence"]

                final_verdict = ml_verdict
                confidence = ml_block["confidence"]

                # SAFETY OVERRIDE: a 100% match against the live government
                # database plus an authentic QR domain is a stronger, more
                # reliable signal than the CV-based tamper score, which is
                # sensitive to photo angle/lighting/compression and can
                # misfire on genuine documents. Never let the model call
                # FAKE when the official record fully confirms the document.
                if comparison and comparison["score"] == 100 and qr_authentic:
                    if final_verdict in ("FAKE", "SUSPICIOUS"):
                        final_verdict = "GENUINE"
                    confidence = max(confidence, 90)
                    ml_block["override_applied"] = (
                        "Official record fully matched — verdict adjusted "
                        "from model output to reflect this."
                    )

                # Generate the explanation from the FINAL (possibly
                # overridden) verdict/confidence, so the text always
                # matches what the user actually sees on screen.
                ml_block["verdict"] = final_verdict
                ml_block["confidence"] = confidence

                explanation = explain_verdict(
                    verdict=final_verdict,
                    confidence=confidence,
                    checks=comparison["checks"] if comparison else {},
                    qr_authentic=qr_authentic,
                    tamper_score=tamper_score,
                    top_factors=ml_block["top_factors"],
                    ocr_results=ocr_results,
                )
                ml_block["explanation"] = explanation["explanation"]
                ml_block["explanation_source"] = explanation["source"]
            except Exception as e:
                print("ML VERIFIER ERROR (falling back to formula):", e)
                ml_block = None

        return {
            "final_decision": final_verdict,
            "confidence_score": confidence,
            "ai_match_score": round(ai_score, 2),
            "tamper_probability": round(tamper_score, 2),
            "extracted_metadata": ocr_results,
            "display_metadata": display_metadata,
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
            "ml_verification": ml_block,
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
            "display_metadata": None,
            "ml_verification": None,
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