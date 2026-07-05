import cv2
import pytesseract
import numpy as np
import re
import os

_tesseract_cmd = os.environ.get("TESSERACT_CMD")
if _tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = _tesseract_cmd
elif os.name == "nt":
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

_SESSIONS = r"(APR|MAR|OCT|NOV|DEC|JAN|FEB)"

_BOARD_NOISE = [
    "STATE BOARD OF SCHOOL EXAMINATIONS",
    "DEPARTMENT OF GOVERNMENT EXAMINATIONS",
    "SECONDARY SCHOOL LEAVING CERTIFICATE",
    "HIGHER SECONDARY COURSE",
    "ISSUED UNDER THE AUTHORITY",
    "GOVERNMENT OF TAMILNADU",
    "GOVERNMENT OF TAMIL NADU",
    "PROVISIONAL CERTIFICATE",
    "X STANDARD",
]

_SCHOOL_KEYWORDS = [
    "GOVT", "GOVERNMENT", "HR SEC", "HIGH SCHOOL",
    "MATRICULATION", "AIDED", "SCHOOL", "COLLEGE",
    "GHSS", "GHNS", "MHSS",
]


def _is_english(text: str) -> bool:
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    return ascii_chars / max(len(text), 1) > 0.7


class OCREngine:

    def _normalize_tamil_digits(self, text):
        return (
            text
            .replace("௦", "0").replace("௧", "1").replace("௨", "2")
            .replace("௩", "3").replace("௪", "4").replace("௫", "5")
            .replace("௬", "6").replace("௭", "7").replace("௮", "8")
            .replace("௯", "9")
        )

    def _ocr(self, gray: np.ndarray, psm: int = 6) -> str:
        """Run Tesseract and return normalized uppercase text."""
        raw = pytesseract.image_to_string(
            gray, lang="eng+tam", config=f"--psm {psm}"
        )
        return self._normalize_tamil_digits(raw.upper())

    def _extract_roll_no(self, text_dump, lines):
        m = re.search(r"ROLL\s*NO\.?\s*[:\-]?\s*(\d{7})", text_dump)
        if m:
            return m.group(1)

        anchor = None
        for i, line in enumerate(lines):
            if "தேர்வெண்" in line or ("ROLL" in line and "NO" in line):
                anchor = i
                break
        if anchor is None:
            return None

        window = " ".join(lines[anchor:anchor + 2])
        dm = re.search(r"\b(\d{7})\b", window)
        if dm:
            return dm.group(1)

        confusions = {"O": "0", "Q": "0", "I": "1", "L": "1",
                      "S": "5", "B": "8", "G": "6", "Z": "2"}
        norm = "".join(confusions.get(c, c) for c in window.upper())
        dm = re.search(r"\b(\d{7})\b", norm)
        if dm:
            return dm.group(1)

        return None

    def _extract_total_marks(self, text_dump, lines):
        m = re.search(r"TOTAL\s*MARKS\s*[:\-]?\s*(\d{3,4})", text_dump)
        if m:
            return m.group(1)

        anchor = None
        for i, line in enumerate(lines):
            if "மொத்த" in line or ("TOTAL" in line and "MARK" in line):
                anchor = i
                break
        if anchor is None:
            return None

        window = " ".join(lines[anchor:anchor + 2])
        sp = window.upper().find("MARKS")
        segment = window[sp + 5:] if sp != -1 else window
        if ":" in segment:
            segment = segment.split(":", 1)[1]
        clean = re.sub(r"\([^)]*\)", " ", segment)

        dm = re.search(r"\b(\d{3,4})\b", clean)
        if dm:
            return dm.group(1)

        words = {"ZERO": "0", "ONE": "1", "TWO": "2", "THREE": "3",
                 "FOUR": "4", "FIVE": "5", "SIX": "6", "SEVEN": "7",
                 "EIGHT": "8", "NINE": "9"}
        tokens = re.findall(r"[A-Z]+", clean.upper())
        digits = [words[t] for t in tokens if t in words]
        if len(digits) >= 3:
            return "".join(digits[:4])
        return None

    def _extract_candidate_name(self, text_dump: str) -> str | None:
        """
        Extract candidate name.
        On TN certificates the name appears right after the
        'NAME OF THE CANDIDATE' label and before the session month.
        """
        # Pattern 1: between label and session token
        m = re.search(
            r'NAME OF THE CANDIDATE\s*[:\-]?\s*'
            r'([A-Z][A-Z\s\.]{2,50}?)'
            r'\s+' + _SESSIONS + r'\s+\d{4}',
            text_dump,
            re.DOTALL,
        )
        if m:
            name = m.group(1).strip()
            # Sanity: reject if it contains sentence-like words
            if not re.search(r'\b(THE|AND|OF|FOR|IN|TO|WITH|IS|ARE|WAS)\b', name):
                return name

        # Pattern 2: immediately after label on the same/next line
        m = re.search(
            r'NAME OF THE CANDIDATE\s*[:\-]?\s*\n*\s*'
            r'([A-Z][A-Z\s\.]{4,40})',
            text_dump,
        )
        if m:
            name = m.group(1).strip().split('\n')[0].strip()
            if not re.search(r'\b(THE|AND|OF|FOR|IN|TO|WITH|IS|ARE|WAS)\b', name):
                return name

        # Pattern 3: Tamil label followed by name
        m = re.search(
            r'தேர்வரின்\s+பெயர்[^\n]*\n\s*([A-Z][A-Z\s\.]{4,40})',
            text_dump,
        )
        if m:
            return m.group(1).strip().split('\n')[0].strip()

        return None

    def _extract_institution(self, lines: list) -> str | None:
        # Strategy 1: anchor on NAME OF THE SCHOOL
        for i, line in enumerate(lines):
            if "NAME OF THE SCHOOL" in line or "பள்ளியின் பெயர்" in line:
                for j in range(i + 1, min(i + 5, len(lines))):
                    candidate = lines[j].strip()
                    candidate = re.sub(r"^\d+\s*", "", candidate)
                    candidate = re.sub(r"[^A-Z0-9.,&()\-\s]+$", "", candidate).strip()
                    if (
                        len(candidate) > 5
                        and _is_english(candidate)
                        and not any(noise in candidate for noise in _BOARD_NOISE)
                        and any(kw in candidate for kw in _SCHOOL_KEYWORDS)
                    ):
                        return candidate
                break

        # Strategy 2: scan all lines
        for line in lines:
            upper = line.strip().upper()
            if not _is_english(upper):
                continue
            if not any(kw in upper for kw in _SCHOOL_KEYWORDS):
                continue
            if any(noise in upper for noise in _BOARD_NOISE):
                continue
            cleaned = re.sub(r"^\d+\s*", "", upper).strip()
            if len(cleaned) > 8:
                return cleaned

        return None

    def extract_details(self, img_bytes: bytes) -> dict:
        try:
            nparr = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                return self._empty(error="imdecode returned None")

            h, w = img.shape[:2]

            # -------------------------------------------------------
            # Downscale for speed: cap longest side at 1800px
            # -------------------------------------------------------
            max_side = 1800
            scale = min(max_side / max(h, w), 1.0)
            if scale < 1.0:
                img = cv2.resize(img, (int(w * scale), int(h * scale)),
                                 interpolation=cv2.INTER_AREA)
                h, w = img.shape[:2]
                print(f"OCR: downscaled to {w}×{h}")

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # -------------------------------------------------------
            # Region-based OCR for speed + accuracy
            # Top 45% of page → name, roll, reg (header zone)
            # Bottom 60% of page → marks, school (data zone)
            # Full page → fallback
            # -------------------------------------------------------
            top = gray[0:int(h * 0.45), :]
            bottom = gray[int(h * 0.40):, :]

            top_text = self._ocr(top, psm=6)
            bottom_text = self._ocr(bottom, psm=6)
            full_text = top_text + "\n" + bottom_text

            print(f"OCR top: {len(top_text)} chars | bottom: {len(bottom_text)} chars")

            lines_top = [l for l in top_text.split("\n") if l.strip()]
            lines_bottom = [l for l in bottom_text.split("\n") if l.strip()]
            lines_all = lines_top + lines_bottom

            extracted = {
                "candidate_name": None,
                "roll_no": None,
                "reg_no": None,
                "total_marks": None,
                "institution": None,
                "raw_text": full_text,
            }

            # ---------- CANDIDATE NAME (top region) ----------
            extracted["candidate_name"] = self._extract_candidate_name(top_text)

            # ---------- ROLL NUMBER (top region) ----------
            extracted["roll_no"] = self._extract_roll_no(top_text, lines_top)
            if not extracted["roll_no"]:
                m = re.search(r"\b\d{7}\b", top_text)
                if m:
                    extracted["roll_no"] = m.group(0)
            # fallback: full page
            if not extracted["roll_no"]:
                extracted["roll_no"] = self._extract_roll_no(full_text, lines_all)
            if not extracted["roll_no"]:
                m = re.search(r"\b\d{7}\b", full_text)
                if m:
                    extracted["roll_no"] = m.group(0)

            # ---------- REGISTER NUMBER (bottom region) ----------
            for text in (bottom_text, full_text):
                m = re.search(r"\bJ\d{7}\b", text)
                if m:
                    extracted["reg_no"] = m.group(0)
                    break
            if not extracted["reg_no"]:
                for text in (bottom_text, full_text):
                    m = re.search(r"\b\d{10}\b", text)
                    if m:
                        extracted["reg_no"] = m.group(0)
                        break
            if not extracted["reg_no"]:
                m = re.search(r"\b[A-Z]{1,3}\d{5,}\b", full_text)
                if m:
                    extracted["reg_no"] = m.group(0)

            # ---------- TOTAL MARKS (bottom region) ----------
            extracted["total_marks"] = self._extract_total_marks(
                bottom_text, lines_bottom
            )
            if not extracted["total_marks"]:
                extracted["total_marks"] = self._extract_total_marks(
                    full_text, lines_all
                )

            # ---------- INSTITUTION (bottom region) ----------
            extracted["institution"] = self._extract_institution(lines_bottom)
            if not extracted["institution"]:
                extracted["institution"] = self._extract_institution(lines_all)

            print("OCR FINAL:", extracted)
            return extracted

        except Exception as e:
            import traceback
            traceback.print_exc()
            return self._empty(error=str(e))

    @staticmethod
    def _empty(error: str = None) -> dict:
        return {
            "candidate_name": None,
            "roll_no": None,
            "reg_no": None,
            "total_marks": None,
            "institution": None,
            "raw_text": "",
            **({"error": error} if error else {}),
        }
