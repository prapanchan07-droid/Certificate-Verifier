"""
Name Validation Engine

Compares OCR extracted candidate name with
official government verified name.

Uses fuzzy matching and confidence scoring.
"""

from .fuzzy_match import FuzzyMatcher

class NameValidator:

    # Similarity thresholds
    EXACT_THRESHOLD = 0.98
    FUZZY_THRESHOLD = 0.90
    LOW_THRESHOLD = 0.70

    @staticmethod
    def validate(
        ocr_name,
        official_name,
        tamil_name=None
    ):

        result = {

            "candidate_name": None,
            
            "tamil_name": tamil_name,

            "tamil_name_found": tamil_result["found"],


            "ocr_name": ocr_name,

            "official_name": official_name,

            "tamil_name": tamil_name,

            "similarity": 0.0,

            "status": "UNKNOWN",

            "confidence": 0.0,

            "use_official": False

        }

        # -----------------------------
        # Missing Official Name
        # -----------------------------
        if not official_name:

            result["candidate_name"] = ocr_name
            result["status"] = "OFFICIAL_NOT_AVAILABLE"
            result["confidence"] = 0.60

            return result

        # -----------------------------
        # Missing OCR Name
        # -----------------------------
        if not ocr_name:

            result["candidate_name"] = official_name
            result["status"] = "OCR_FAILED"
            result["confidence"] = 1.00
            result["use_official"] = True

            return result

        # -----------------------------
        # Compute Similarity
        # -----------------------------
        similarity = FuzzyMatcher.similarity(
            ocr_name,
            official_name
        )

        result["similarity"] = round(similarity, 3)

        # -----------------------------
        # Exact Match
        # -----------------------------
        if similarity >= NameValidator.EXACT_THRESHOLD:

            result["candidate_name"] = official_name

            result["status"] = "EXACT_MATCH"

            result["confidence"] = 1.00

            return result

        # -----------------------------
        # Fuzzy Match
        # -----------------------------
        if similarity >= NameValidator.FUZZY_THRESHOLD:

            result["candidate_name"] = official_name

            result["status"] = "FUZZY_MATCH"

            result["confidence"] = similarity

            return result

        # -----------------------------
        # Weak OCR
        # -----------------------------
        if similarity >= NameValidator.LOW_THRESHOLD:

            result["candidate_name"] = official_name

            result["status"] = "LOW_CONFIDENCE"

            result["confidence"] = similarity

            result["use_official"] = True

            return result

        # -----------------------------
        # OCR Completely Wrong
        # -----------------------------
        result["candidate_name"] = official_name

        result["status"] = "MANUAL_REVIEW"

        result["confidence"] = similarity

        result["use_official"] = True

        return result