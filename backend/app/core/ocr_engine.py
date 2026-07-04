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


class OCREngine:

    def _normalize_tamil_digits(self, text):
        return (
            text
            .replace("௦", "0").replace("௧", "1").replace("௨", "2")
            .replace("௩", "3").replace("௪", "4").replace("௫", "5")
            .replace("௬", "6").replace("௭", "7").replace("௮", "8")
            .replace("௯", "9")
        )

    def _crop_roll_no_region(self, gray):
        try:
            data = pytesseract.image_to_data(
                gray, lang="eng+tam", output_type=pytesseract.Output.DICT
            )
        except Exception as e:
            print(f"ROLL CROP: image_to_data failed: {e}")
            return None

        n = len(data.get("text", []))
        label_box = None
        for i in range(n):
            word = data["text"][i].strip().upper()
            if word in ("ROLL", "தேர்வெண்"):
                label_box = (data["left"][i], data["top"][i],
                             data["width"][i], data["height"][i])
                break

        if label_box is None:
            return None

        x, y, w, h = label_box
        img_h, img_w = gray.shape[:2]
        if w == 0 or h == 0:
            return None

        crop_x1 = max(0, x - 2 * w)
        crop_y1 = max(0, y)
        crop_x2 = min(img_w, x + 10 * w)
        crop_y2 = min(img_h, y + 10 * h)
        crop = gray[crop_y1:crop_y2, crop_x1:crop_x2]
        if crop.size == 0:
            return None

        crop_up = cv2.resize(crop, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
        thresh = cv2.threshold(crop_up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        raw = pytesseract.image_to_string(
            thresh, config="--psm 6 -c tessedit_char_whitelist=0123456789"
        ).strip()
        m = re.search(r"\b\d{7}\b", raw)
        return m.group(0) if m else None

    def _extract_roll_no(self, text_dump, lines):
        # 1) Clean
        m = re.search(r"ROLL\s*NO\.?\s*[:\-]?\s*(\d{7})", text_dump)
        if m:
            return m.group(1)

        # 2) Anchor
        anchor = None
        for i, line in enumerate(lines):
            if "தேர்வெண்" in line or ("ROLL" in line and "NO" in line):
                anchor = i
                break
        if anchor is None:
            return None

        window = " ".join(lines[anchor:anchor + 2])
        sp = window.upper().find("NO.")
        if sp == -1:
            sp = window.upper().find("ROLL")
        segment = window[sp:] if sp != -1 else window

        dm = re.search(r"\b(\d{7})\b", segment)
        if dm:
            return dm.group(1)

        # confusion normalise
        confusions = {"O": "0", "Q": "0", "I": "1", "L": "1",
                      "S": "5", "B": "8", "G": "6", "Z": "2"}
        norm = "".join(confusions.get(c, c) for c in segment.upper())
        dm = re.search(r"\b(\d{7})\b", norm)
        if dm:
            return dm.group(1)

        # 3) Spelled-out digits
        words = {"ZERO": "0", "ONE": "1", "TWO": "2", "THREE": "3", "FOUR": "4",
                 "FIVE": "5", "SIX": "6", "SEVEN": "7", "EIGHT": "8", "NINE": "9"}
        tokens = re.findall(r"[A-Z]+", segment.upper())
        digits = [words[t] for t in tokens if t in words]
        if len(digits) >= 7:
            return "".join(digits[:7])
        return None

    def _extract_total_marks(self, text_dump, lines):
        # 1) Clean
        m = re.search(r"TOTAL\s*MARKS\s*[:\-]?\s*(\d{3,4})", text_dump)
        if m:
            return m.group(1)

        # 2) Anchor
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

        words = {"ZERO": "0", "ONE": "1", "TWO": "2", "THREE": "3", "FOUR": "4",
                 "FIVE": "5", "SIX": "6", "SEVEN": "7", "EIGHT": "8", "NINE": "9"}
        tokens = re.findall(r"[A-Z]+", clean.upper())
        digits = [words[t] for t in tokens if t in words]
        if len(digits) >= 3:
            return "".join(digits[:4])
        return None

    def _extract_candidate_name(self, text_dump):
        """Extract name for both SSLC (APR) and HSC (MAR) sessions."""
        # Pattern: <NAME> <SESSION_MONTH> <YEAR>
        m = re.search(
            r'NAME OF THE CANDIDATE\s+([A-Z][A-Z\s]{2,40}?)\s+' + _SESSIONS + r'\s+\d{4}',
            text_dump,
            re.DOTALL,
        )
        if m:
            return m.group(1).strip()

        # Fallback: any multi-word name just before session token
        m = re.search(r'([A-Z]{2,}(?:\s+[A-Z]{1,}){1,3})\s+' + _SESSIONS, text_dump)
        if m:
            return m.group(1).strip()
        return None

    def extract_details(self, img_bytes: bytes) -> dict:
        try:
            nparr = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                return self._empty(error="imdecode returned None")

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (3, 3), 0)

            text_dump = pytesseract.image_to_string(gray, lang="eng+tam")
            text_dump = self._normalize_tamil_digits(text_dump.upper())
            lines = text_dump.split("\n")

            extracted = {
                "candidate_name": None,
                "roll_no": None,
                "reg_no": None,
                "total_marks": None,
                "institution": None,
                "raw_text": text_dump,
            }

            # ---------- ROLL NUMBER ----------
            extracted["roll_no"] = self._extract_roll_no(text_dump, lines)

            if not extracted["roll_no"]:
                m = re.search(r"\b\d{7}\b", text_dump)
                if m:
                    extracted["roll_no"] = m.group(0)

            if not extracted["roll_no"]:
                for psm in ("--psm 6", "--psm 4", "--psm 11"):
                    rt = self._normalize_tamil_digits(
                        pytesseract.image_to_string(gray, lang="eng+tam", config=psm).upper()
                    )
                    rl = rt.split("\n")
                    roll = self._extract_roll_no(rt, rl)
                    if not roll:
                        m = re.search(r"\b\d{7}\b", rt)
                        if m:
                            roll = m.group(0)
                    if roll:
                        extracted["roll_no"] = roll
                        break

            if not extracted["roll_no"]:
                extracted["roll_no"] = self._crop_roll_no_region(gray)

            # ---------- REGISTER NUMBER ----------
            # SSLC: J3040362   HSC permanent reg: 2414284179 (10 digits)   HSC TMR: A2253054
            m = re.search(r"\bJ\d{7}\b", text_dump)
            if m:
                extracted["reg_no"] = m.group(0)

            if not extracted["reg_no"]:
                m = re.search(r"\b\d{10}\b", text_dump)
                if m:
                    extracted["reg_no"] = m.group(0)

            if not extracted["reg_no"]:
                m = re.search(r"\b[A-Z]{1,3}\d{5,}\b", text_dump)
                if m:
                    extracted["reg_no"] = m.group(0)

            # ---------- TOTAL MARKS ----------
            extracted["total_marks"] = self._extract_total_marks(text_dump, lines)

            # ---------- CANDIDATE NAME ----------
            extracted["candidate_name"] = self._extract_candidate_name(text_dump)

            # ---------- INSTITUTION ----------
            keywords = ["SCHOOL", "COLLEGE", "HR SEC", "MATRIC", "INSTITUTION"]
            for line in lines:
                if any(kw in line for kw in keywords):
                    inst = re.sub(r"^\d+\s*", "", line.strip())
                    inst = re.sub(r"[^A-Z0-9.,&()\-\s]+$", "", inst).strip()
                    if inst:
                        extracted["institution"] = inst
                        break

            print("OCR FINAL:", extracted)
            return extracted

        except Exception as e:
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
