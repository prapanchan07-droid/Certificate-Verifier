from fastapi import UploadFile, HTTPException
import os
import sys

from app.services.base_verification import BaseVerificationService

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ML_ENGINE_PATH = os.path.join(CURRENT_DIR, "..", "..", "ml_engine")
sys.path.insert(0, ML_ENGINE_PATH)

from ml_verifier import MLVerifier


class SSLCVerificationService(BaseVerificationService):

    doc_type = "SSLC"

    def __init__(self):
        super().__init__()

        self.ml_verifier = MLVerifier()
        print("SSLC ML VERIFIER AVAILABLE:", self.ml_verifier.available)

        self.TEMPLATE_PATH = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "..", "templates", "tn_10th_template.png",
        )

    async def verify(self, file: UploadFile):
        print("API CALLED:", file.filename)

        try:
            img, is_pdf = await self.load_document(file)

            if img is None:
                raise HTTPException(status_code=400, detail="Invalid image.")

            print("IMAGE SIZE:", img.shape)

            img = self.preprocess_document(img, is_pdf)
            qr_results = self.extract_qr(img)
            ocr_results = self.extract_ocr(img)

            official_data, comparison, official_score, official_unavailable = (
                self.verify_official(qr_results, ocr_results)
            )

            display_metadata = self.build_display_metadata(official_data, ocr_results)

            ai_score, tamper_score = self.analyze_ai(img, self.TEMPLATE_PATH)
            qr_authentic = qr_results.get("domain_authenticity", False)

            # ==========================================
            # FORMULA-BASED CONFIDENCE/VERDICT — kept as the fallback
            # path used when ML models aren't available.
            # ==========================================
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

            if official_unavailable:
                final_verdict = "UNVERIFIED"
            elif official_score >= 0.80 and qr_authentic:
                final_verdict = "GENUINE"
            elif confidence < 50:
                final_verdict = "FAKE"
            else:
                final_verdict = "SUSPICIOUS"

            # ==========================================
            # ML DECISION LAYER — overrides the formula result above
            # when available. Never breaks this endpoint if it fails.
            # ==========================================
            final_verdict, confidence, ml_block = self.run_ml(
                img, ai_score, tamper_score, qr_results, comparison,
                ocr_results, qr_authentic, final_verdict, confidence,
            )

            return self.build_response(
                final_verdict, confidence, ai_score, tamper_score,
                ocr_results, display_metadata, qr_results, official_data,
                comparison, official_unavailable, ml_block,
            )

        except HTTPException:
            raise

        except Exception as e:
            import traceback
            traceback.print_exc()
            return self.build_error_response(e)