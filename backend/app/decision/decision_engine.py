from typing import Dict, Any


class DecisionEngine:
    """
    Combines the outputs of all AI modules and
    produces the final verification decision.
    """

    def __init__(self):
        pass

    def evaluate(
        self,
        qr_result: Dict[str, Any],
        comparison: Dict[str, Any],
        ai_score: float,
        tamper_score: float,
        cnn_probability: float,
        rf_result: Dict[str, Any],
    ) -> Dict[str, Any]:

        explanation = []

        qr_verified = (
            qr_result.get("domain_authenticity", False)
            and qr_result.get("is_secure", False)
        )

        comparison_score = comparison.get("score", 0) if comparison else 0

        rf_confidence = rf_result.get("confidence", 0.5)

        # -------------------------------
        # QR Verification
        # -------------------------------

        if qr_verified:
            explanation.append("Authentic Government QR detected.")
        else:
            explanation.append("Government QR could not be verified.")

        # -------------------------------
        # OCR Comparison
        # -------------------------------

        if comparison_score == 100:
            explanation.append("OCR fields perfectly match official records.")
        elif comparison_score >= 80:
            explanation.append("Most OCR fields match official records.")
        else:
            explanation.append("OCR comparison score is low.")

        # -------------------------------
        # CNN
        # -------------------------------

        if cnn_probability < 0.20:

            explanation.append(
                f"CNN detected no significant image tampering "
                f"({cnn_probability*100:.1f}% tamper probability)."
            )

        elif cnn_probability < 0.50:

            explanation.append(
                f"CNN detected minor visual anomalies "
                f"({cnn_probability*100:.1f}% tamper probability)."
            )

        elif cnn_probability < 0.80:

            explanation.append(
                f"CNN detected moderate tampering risk "
                f"({cnn_probability*100:.1f}% tamper probability)."
            )

        else:

            explanation.append(
                f"CNN detected strong evidence of tampering "
                f"({cnn_probability*100:.1f}% tamper probability)."
            )

        # -------------------------------
        # AI Engine
        # -------------------------------

        if not (qr_verified and comparison_score == 100):

            if ai_score >= 0.70:
                explanation.append(
                    f"Image authenticity score is high ({ai_score*100:.1f}%)."
                )
            else:
                explanation.append(
                    f"Image authenticity score is below the expected threshold ({ai_score*100:.1f}%)."
                )

        else:
            explanation.append(
                "Official government verification overrides image similarity analysis."
            )

        # -------------------------------
        # Random Forest
        # -------------------------------

        tampered_probability = (1 - rf_confidence) * 100

        explanation.append(
            f"Random Forest estimated {tampered_probability:.1f}% tampering likelihood before applying official verification."
        )

        # ============================================================
        # FINAL DECISION
        # ============================================================

        if qr_verified and comparison_score == 100:

            decision = "GENUINE"
            confidence = 99
            risk = "LOW"

        elif cnn_probability >= 0.85:

            decision = "FAKE"
            confidence = int(cnn_probability * 100)
            risk = "HIGH"

        elif ai_score >= 0.70 and tamper_score <= 0.30:

            decision = "GENUINE"
            confidence = int(ai_score * 100)
            risk = "LOW"

        elif rf_confidence > 0.70:

            decision = "SUSPICIOUS"
            confidence = int(rf_confidence * 100)
            risk = "MEDIUM"

        else:

            decision = "SUSPICIOUS"
            confidence = 50
            risk = "MEDIUM"
        
        # -------------------------------
        # Decision Summary
        # -------------------------------

        if decision == "GENUINE":

            reason = (
                "Certificate verified successfully using government QR, "
                "official record comparison and AI analysis."
            )

        elif decision == "SUSPICIOUS":

            reason = (
                "Certificate contains conflicting verification signals "
                "and should be reviewed manually."
            )

        else:

            reason = (
                "Certificate failed verification due to strong evidence "
                "of tampering."
            )

        return {

            "decision": decision,

            "confidence": confidence,

            "risk": risk,

            "reason": reason,

            "explanation": explanation,

            "details": {

                "qr_verified": qr_verified,

                "comparison_score": comparison_score,

                "ai_score": round(ai_score, 3),

                "tamper_score": round(tamper_score, 3),

                "cnn_probability": round(cnn_probability, 3),

                "rf_confidence": round(rf_confidence, 3),

            },

        }