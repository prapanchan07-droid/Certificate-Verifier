from __future__ import annotations

import cv2
from matplotlib import lines
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

_SENTENCE_WORDS = re.compile(
    r'\b(THE|AND|OF|FOR|IN|TO|WITH|IS|ARE|WAS|OBTAINED|FOLLOWING'
    r'|CERTIFIED|APPEARED|MARKS|SUBJECT|PRACTICAL|THEORY|PASS|FAIL'
    r'|ABOVE|MENTIONED|SECONDARY|LEAVING|CERTIFICATE|PUBLIC|EXAMINATION'
    r'|ISSUED|UNDER|AUTHORITY|DEPARTMENT|GOVERNMENT|TAMILNADU)\b'
)


def _is_english(text: str) -> bool:
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    return ascii_chars / max(len(text), 1) > 0.7


def _looks_like_name(text: str) -> bool:
    text = text.strip()
    if len(text) < 3 or len(text) > 60:
        return False
    if not _is_english(text):
        return False
    if _SENTENCE_WORDS.search(text):
        return False
    if not re.match(r'^[A-Z][A-Z\s\.]+$', text):
        return False
    words = [w for w in text.split() if w]
    if len(words) < 2:
        return False
    if any(len(w) > 20 for w in words):
        return False
    return True


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
        raw = pytesseract.image_to_string(
            gray, lang="eng+tam", config=f"--psm {psm}"
        )
        return self._normalize_tamil_digits(raw.upper())

    def _extract_roll_no(self, text_dump: str, lines: list) -> str | None:
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

        window = " ".join(lines[anchor:anchor + 3])
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

    def _extract_reg_no(self, text_dump: str) -> str | None:
        # Priority 1: J-prefix SSLC e.g. J3040362
        m = re.search(r"\bJ\d{7}\b", text_dump)
        if m:
            return m.group(0)

        # Priority 2: XM23R... style permanent reg
        m = re.search(r"\b[A-Z]{2,4}\d{2}[A-Z]\d{7,}\b", text_dump)
        if m:
            return m.group(0)

        # Priority 3: 10-digit permanent reg — skip EMIS IDs (start with 1012)
        for match in re.finditer(r"\b(\d{10})\b", text_dump):
            val = match.group(1)
            if not val.startswith("1012"):
                return val

        # Priority 4: alpha+digit e.g. A2253054
        m = re.search(r"\b[A-Z]{1,3}\d{5,9}\b", text_dump)
        if m:
            return m.group(0)

        return None

    def _extract_total_marks(self, text_dump: str, lines: list) -> str | None:
        m = re.search(r"TOTAL\s*MARKS\s*[:\-]?\s*(\d{3,4})", text_dump)
        if m:
            return m.group(1)

        anchor = None
        for i, line in enumerate(lines):
            if "மொத்த" in line or ("TOTAL" in line and "MARK" in line):
                anchor = i
                break

        if anchor is not None:
            window = " ".join(lines[anchor:anchor + 3])
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

        # Fallback: the TOTAL MARKS row is the only mark line trailed by
        # the word "PASS" -- subject rows are trailed by the shorter
        # "(P)" instead. This survives even when OCR mangles the "TOTAL
        # MARKS" label itself (confirmed case: "TOTAL" misread as
        # "TOTAR" merged into "MARKS" with no space, breaking the
        # anchor search above).
        for dm in re.finditer(r"\b(\d{3,4})\b", text_dump):
            tail = text_dump[dm.end():dm.end() + 40].upper()
            if "PASS" in tail or "ASS)" in tail or "ASS " in tail:
                return dm.group(1)

        return None

    def _extract_candidate_name(self, text_dump: str, lines: list) -> str | None:
        """
        From the logs, the OCR produces this exact line:
            'ல MUTHU KRISHNAN N APR 2023'
        So the name and session are on the SAME line with garbage prefix.
        Pattern: strip garbage → extract name before session token.
        """

        session_re = re.compile(_SESSIONS + r'\s+\d{4}')
        for line in lines:
            if session_re.search(line):
                # Strip everything before the first capital English letter
                cleaned = re.sub(r'^[^A-Z]+', '', line.strip())
                # Keep ONLY text before the session token. Anything after
                # it (e.g. a trailing "P" or "FY") is watermark/border
                # bleed-through on this template, confirmed by direct
                # inspection of raw OCR output -- not part of the name.
                m2 = session_re.search(cleaned)
                name_part = cleaned[:m2.start()].strip() if m2 else cleaned
                name_part = re.sub(r'[^A-Z\s\.]', '', name_part).strip()
                if _looks_like_name(name_part):
                    print(f"NAME P1 (same line): {name_part}")
                    return name_part

        # Pattern 2: directly after NAME OF THE CANDIDATE label
        for i, line in enumerate(lines):
            if "NAME OF THE CANDIDATE" in line:
                after = re.sub(r'.*NAME OF THE CANDIDATE\s*[:\-/|]?\s*', '',
                               line).strip()
                after = re.sub(r'^[^A-Z]+', '', after).strip()
                after = session_re.sub('', after).strip()
                after = re.sub(r'[^A-Z\s\.]', '', after).strip()
                if _looks_like_name(after):
                    print(f"NAME P2a: {after}")
                    return after
                # Check next lines
                for j in range(i + 1, min(i + 5, len(lines))):
                    candidate = re.sub(r'^[^A-Z]+', '', lines[j].strip())
                    candidate = session_re.sub('', candidate).strip()
                    candidate = re.sub(r'[^A-Z\s\.]', '', candidate).strip()
                    if _looks_like_name(candidate):
                        print(f"NAME P2b: {candidate}")
                        return candidate
                break

        # Pattern 3: scan all lines for name near session context
        for i, line in enumerate(lines):
            stripped = re.sub(r'^[^A-Z]+', '', line.strip())
            if not stripped:
                continue
            # Skip lines with digits
            if re.search(r'\d', stripped):
                continue
            if _looks_like_name(stripped):
                prev = lines[i - 1].strip() if i > 0 else ""
                nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
                context = prev + " " + nxt
                if re.search(_SESSIONS, context) or "CANDIDATE" in context \
                        or "பெயர்" in context or "பருவம்" in context:
                    print(f"NAME P3: {stripped}")
                    return stripped

        return None

    def _extract_institution(self, lines: list) -> str | None:

        def _clean(s):
            # Strip ALL leading non-alpha-numeric garbage including digits+space
            s = re.sub(r'^[\W\d_]+', '', s.strip())
            # Strip trailing non-alphanumeric garbage
            s = re.sub(r'[\W]+$', '', s).strip()
            # Remove OCR artifacts like backslash, quotes
            s = re.sub(r"[\\'\"`]+", "", s).strip()
            return s

        # Strategy 1: anchor on NAME OF THE SCHOOL
        for i, line in enumerate(lines):
            if "NAME OF THE SCHOOL" in line or "பள்ளியின் பெயர்" in line:
                for j in range(i + 1, min(i + 5, len(lines))):
                    candidate = _clean(lines[j])
                    if (
                        len(candidate) > 5
                        and _is_english(candidate)
                        and not any(noise in candidate for noise in _BOARD_NOISE)
                        and any(kw in candidate for kw in _SCHOOL_KEYWORDS)
                    ):
                        return candidate
                break

        # Strategy 2: scan lines for English school name
        for line in lines:
            upper = _clean(line.upper())
            if not _is_english(upper):
                continue
            if not any(kw in upper for kw in _SCHOOL_KEYWORDS):
                continue
            if any(noise in upper for noise in _BOARD_NOISE):
                continue
            if len(upper) > 8:
                return upper

        return None
    def extract_details(self, img_bytes: bytes) -> dict:
        try:
            nparr = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                return self._empty(error="imdecode returned None")

            h, w = img.shape[:2]
            print(f"OCR input: {w}x{h}")

            max_h = 1400
            if h > max_h:
                scale = max_h / h
                img = cv2.resize(img, (int(w * scale), max_h),
                                 interpolation=cv2.INTER_AREA)
                h, w = img.shape[:2]
                print(f"OCR: resized to {w}x{h}")

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            full_text = self._ocr(gray, psm=6)
            full_text = full_text.strip()
            lines_all = [l for l in full_text.split("\n") if l.strip()]

            print(f"OCR full: {len(full_text)} chars, {len(lines_all)} lines")

            if len(full_text) < 100:
                print("OCR: retrying with PSM 3")
                full_text = self._ocr(gray, psm=3)
                lines_all = [l for l in full_text.split("\n") if l.strip()]

            extracted = {
                "candidate_name": None,
                "roll_no": None,
                "reg_no": None,
                "total_marks": None,
                "institution": None,
                "raw_text": full_text,
            }

            extracted["candidate_name"] = self._extract_candidate_name(
                full_text, lines_all
            )

            extracted["roll_no"] = self._extract_roll_no(full_text, lines_all)
            if not extracted["roll_no"]:
                m = re.search(r"\b\d{7}\b", full_text)
                if m:
                    extracted["roll_no"] = m.group(0)

            # Use dedicated method — correctly skips EMIS IDs
            extracted["reg_no"] = self._extract_reg_no(full_text)

            extracted["total_marks"] = self._extract_total_marks(
                full_text, lines_all
            )

            mid = len(lines_all) // 2
            extracted["institution"] = self._extract_institution(
                lines_all[mid:]
            )
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