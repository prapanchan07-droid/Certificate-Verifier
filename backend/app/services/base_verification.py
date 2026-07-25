from __future__ import annotations

from abc import ABC, abstractmethod
import os
import sys

from fastapi import UploadFile, HTTPException

import cv2
import numpy as np
from pdf2image import convert_from_bytes

from app.core.ai_engine import AIVerificationEngine
from app.core.ocr_engine import OCREngine
from app.core.qr_engine import QREngine
from app.core.official_verifier import OfficialVerifier

# explain_verdict is document-type-agnostic (verdict/confidence/checks/
# top_factors are all generic), so it's shared infrastructure here rather
# than duplicated per service.
_ML_ENGINE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "ml_engine"
)
sys.path.insert(0, _ML_ENGINE_PATH)
from explanation_engine import explain_verdict


class BaseVerificationService(ABC):

    doc_type: str = "unknown"

    # Class-level default so every subclass gets this without having to
    # redeclare it. Override on a specific subclass only if that document
    # type genuinely needs a different limit.
    MAX_UPLOAD_BYTES = 20 * 1024 * 1024

    def __init__(self):
        print(f">>> BaseVerificationService initialized ({self.__class__.__name__})")

        self.ai_engine = AIVerificationEngine()
        self.ocr_engine = OCREngine()
        self.qr_engine = QREngine()
        self.official_verifier = OfficialVerifier()

        # Subclasses that support ML verification set this in their own
        # __init__ (e.g. self.ml_verifier = MLVerifier()). Left unset here
        # -> run_ml() safely no-ops via getattr below, so stub services
        # (like an in-progress HSCVerificationService) don't need to know
        # or care about ML at all yet.

    @abstractmethod
    async def verify(self, file):
        pass

    # ------------------------------------------------------------------
    # Fixed pipeline steps — same for every subclass.
    # ------------------------------------------------------------------

    async def load_document(self, file: UploadFile):
        contents = await file.read()

        if len(contents) > self.MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File too large (max 20 MB).")

        if file.filename.lower().endswith(".pdf"):
            poppler_path = os.environ.get("POPPLER_PATH")
            pages = convert_from_bytes(contents, dpi=150, poppler_path=poppler_path)
            page = np.array(pages[0])
            img = cv2.cvtColor(page, cv2.COLOR_RGB2BGR)
            return img, True

        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img, False

    def preprocess_document(self, img, is_pdf):
        if not is_pdf:
            img = self.ai_engine.deskew(img)
        img = self.ai_engine.enhance(img, is_pdf=is_pdf)
        return img

    def extract_qr(self, img):
        qr_results = self.qr_engine.scan_and_verify(img)
        print("QR RESULTS:", qr_results)
        return qr_results

    def extract_ocr(self, img):
        success, encoded = cv2.imencode(".png", img)
        if not success:
            raise RuntimeError("OCR Encode Failed")
        ocr_results = self.ocr_engine.extract_details(encoded.tobytes())
        print("OCR RESULTS")
        print(ocr_results)
        return ocr_results

    def verify_official(self, qr_results, ocr_results):
        official_data = {}
        comparison = None
        official_score = 0.0
        official_unavailable = False

        if qr_results.get("data") and qr_results.get("domain_authenticity"):
            print("QR URL =", qr_results["data"])

            official_data = self.official_verifier.extract_official_data(qr_results["data"])
            print("OFFICIAL DATA")
            print(official_data)

            if official_data.get("success"):
                try:
                    comparison = self.official_verifier.compare_records(ocr_results, official_data)
                    print("COMPARISON")
                    print(comparison)
                    official_score = comparison["score"] / 100.0
                except Exception as e:
                    print("COMPARE ERROR:", e)
                    official_unavailable = True
            else:
                official_unavailable = True

        return official_data, comparison, official_score, official_unavailable

    def analyze_ai(self, img, template_path):
        template = cv2.imread(template_path) if template_path else None
        print("TEMPLATE LOADED:", template is not None)

        if template is not None:
            ai_score, tamper_score = self.ai_engine.calculate_tamper_score(img, template)
        else:
            ai_score, tamper_score = 0.5, 0.5

        print("AI SCORE:", ai_score)
        print("TAMPER:", tamper_score)
        return ai_score, tamper_score

    def build_display_metadata(self, official_data, ocr_results):
        """Prefer the clean official-record values over the OCR'd
        photograph, wherever the official record is available."""
        if official_data.get("success"):
            return {
                "candidate_name": official_data.get("candidate_name") or ocr_results.get("candidate_name"),
                "roll_no": official_data.get("roll_no") or ocr_results.get("roll_no"),
                "reg_no": official_data.get("reg_no") or ocr_results.get("reg_no"),
                "total_marks": official_data.get("total_marks") or ocr_results.get("total_marks"),
                "institution": official_data.get("institution") or ocr_results.get("institution"),
                "source": "official_record",
            }
        return {
            "candidate_name": ocr_results.get("candidate_name"),
            "roll_no": ocr_results.get("roll_no"),
            "reg_no": ocr_results.get("reg_no"),
            "total_marks": ocr_results.get("total_marks"),
            "institution": ocr_results.get("institution"),
            "source": "ocr_extraction",
        }

    def run_ml(
        self,
        img,
        ai_score,
        tamper_score,
        qr_results,
        comparison,
        ocr_results,
        qr_authentic,
        formula_verdict,
        formula_confidence,
    ):
        """
        Runs the CNN + RandomForest/XGBoost decision layer if this service
        has a configured self.ml_verifier that's available (i.e. trained
        model files were found). Applies the official-record override
        (a 100% match + authentic QR beats a noisy CV tamper score) BEFORE
        generating the explanation, so the explanation text always matches
        the final verdict shown to the user.

        Falls back to the formula-based verdict/confidence untouched if
        ML is unavailable or fails for any reason -- this must never break
        the /verify endpoint.

        Returns (final_verdict, confidence, ml_block). ml_block is None
        when ML isn't available/used.
        """
        ml_verifier = getattr(self, "ml_verifier", None)

        final_verdict = formula_verdict
        confidence = formula_confidence
        ml_block = None

        if not ml_verifier or not ml_verifier.available:
            return final_verdict, confidence, ml_block

        try:
            features = ml_verifier.build_features(
                img, ai_score, tamper_score, qr_results, comparison, ocr_results
            )
            (
                ml_verdict,
                ml_confidence,
                contributions,
                cnn_probability,
                rf_probability,
            ) = ml_verifier.predict(features)
            print("RAW ML CONFIDENCE:", ml_confidence)

            ml_block = {
                "verdict": ml_verdict,
                "confidence": round(ml_confidence * 100),

                # NEW
                "cnn_tamper_prob": cnn_probability,
                "rf_probability": rf_probability,

                "top_factors": contributions,
                "model_type": type(ml_verifier.tabular_model).__name__,
                "raw_verdict": ml_verdict,
            }
            
            ml_block["raw_confidence"] = ml_block["confidence"]

            final_verdict = ml_verdict
            confidence = ml_block["confidence"]

            # SAFETY OVERRIDE: a 100% match against the live government
            # database plus an authentic QR domain is a stronger, more
            # reliable signal than the CV-based tamper score, which can
            # misfire on genuine documents (angle/lighting/compression).
            if comparison and comparison["score"] == 100 and qr_authentic:
                if final_verdict in ("FAKE", "SUSPICIOUS"):
                    final_verdict = "GENUINE"
                confidence = max(confidence, 90)
                ml_block["override_applied"] = (
                    "Official record fully matched — verdict adjusted "
                    "from model output to reflect this."
                )

            # Explanation generated from the FINAL (possibly overridden)
            # verdict/confidence, so the text never contradicts the number
            # shown on screen.
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
            print(f"ML ERROR ({self.doc_type}):", e)
            ml_block = None
            final_verdict = formula_verdict
            confidence = formula_confidence

        return final_verdict, confidence, ml_block

    def build_response(
        self,
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
    ):
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

    def build_error_response(self, error: Exception):
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
                "error": str(error),
            },
            "display_metadata": None,
            "qr_verification": {
                "status": "NOT_FOUND",
                "is_secure": False,
                "data": None,
                "domain": None,
                "domain_authenticity": False,
            },
            "official_verification": None,
            "ml_verification": None,
        }