from __future__ import annotations

from app.parsers.sslc_parser import SSLCParser
from app.parsers.hsc_parser import HSCParser
import cv2
import pytesseract
from pytesseract import Output
import numpy as np
import re
import os

_tesseract_cmd = os.environ.get("TESSERACT_CMD")
if _tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = _tesseract_cmd
elif os.name == "nt":
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Phrases we expect to see verbatim (or near enough) on a correctly-read
# certificate. Used only to SCORE how good an OCR pass was, never parsed
# directly -- the actual field extraction still happens in the parsers.
_ANCHOR_PHRASES = [
    "NAME OF", "DATE OF BIRTH", "PERMANENT REGISTER", "TOTAL MARKS",
    "ROLL NO", "SCHOOL", "GROUP CODE", "MEDIUM OF",
    "HIGHER SECONDARY", "SECONDARY SCHOOL LEAVING",
]

# Stop trying further OCR passes once a pass hits this many anchors --
# good enough that additional passes are very unlikely to help and would
# just cost time.
_GOOD_ENOUGH_HITS = 6


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

    # ------------------------------------------------------------------
    # Preprocessing
    # ------------------------------------------------------------------

    def _normalize_size(self, img: np.ndarray) -> np.ndarray:
        """Bring the image to a resolution Tesseract does well with.
        Downscale very large photos (keeps runtime sane); upscale small
        ones (phone photos taken from far away lose fine text detail
        that a bigger canvas + cubic interpolation can partially
        recover)."""
        h, w = img.shape[:2]
        target_h = 1400

        if h > target_h:
            scale = target_h / h
            img = cv2.resize(img, (int(w * scale), target_h),
                              interpolation=cv2.INTER_AREA)
            print(f"OCR: downscaled to {img.shape[1]}x{img.shape[0]}")
        elif h < 1000:
            scale = target_h / h
            img = cv2.resize(img, (int(w * scale), target_h),
                              interpolation=cv2.INTER_CUBIC)
            print(f"OCR: upscaled to {img.shape[1]}x{img.shape[0]}")

        return img

    def _prepare_variants(self, gray: np.ndarray):
        """Returns a small set of preprocessed variants of the same
        image, ordered roughly best-general-case-first. Each is tried
        with OCR and scored; see _score_text."""
        denoised = cv2.fastNlMeansDenoising(
            gray, None, h=10, templateWindowSize=7, searchWindowSize=21
        )

        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)

        thresholded = cv2.adaptiveThreshold(
            enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 31, 15,
        )

        return enhanced, thresholded

    # ------------------------------------------------------------------
    # OCR pass scoring / selection
    # ------------------------------------------------------------------

    def _score_text(self, text: str) -> tuple:
        """(anchor_hits, char_count) -- compared as a tuple, so a pass
        that found more structural anchors always wins regardless of
        raw character count; character count only breaks ties between
        passes with equal anchor coverage."""
        u = text.upper()
        hits = sum(1 for a in _ANCHOR_PHRASES if a in u)
        return (hits, len(text))

    def _best_ocr_pass(self, gray: np.ndarray):
        """Tries a short list of (image variant, psm) combinations,
        stopping early once one scores well enough. Returns
        (full_text, lines, psm_used) for the best-scoring pass tried.

        Passes are ordered cheapest/most-likely-to-work first:
          1. enhanced image, psm 6 (default block-of-text mode)
          2. enhanced image, psm 3 (full-page auto segmentation)
          3. thresholded image, psm 6 (binary fallback for low-contrast scans)
          4. enhanced image, psm 11 (sparse text, last resort)
        """
        enhanced, thresholded = self._prepare_variants(gray)

        attempts = [
            (enhanced, 6),
            (enhanced, 3),
            (thresholded, 6),
            (enhanced, 11),
        ]

        best_score = (-1, -1)
        best = None

        for image, psm in attempts:
            text = self._ocr(image, psm=psm).strip()
            score = self._score_text(text)
            print(f"OCR pass psm={psm} variant={'thresh' if image is thresholded else 'enhanced'} "
                  f"-> anchors={score[0]} chars={score[1]}")

            if score > best_score:
                best_score = score
                lines = [l for l in text.split("\n") if l.strip()]
                best = (text, lines, psm)

            if score[0] >= _GOOD_ENOUGH_HITS:
                break

        return best

    # ------------------------------------------------------------------
    # Targeted name-region retry
    # ------------------------------------------------------------------

    def _retry_candidate_name(self, gray: np.ndarray, parser) -> str | None:
        """Targeted re-OCR of just the name region, used when the
        full-page OCR pass never captured the English name text at all
        (a scan where every other field reads fine but the "NAME OF THE
        CANDIDATE" row came back Tamil-only, with no Latin name text
        anywhere in the full-page output -- no amount of string-parsing
        recovers text that was never recognized in the first place).
        Locates the word "CANDIDATE" via word-level bounding boxes,
        crops a band starting at that line and extending a few
        line-heights down, upscales it, and re-OCRs just that crop
        where there's far less surrounding noise to distract Tesseract.

        `parser` must expose extract_candidate_name(lines) -> str|None;
        if it doesn't, the retry is skipped. Returns the recovered name
        or None.
        """
        extract_fn = getattr(parser, "extract_candidate_name", None)
        if extract_fn is None:
            return None

        try:
            data = pytesseract.image_to_data(
                gray, lang="eng+tam", config="--psm 6", output_type=Output.DICT
            )
        except Exception as e:
            print("NAME RETRY: image_to_data failed:", e)
            return None

        anchor_top = None
        anchor_height = None
        for word, top, height in zip(data["text"], data["top"], data["height"]):
            if word.strip().upper().startswith("CANDIDAT"):
                anchor_top = top
                anchor_height = height
                break

        if anchor_top is None:
            print("NAME RETRY: 'CANDIDATE' anchor not found, skipping")
            return None

        h, w = gray.shape[:2]
        line_h = max(anchor_height, 20)
        y0 = max(0, anchor_top - line_h)
        y1 = min(h, anchor_top + line_h * 5)

        crop = gray[y0:y1, 0:w]
        if crop.size == 0:
            return None

        crop = cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        crop = cv2.GaussianBlur(crop, (3, 3), 0)

        retry_text = self._ocr(crop, psm=6)
        retry_lines = [l for l in retry_text.split("\n") if l.strip()]

        print("NAME RETRY LINES:", retry_lines)

        name = extract_fn(retry_lines)
        print("NAME RETRY:", "recovered ->", name if name else "still not found")
        return name

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def extract_details(self, img_bytes: bytes) -> dict:
        try:
            nparr = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                return self._empty(error="imdecode returned None")

            h, w = img.shape[:2]
            print(f"OCR input: {w}x{h}")

            img = self._normalize_size(img)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            full_text, lines_all, psm_used = self._best_ocr_pass(gray)
            print(f"OCR best pass: psm={psm_used}, {len(full_text)} chars, {len(lines_all)} lines")

            # Detect document type and call parser

            upper = full_text.upper()

            # Normalize common OCR mistakes
            upper = upper.replace("-", " ")
            upper = upper.replace(".", " ")
            upper = upper.replace("!", " ")
            upper = upper.replace("/", " ")

            upper = upper.replace("TOTALMARKS", "TOTAL MARKS")
            upper = upper.replace("REGISTERNUMBER", "REGISTER NUMBER")
            upper = upper.replace("PERMANENTREGISTER", "PERMANENT REGISTER")
            upper = upper.replace("MEDIUMOF", "MEDIUM OF")
            upper = upper.replace("GROUPCODE", "GROUP CODE")

            upper = re.sub(r"\s+", " ", upper)

            # ----------------------------
            # HSC Detection
            # ----------------------------

            if (
                "HIGHER SECONDARY" in upper
                and (
                    "FIRST YEAR" in upper
                    or "SECOND YEAR" in upper
                )
            ):
                print("Detected HSC Certificate")

                extracted = self.hsc_parser.parse(full_text, lines_all)
                active_parser = self.hsc_parser

            # ----------------------------
            # SSLC Detection
            # ----------------------------

            elif (
                "SECONDARY SCHOOL LEAVING" in upper
                or "SSLC" in upper
            ):
                print("Detected SSLC Certificate")

                extracted = self.sslc_parser.parse(full_text, lines_all)
                active_parser = self.sslc_parser

            # ----------------------------
            # Unknown
            # ----------------------------

            else:
                print("Unknown document")

                extracted = self._empty()
                extracted["raw_text"] = full_text
                active_parser = None

            # FIX #2 -- the full-page pass sometimes never captures the
            # English name text at all (see _retry_candidate_name
            # docstring). Previously this branch only logged and gave
            # up; _retry_candidate_name is a fully-built targeted
            # crop-and-re-OCR of just the name region but was never
            # actually invoked. Wire it in: attempt a targeted, higher-
            # quality crop of just that region before giving up on the
            # field, and use the recovered value if found.
            if (
                active_parser is not None
                and not extracted.get("candidate_name")
            ):
                retried_name = self._retry_candidate_name(gray, active_parser)
                if retried_name:
                    extracted["candidate_name"] = retried_name
                    print("Candidate name recovered via targeted retry:", retried_name)
                else:
                    print("Candidate name missing - retry attempted, still not found")

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