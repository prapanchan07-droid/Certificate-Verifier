import cv2
import pytesseract
import numpy as np
import re
import os

# On Linux containers/servers, tesseract-ocr installed via apt is already
# on PATH, so pytesseract finds it automatically -- no override needed.
# On Windows dev machines it usually isn't, so allow pointing at it via
# an env var (falls back to the common default install path).
_tesseract_cmd = os.environ.get("TESSERACT_CMD")

if _tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = _tesseract_cmd
elif os.name == "nt":
    pytesseract.pytesseract.tesseract_cmd = (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )


class OCREngine:

    def _extract_total_marks(self, text_dump, lines):
        """Pull the total marks figure out of noisy OCR text.

        Tries, in order:
        1. A clean "TOTAL ... MARKS ... ddd" match (works when OCR read
           the label cleanly).
        2. Anchoring on the label line (English "TOTAL MARKS" or the
           Tamil "மொத்த", which survives OCR corruption better) and
           pulling a 3-digit number from right after it -- ignoring
           anything inside parentheses, since that's reliably noise
           like "(PASS)" or a garbled "(155)", never the real value.
        3. If no bare digits remain in that window, converting any
           spelled-out number words ("FOUR SEVEN NINE") into digits.
        """

        # 1) Clean case: label and number sit right next to each other.
        clean_match = re.search(
            r"TOTAL\s*MARKS\s*[:\-]?\s*(\d{3})",
            text_dump
        )

        if clean_match:
            return clean_match.group(1)

        # 2) Anchor on whichever label survived OCR.
        anchor_idx = None

        for i, line in enumerate(lines):

            if "மொத்த" in line or ("TOTAL" in line and "MARK" in line):
                anchor_idx = i
                break

        if anchor_idx is None:
            return None

        window = " ".join(lines[anchor_idx:anchor_idx + 2])

        # Skip past "MARKS" (and any colon after it) to avoid grabbing
        # digits that came from a garbled label before the real value.
        split_point = window.upper().find("MARKS")

        segment = window[split_point + 5:] if split_point != -1 else window

        if ":" in segment:
            segment = segment.split(":", 1)[1]

        segment_clean = re.sub(r"\([^)]*\)", " ", segment)

        digit_match = re.search(r"\b(\d{3})\b", segment_clean)

        if digit_match:
            return digit_match.group(1)

        # 3) No bare digits left -- try spelled-out words instead.
        words = {
            "ZERO": "0",
            "ONE": "1",
            "TWO": "2",
            "THREE": "3",
            "FOUR": "4",
            "FIVE": "5",
            "SIX": "6",
            "SEVEN": "7",
            "EIGHT": "8",
            "NINE": "9"
        }

        tokens = re.findall(r"[A-Z]+", segment_clean.upper())

        digit_tokens = [
            words[token]
            for token in tokens
            if token in words
        ]

        if len(digit_tokens) >= 3:
            return "".join(digit_tokens[:3])

        return None

    def extract_details(self, img_bytes):

        try:

            nparr = np.frombuffer(img_bytes, np.uint8)

            img = cv2.imdecode(
                nparr,
                cv2.IMREAD_COLOR
            )

            if img is None:
                return {
                    "candidate_name": None,
                    "roll_no": None,
                    "reg_no": None,
                    "total_marks": None,
                    "institution": None,
                    "raw_text": ""
                }

            gray = cv2.cvtColor(
                img,
                cv2.COLOR_BGR2GRAY
            )

            gray = cv2.GaussianBlur(
                gray,
                (3, 3),
                0
            )

            text_dump = pytesseract.image_to_string(
                gray,
                lang="eng+tam"
            )

            text_dump = text_dump.upper()
            
            text_dump = (
    text_dump
    .replace("௦", "0")
    .replace("௧", "1")
    .replace("௨", "2")
    .replace("௩", "3")
    .replace("௪", "4")
    .replace("௫", "5")
    .replace("௬", "6")
    .replace("௭", "7")
    .replace("௮", "8")
    .replace("௯", "9")
)
            
            lines = text_dump.split("\n")

            extracted = {
                "candidate_name": None,
                "roll_no": None,
                "reg_no": None,
                "total_marks": None,
                "institution": None,
                "raw_text": text_dump
            }

            roll_match = re.search(
                r"ROLL\s*NO.*?(\d{7})",
                text_dump,
                re.DOTALL
            )

            if roll_match:
                extracted["roll_no"] = roll_match.group(1)
            
            if not extracted["roll_no"]:
                roll_match = re.search(r"\b\d{7}\b", text_dump)

            reg_match = re.search(
                r"J\d{7}",
                text_dump
            )

            if reg_match:
                extracted["reg_no"] = reg_match.group(0)
            
            if not reg_match:
                reg_match = re.search(
                    r"\b[A-Z]{1,5}\d{5,}[A-Z0-9]*\b",
                    text_dump
                )

            # ==========================
            # TOTAL MARKS
            # ==========================
            #
            # Tesseract frequently mangles the English word "TOTAL" beyond
            # recognition (e.g. "TOTAL" -> "101&ட") while leaving the Tamil
            # label "மொத்த" (also meaning "total") intact, so we anchor on
            # whichever label survived. We also strip out anything inside
            # parentheses before grabbing digits, since on real certificates
            # the parenthesized text next to the total is noise like
            # "(PASS)" or an OCR-garbled "(155)" -- never the actual mark.
            # If no bare digits remain, we fall back to converting any
            # spelled-out number words ("FOUR SEVEN NINE") into digits.

            extracted["total_marks"] = self._extract_total_marks(
                text_dump,
                lines
            )

            # Candidate Name Extraction

            lines = text_dump.split("\n")

            name_match = re.search(
                r'([A-Z]+\s+[A-Z])\s+APR',
                text_dump
            )

            if name_match:
                extracted["candidate_name"] = name_match.group(1)
                
            school_keywords = [
                "SCHOOL",
                "COLLEGE",
                "HR SEC",
                "MATRIC",
                "INSTITUTION"
            ]

            for line in lines:

                if any(
                    word in line
                    for word in school_keywords
                ):
                    institution_line = line.strip()

                    # Strip stray leading digits/punctuation Tesseract
                    # sometimes prepends (e.g. "4 STATE BOARD OF ...")
                    institution_line = re.sub(
                        r'^\d+\s*',
                        '',
                        institution_line
                    )

                    # Strip stray trailing characters that aren't part of
                    # the English institution name (Tamil glyphs, stray
                    # punctuation) that Tesseract sometimes bleeds in from
                    # an adjacent line or column.
                    institution_line = re.sub(
                        r'[^A-Z0-9.,&()\-\s]+$',
                        '',
                        institution_line
                    ).strip()

                    extracted["institution"] = institution_line
                    break

            print("OCR FINAL RESULT")
            print(extracted)
            
            return extracted

        except Exception as e:

            return {
                "candidate_name": None,
                "roll_no": None,
                "reg_no": None,
                "total_marks": None,
                "institution": None,
                "raw_text": "",
                "error": str(e)
            }