from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from app.core.official_verifier import OfficialVerifier

import cv2
import numpy as np

from pdf2image import convert_from_bytes

from app.core.ai_engine import AIVerificationEngine
from app.core.ocr_engine import OCREngine
from app.core.qr_engine import QREngine
from app.core.report_generator import generate_pdf_report
app = FastAPI(title="AI Verification Portal Architecture")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

            pages = convert_from_bytes(
                contents,
                dpi=300,
                poppler_path=r"C:\Users\vshar\Downloads\Release-26.02.0-0\poppler-26.02.0\Library\bin"
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

        if qr_results.get("data"):

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

            else:

                comparison = None

        else:

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
        if official_score >= 0.8 and qr_authentic:
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
    "checks": comparison["checks"] if comparison else {}
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