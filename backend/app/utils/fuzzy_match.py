"""
Utility functions for fuzzy string comparison.

Used for:
- Candidate Name
- Institution
- Group
- Medium
"""

import re
from difflib import SequenceMatcher


class FuzzyMatcher:

    @staticmethod
    def clean(text: str) -> str:
        """
        Remove punctuation, duplicate spaces and convert to uppercase.
        """

        if not text:
            return ""

        text = text.upper()

        text = re.sub(r"[^A-Z0-9 ]", " ", text)

        text = re.sub(r"\s+", " ", text)

        return text.strip()


    @staticmethod
    def similarity(a: str, b: str) -> float:
        """
        Returns similarity between 0 and 1.
        """

        a = FuzzyMatcher.clean(a)
        b = FuzzyMatcher.clean(b)

        if not a or not b:
            return 0.0

        return SequenceMatcher(None, a, b).ratio()


    @staticmethod
    def is_match(a: str,
                 b: str,
                 threshold: float = 0.90) -> bool:
        """
        True if similarity >= threshold
        """

        return (
            FuzzyMatcher.similarity(a, b)
            >= threshold
        )


    @staticmethod
    def compare(a: str,
                b: str,
                threshold: float = 0.90):

        score = FuzzyMatcher.similarity(a, b)

        return {

            "match": score >= threshold,

            "score": round(score, 3),

            "ocr": a,

            "official": b

        }