"""
Parser Confidence Engine

Calculates confidence for parsed HSC data.
"""

import re


class ParserConfidence:

    # Weight assigned to each field
    WEIGHTS = {
        "candidate_name": 20,
        "roll_number": 15,
        "register_number": 15,
        "school_name": 15,
        "total_marks": 15,
        "date_of_birth": 10,
        "group": 5,
        "medium": 5,
    }

    @staticmethod
    def _valid_text(value, min_len=3):
        return isinstance(value, str) and len(value.strip()) >= min_len

    @staticmethod
    def _valid_number(value):
        if value is None:
            return False

        value = str(value).strip()

        return value.isdigit()

    @staticmethod
    def _valid_marks(value):

        if value is None:
            return False

        try:
            value = int(value)

            return 0 <= value <= 600

        except:
            return False

    @staticmethod
    def _valid_dob(value):

        if not value:
            return False

        return bool(
            re.match(
                r"\d{2}/\d{2}/\d{4}",
                str(value)
            )
        )

    @classmethod
    def calculate(cls, data):

        score = 0

        details = {}

        # Candidate Name
        ok = cls._valid_text(data.get("candidate_name"))
        details["candidate_name"] = ok
        if ok:
            score += cls.WEIGHTS["candidate_name"]

        # Roll Number
        ok = cls._valid_number(data.get("roll_number"))
        details["roll_number"] = ok
        if ok:
            score += cls.WEIGHTS["roll_number"]

        # Register Number
        ok = cls._valid_text(data.get("register_number"))
        details["register_number"] = ok
        if ok:
            score += cls.WEIGHTS["register_number"]

        # School
        ok = cls._valid_text(data.get("school_name"), 5)
        details["school_name"] = ok
        if ok:
            score += cls.WEIGHTS["school_name"]

        # Marks
        ok = cls._valid_marks(data.get("total_marks"))
        details["total_marks"] = ok
        if ok:
            score += cls.WEIGHTS["total_marks"]

        # DOB
        ok = cls._valid_dob(data.get("date_of_birth"))
        details["date_of_birth"] = ok
        if ok:
            score += cls.WEIGHTS["date_of_birth"]

        # Group
        ok = cls._valid_text(data.get("group"))
        details["group"] = ok
        if ok:
            score += cls.WEIGHTS["group"]

        # Medium
        ok = cls._valid_text(data.get("medium"))
        details["medium"] = ok
        if ok:
            score += cls.WEIGHTS["medium"]

        # Confidence label
        if score >= 90:
            label = "EXCELLENT"

        elif score >= 75:
            label = "GOOD"

        elif score >= 60:
            label = "FAIR"

        elif score >= 40:
            label = "LOW"

        else:
            label = "VERY_LOW"

        return {

            "score": score,

            "label": label,

            "details": details

        }