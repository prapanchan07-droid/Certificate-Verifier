import os

from app.services.base_verification import BaseVerificationService
from app.decision.decision_engine import DecisionEngine

TEMPLATE_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "templates",
    "tn_hsc_template.png",
)

class HSCVerificationService(BaseVerificationService):

    doc_type = "hsc"
    
    def __init__(self):
        super().__init__()
        self.decision_engine = DecisionEngine()

    async def verify(self, file):
        try:
            # existing verification code
            img, is_pdf = await self.load_document(file)

            img = self.preprocess_document(img, is_pdf)

            qr_results = self.extract_qr(img)

            ocr_results = self.extract_ocr(img)

            # After ocr_results is extracted, in hsc_service.py:
            cert_type = ocr_results.get("certificate_type", "HSS")
            print(f"HSC Certificate Type: {cert_type}")

            official_data, comparison, official_score, official_unavailable = (
                self.verify_official(qr_results, ocr_results)
            )

            ai_score, tamper_score = self.analyze_ai(
                img,
                TEMPLATE_PATH,
            )

            # your formula-based decision
            if comparison:
                score = comparison.get("score", 0)

                if score >= 95:
                    formula_verdict = "GENUINE"
                    formula_confidence = 95

                elif score >= 70:
                    formula_verdict = "SUSPICIOUS"
                    formula_confidence = 75

                else:
                    formula_verdict = "FAKE"
                    formula_confidence = 40

            elif qr_results.get("domain_authenticity"):
                formula_verdict = "SUSPICIOUS"
                formula_confidence = 60

            else:
                formula_verdict = "FAKE"
                formula_confidence = 40
            

            final_verdict, confidence, ml_block = self.run_ml(
                img=img,
                ai_score=ai_score,
                tamper_score=tamper_score,
                qr_results=qr_results,
                comparison=comparison,
                ocr_results=ocr_results,
                qr_authentic=qr_results.get("domain_authenticity", False),
                formula_verdict=formula_verdict,
                formula_confidence=formula_confidence,
            )

            if ml_block:
                decision = self.decision_engine.evaluate(
                    qr_result=qr_results,
                    comparison=comparison,
                    ai_score=ai_score,
                    tamper_score=tamper_score,
                    cnn_probability=ml_block["cnn_tamper_prob"],
                    rf_result={
                        "confidence": ml_block["rf_probability"]
                    },
                )

                final_verdict = decision["decision"]
                confidence = decision["confidence"]

            display_metadata = self.build_display_metadata(
                official_data,
                ocr_results,
            )

            response = self.build_response(
                final_verdict,
                confidence,
                ai_score,
                tamper_score,
                ocr_results,
                display_metadata,
                qr_results,
                official_data,
                comparison,
                official_unavailable,
                ml_block,
            )

            if ml_block:
                response["decision_reason"] = decision["reason"]
                response["decision_explanation"] = decision["explanation"]
                response["decision_details"] = decision["details"]

            return response

        except Exception as e:
            print(f"HSC Verification Error: {e}")
            return self.build_error_response(e)
