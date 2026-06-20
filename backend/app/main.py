from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from app.core.official_verifier import OfficialVerifier

import cv2
import numpy as np
import os

from pdf2image import convert_from_bytes

from app.core.ai_engine import AIVerificationEngine
from app.core.ocr_engine import OCREngine
from app.core.qr_engine import QREngine
from app.core.report_generator import generate_pdf_report
app = FastAPI(title="AI Verification Portal Architecture")
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

import io
from fastapi import Body
from fastapi.responses import StreamingResponse
from app.core.report_generator import generate_pdf_report


@app.post("/api/verify")
async def verify_certificate(file: UploadFile = File(...)):

    print("API CALLED")
    print("FILE:", file.filename)

    contents = await file.read()

    try:

        # ===============================
        # PDF SUPPORT
        # ===============================

        if file.filename.lower().endswith(".pdf"):

            poppler_path = os.environ.get("POPPLER_PATH")  # None on Linux
            # containers where poppler-utils is installed system-wide and
            # already on PATH; set this env var only on Windows dev boxes
            # where poppler isn't installed globally.

            pages = convert_from_bytes(
                contents,
                dpi=300,
                poppler_path=poppler_path
            )
            print("PDF CONVERTED")

            page = np.array(pages[0])

            img = cv2.cvtColor(
                page,
                cv2.COLOR_RGB2BGR
            )

            cv2.imwrite(
                "full_page.jpg",
                img
            )

        # ===============================
        # IMAGE SUPPORT
        # ===============================

        else:

            nparr = np.frombuffer(
                contents,
                np.uint8
            )

            img = cv2.imdecode(
                nparr,
                cv2.IMREAD_COLOR
            )

        # ==========================
        # INVALID FILE CHECK
        # ==========================
        if img is None:

            raise HTTPException(
                status_code=400,
                detail="Invalid file format."
            )

        # ==========================
        # QR SCAN
        # ==========================
        qr_results = qr_engine.scan_and_verify(
            img
        )

        # ==========================
        # OCR
        # ==========================
        success, encoded = cv2.imencode(
            ".png",
            img
        )
        
        if not success:
            raise Exception(
                "Failed to encode image"
            )

        ocr_results = ocr_engine.extract_details(
            encoded.tobytes()
        )
        
        print("OCR RESULTS")
        print(ocr_results)
        
        official_score = 0
        official_unavailable = False  # True only when a QR was found but
                                       # the official record could not be
                                       # reached/compared (network error,
                                       # expired SSL cert, etc.) -- distinct
                                       # from "compared and didn't match".

        if qr_results.get("data") and qr_results.get("domain_authenticity"):

            print("QR URL =", qr_results["data"])
            print("OFFICIAL VERIFIER STARTED")
            
            official_data = (
                official_verifier.extract_official_data(
                    qr_results["data"]
                )
            )
            
            print("OFFICIAL DATA =", official_data)

            if official_data.get("success"):

                try:
                    
                    print("OCR SENT TO COMPARE")
                    print(ocr_results)

                    print("OFFICIAL SENT TO COMPARE")
                    print(official_data)
                    
                    comparison = (
                        official_verifier.compare_records(
                            ocr_results,
                            official_data
                        )
                    )

                    print("COMPARISON RESULT")
                    print(comparison)

                    official_score = comparison["score"] / 100.0

                except Exception as e:

                    print("COMPARE ERROR:", str(e))

                    comparison = None
                    official_score = 0
                    official_unavailable = True

            else:

                # Official site could not be reached (network error,
                # expired SSL cert, timeout, etc.) -- we genuinely don't
                # know if the certificate is real or fake here.
                comparison = None
                official_unavailable = True

        else:

            # Either no QR data at all, or the QR points at a domain
            # that isn't on our allowlist -- we deliberately never fetch
            # an unverified URL (prevents a malicious QR code from being
            # used to make this server request arbitrary/internal URLs).
            comparison = None
        
        template = cv2.imread(
            "templates/tn_10th_template.png"
        )
        
        print("TEMPLATE LOADED:", template is not None)

        if template is not None:

            ai_score, tamper_score = (
                ai_engine.calculate_tamper_score(
                    img,
                    template
                )
            )

        else:

            ai_score = 0.75
            tamper_score = 0.25
            
        print("AI SCORE:", ai_score)
        print("TAMPER:", tamper_score)

        # ==========================
        # QR AUTHENTICITY
        # ==========================
        qr_authentic = qr_results.get(
            "domain_authenticity",
            False
        )
        
        print("QR RESULTS")
        print(qr_results)

        ocr_score = 0

        if ocr_results.get("candidate_name"):
            ocr_score += 0.25

        if ocr_results.get("roll_no"):
            ocr_score += 0.25

        if ocr_results.get("reg_no"):
            ocr_score += 0.25

        if ocr_results.get("institution"):
            ocr_score += 0.25

        if official_unavailable:

            # The official record was never actually compared, so don't
            # let its 60% weight collapse confidence to near-zero as if
            # the document had failed verification. Reweight across the
            # signals we do have.
            confidence = int(
            (
                ai_score * 0.30
                + (1 - tamper_score) * 0.30
                + (1.0 if qr_authentic else 0.0) * 0.40
            ) * 100
            )

        else:

            confidence = int(
            (
                ai_score * 0.10
                + (1 - tamper_score) * 0.10
                + (1.0 if qr_authentic else 0.0) * 0.20
                + official_score * 0.60
            ) * 100
            )

            if comparison and comparison["score"] == 100:
                confidence = 95
            
        # ==========================
        # FINAL DECISION
        # ==========================
        if official_unavailable:

            # We genuinely don't know -- the official source couldn't be
            # reached, so we shouldn't call this FAKE or GENUINE.
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
            "ai_match_score": round(
                ai_score,
                2
            ),
            "tamper_probability": round(
                tamper_score,
                2
            ),
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
    "error": (
        official_data.get("error")
        if official_unavailable and "official_data" in locals()
        else None
    )
}
        }

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
                "error": str(e)
            },
            "qr_verification": {
                "status": "NOT_FOUND",
                "is_secure": False,
                "data": None,
                "domain": None,
                "domain_authenticity": False
            }
        }
    
@app.post("/api/report")
async def download_report(data: dict = Body(...)):

    try:

        print("REPORT REQUEST RECEIVED")
        print("DATA:", data)

        pdf_buffer = generate_pdf_report(data)

        size = pdf_buffer.getbuffer().nbytes

        print("PDF SIZE =", size)

        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition":
                "attachment; filename=verification_report.pdf"
            }
        )

    except Exception as e:

        print("REPORT ERROR:", str(e))

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )