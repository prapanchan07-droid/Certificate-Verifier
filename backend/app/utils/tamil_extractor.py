"""
Tamil Name Extractor

Extracts the Tamil candidate name from OCR text.

Supports:
- தேர்வரின் பெயர்
- மாணவர் பெயர்
- பெயர்
"""

import re


class TamilExtractor:

    # Common Tamil labels
    NAME_LABELS = [
        "தேர்வரின் பெயர்",
        "மாணவர் பெயர்",
        "பெயர்",
    ]

    @staticmethod
    def is_tamil(text: str) -> bool:
        """
        Returns True if the string contains Tamil Unicode characters.
        """
        if not text:
            return False

        return any("\u0B80" <= ch <= "\u0BFF" for ch in text)

    @staticmethod
    def clean_name(text: str) -> str:
        """
        Keep only Tamil letters and spaces.
        """
        if not text:
            return ""

        text = "".join(
            ch
            for ch in text
            if ("\u0B80" <= ch <= "\u0BFF") or ch == " "
        )

        text = re.sub(r"\s+", " ", text)

        return text.strip()

    @classmethod
    def extract(cls, lines):
        """
        Extract Tamil candidate name from OCR lines.

        Parameters
        ----------
        lines : list[str]

        Returns
        -------
        dict
        """

        result = {
            "found": False,
            "candidate_name": None,
            "line_number": None,
            "label": None
        }

        if not lines:
            return result

        total = len(lines)

        for i, line in enumerate(lines):

            line = line.strip()

            # Look for known labels
            matched_label = None

            for label in cls.NAME_LABELS:

                if label in line:
                    matched_label = label
                    break

            if matched_label is None:
                continue

            # Check current line and next 3 lines
            for j in range(i, min(i + 4, total)):

                candidate = cls.clean_name(lines[j])

                # Ignore label-only lines
                if (
                    candidate
                    and candidate not in cls.NAME_LABELS
                    and len(candidate) >= 3
                ):

                    result["found"] = True
                    result["candidate_name"] = candidate
                    result["line_number"] = j
                    result["label"] = matched_label

                    return result

        return result

    @classmethod
    def extract_from_text(cls, text):
        """
        Extract from a single OCR text block.
        """

        if not text:
            return {
                "found": False,
                "candidate_name": None
            }

        lines = [
            line.strip()
            for line in text.split("\n")
            if line.strip()
        ]

        # -----------------------------
        # Extract Tamil Name
        # -----------------------------

        tamil_result = TamilExtractor.extract(lines)

        tamil_name = tamil_result["candidate_name"]
        
        return cls.extract(lines)