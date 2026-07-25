from __future__ import annotations

from app.parsers.sslc_parser import SSLCParser
from app.parsers.hsc_parser import HSCParser
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

class OCREngine:

    def __init__(self):

        self.sslc_parser = SSLCParser()

        self.hsc_parser = HSCParser()
        
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

            upper = full_text.upper()

            # Detect document type and call parser

            if "SECONDARY SCHOOL LEAVING CERTIFICATE" in upper:

                print("Detected SSLC Certificate")

                extracted = self.sslc_parser.parse(
                    full_text,
                    lines_all
                )

            elif "HIGHER SECONDARY COURSE" in upper:

                print("Detected HSC Certificate")

                extracted = self.hsc_parser.parse(
                    full_text,
                    lines_all
                )

            else:

                print("Unknown document")

                extracted = self._empty()
                extracted["raw_text"] = full_text

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