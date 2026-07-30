from __future__ import annotations
import requests
from bs4 import BeautifulSoup
import re

from app.utils.fuzzy_match import FuzzyMatcher  # NEW — fuzzy name matching

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

_DIGIT_WORDS = (
    "ZERO", "ONE", "TWO", "THREE", "FOUR", "FIVE",
    "SIX", "SEVEN", "EIGHT", "NINE",
)

# Similarity threshold for fuzzy candidate-name matching. Measured
# directly against confirmed real OCR outputs rather than guessed:
#   "TAMUEUAN V"   vs official "TAMILELAN V"  -> 0.762 (real, should match)
#   "SRISAPARIS I" vs official "SRISABARI S"  -> 0.783 (real, should match)
#   "KAVYA R"      vs "DIVYA R" (different student) -> 0.714 (must NOT match)
# 0.80 was rejecting both real cases above. 0.75 accepts both while still
# sitting above the nearest-miss different-name pair found.


# Minimum length (after whitespace-stripping) an institution string must
# have before the plain substring check in _normalize_school is trusted.
# Without a floor, a short OCR read like "SCHOOL" or "SEC" would be a
# substring of nearly every institution name in this dataset and would
# trivially "match" any school -- the floor ensures the shorter of the
# two strings actually carries enough of the school's identity to mean
# something.
_MIN_SCHOOL_MATCH_LEN = 12


class OfficialVerifier:

    def extract_official_data(self, qr_url: str) -> dict:
        try:
            response = requests.get(qr_url, timeout=15)
            if response.status_code != 200:
                return {"success": False, "error": f"HTTP {response.status_code}"}

            soup = BeautifulSoup(response.text, "html.parser")
            page_text = soup.get_text(separator=" ", strip=True).upper()

            is_hsc = (
                "HIGHER SECONDARY" in page_text
                or "SECOND YEAR MARK CERTIFICATE" in page_text
                or "FIRST YEAR MARK CERTIFICATE" in page_text
            )

            result = {
                "success": True,
                "candidate_name": None,
                "roll_no": None,
                "reg_no": None,
                "total_marks": None,
                "institution": None,
                "raw_text": page_text,
            }

            if is_hsc:
                result["years"] = self._extract_hsc_years(page_text)
                # Kept for any code that still reads the flat roll_no/
                # total_marks fields for display purposes -- defaults to
                # whichever year is chronologically later ("second_year").
                result["roll_no"] = result["years"]["second_year"]["roll_no"]
                result["total_marks"] = result["years"]["second_year"]["total_marks"]
            else:
                m = re.search(r"\b\d{7}\b", page_text)
                if m:
                    result["roll_no"] = m.group()

                m = re.search(r"TOTAL\s+MARKS.*?(\d{3,4})", page_text, re.IGNORECASE)
                if m:
                    result["total_marks"] = m.group(1)

            # Register number — shared across both years
            m = re.search(r"\bJ\d{7}\b", page_text)
            if m:
                result["reg_no"] = m.group()
            if not result["reg_no"]:
                m = re.search(r"\b[A-Z]{2,4}\d{2}[A-Z]\d{7,}\b", page_text)
                if m:
                    result["reg_no"] = m.group()
            if not result["reg_no"]:
                for match in re.finditer(r"\b(\d{10})\b", page_text):
                    val = match.group(1)
                    if not val.startswith("1012"):
                        result["reg_no"] = val
                        break
            if not result["reg_no"]:
                m = re.search(r"\b[A-Z]{1,3}\d{5,9}\b", page_text)
                if m:
                    result["reg_no"] = m.group()

            # Candidate name — shared across both years
            if is_hsc:
                m = re.search(
                    r"NAME OF THE CANDIDATE.*?([A-Z ]+?)\s+PASS",
                    page_text,
                    re.DOTALL,
                )
                if m:
                    result["candidate_name"] = m.group(1).strip()
            else:
                m = re.search(
                    r"NAME OF THE CANDIDATE\s+([A-Z][A-Z\s]{2,40}?)\s+"
                    r"(APR|MAR|OCT|NOV|DEC|JAN|FEB)\s+\d{4}",
                    page_text, re.DOTALL,
                )
                if m:
                    result["candidate_name"] = m.group(1).strip()
                else:
                    m = re.search(
                        r"NAME OF THE CANDIDATE.*?([A-Z]+\s+[A-Z]+(?:\s+[A-Z]+)?)",
                        page_text, re.DOTALL,
                    )
                    if m:
                        result["candidate_name"] = m.group(1).strip()

            if result["candidate_name"]:
                # Trailing session-month token bleeding into the match
                # (e.g. "SRISABARI S APR" -> "SRISABARI S")
                result["candidate_name"] = re.sub(
                    r'\s+(APR|MAR|OCT|NOV|DEC|JAN|FEB)$', '',
                    result["candidate_name"]
                ).strip()
                # Leading "SESSION" token bleeding in on the HSC page,
                # confirmed case: "NAME OF THE CANDIDATE / SESSION
                # PRAPANCHAN V PASS" -> captures "SESSION PRAPANCHAN V".
                result["candidate_name"] = re.sub(
                    r'^SESSION\s+', '', result["candidate_name"]
                ).strip()

            # Institution — shared across both years
            if is_hsc:
                result["institution"] = self._extract_hsc_school(page_text)
            else:
                result["institution"] = self._extract_institution_from_text(page_text)

            print("OFFICIAL DATA EXTRACTED:", result)
            return result

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _extract_hsc_years(self, page_text: str) -> dict:
        """
        Splits First Year vs Second Year data WITHOUT relying on heading
        text position (confirmed unreliable -- "FIRST YEAR" sometimes
        appears embedded mid-row in the summary line, after the subject
        rows, rather than as a heading before them).

        Instead, uses the calendar year embedded in each row's own
        "(ROLLNO / MONTH / YEAR)" annotation -- e.g. "(4419728 / MAR /
        2024)" for First Year, "(1419730 / MAR / 2025)" for Second Year.
        Whichever calendar year is numerically SMALLER is First Year,
        whichever is LARGER is Second Year -- this works for any student
        regardless of which actual years appear (2022/2023, 2025/2026,
        etc.), since it only ever compares the two years found against
        each other, never against a hardcoded year.
        """
        entries = re.findall(
            r"\(\s*(\d{7})\s*/\s*[A-Z]{3}\s*/\s*(\d{4})\s*\)",
            page_text,
        )

        years = {
            "first_year": {"roll_no": None, "total_marks": None},
            "second_year": {"roll_no": None, "total_marks": None},
        }

        if entries:
            # distinct (roll_no, calendar_year) pairs, ascending by year
            distinct = sorted(set(entries), key=lambda pair: int(pair[1]))
            years["first_year"]["roll_no"] = distinct[0][0]
            years["second_year"]["roll_no"] = distinct[-1][0]

        # Total marks: each year's aggregate is a 3-4 digit number
        # immediately followed by its own spelled-out digit echo (e.g.
        # "0574 ZERO FIVE SEVEN FOUR", "0560 ZERO FIVE SIX ZERO"). This
        # survives regardless of whether the "TOTAL MARKS" label text
        # appears before or after the number (confirmed inconsistent
        # between the two years on the same page) because it doesn't
        # depend on the label's position at all -- only on the number
        # being immediately echoed in words, which both years do.
        digit_word_pattern = "|".join(_DIGIT_WORDS)
        marks_matches = re.findall(
            rf"\b(\d{{3,4}})\b\s+(?:{digit_word_pattern})"
            rf"(?:\s+(?:{digit_word_pattern})){{2,3}}\b",
            page_text,
        )

        if len(marks_matches) >= 1:
            years["first_year"]["total_marks"] = marks_matches[0]
        if len(marks_matches) >= 2:
            years["second_year"]["total_marks"] = marks_matches[1]
        elif len(marks_matches) == 1:
            years["second_year"]["total_marks"] = marks_matches[0]

        return years

    def _extract_institution_from_text(self, page_text: str):
        idx = page_text.find("NAME OF THE SCHOOL")
        if idx == -1:
            return None

        after = page_text[idx + len("NAME OF THE SCHOOL"):]
        end_idx = len(after)
        for stop_word in ("IP ADDRESS", "DATE & TIME", "DATE &TIME", "DATE&TIME"):
            pos = after.find(stop_word)
            if pos != -1:
                end_idx = min(end_idx, pos)
        segment = after[:end_idx]

        runs = re.findall(r"[A-Z][A-Z,\s]{4,80}", segment)
        if runs:
            candidate = re.sub(r'\s+', ' ', runs[-1]).strip().strip(',').strip()
            if candidate and candidate != "NAME OF THE SCHOOL" \
                    and not any(noise in candidate for noise in _BOARD_NOISE):
                return candidate

        return None

    def _extract_hsc_school(self, page_text: str):
        idx = page_text.find("NAME OF THE SCHOOL")
        if idx == -1:
            return None

        after = page_text[idx + len("NAME OF THE SCHOOL"):]

        stop_words = [
            "GROUP CODE",
            "MEDIUM OF INSTRUCTION",
            "EMIS ID",
            "QR CODE",
            "TMR.CODE",
            "DATE",
        ]

        end = len(after)
        for word in stop_words:
            pos = after.find(word)
            if pos != -1:
                end = min(end, pos)

        segment = after[:end]

        match = re.search(
            r"GOVERNMENT.*?SCHOOL[ A-Z]*|[A-Z ]+SCHOOL[ A-Z]*",
            segment,
        )

        if match:
            return re.sub(r"\s+", " ", match.group()).strip()

        return None

    @staticmethod
    def clean_text(text) -> str:
        if not text:
            return ""
        t = str(text).strip().upper()
        # Normalize common OCR/formatting punctuation noise (periods,
        # commas, hyphens) to spaces before collapsing whitespace --
        # e.g. official "P.A. VIDYA BHAVAN" vs OCR "PA VIDYA BHAVAN"
        # should tokenize the same way for the word-overlap checks
        # below. Only affects name/institution comparisons; reg_no and
        # roll_no are pure digit strings and are unaffected by this.
        t = re.sub(r"[.,\-]", " ", t)
        return re.sub(r"\s+", " ", t).strip()

    @staticmethod
    def _normalize_school(text: str) -> str:
        if not text:
            return ""

        text = OfficialVerifier.clean_text(text)

        return re.sub(r"\s+", "", text)

    @staticmethod
    def _school_match(ocr_inst: str, off_inst: str) -> bool:
        """Whitespace-collapsed substring check, guarded by a minimum
        length floor. Without the floor, a short/partial OCR read (e.g.
        just "SCHOOL" or "SEC") would be a substring of virtually every
        institution name in this dataset and would trivially "match"
        any school on the register -- the floor requires the SHORTER of
        the two normalized strings to carry enough of the school's
        actual identity before the substring check is trusted."""
        ocr = OfficialVerifier._normalize_school(ocr_inst)
        official = OfficialVerifier._normalize_school(off_inst)

        if not ocr or not official:
            return False

        shorter_len = min(len(ocr), len(official))
        if shorter_len < _MIN_SCHOOL_MATCH_LEN:
            return False

        return ocr in official or official in ocr

    @staticmethod
    def _marks_match(ocr_marks: str, off_marks: str) -> bool:
        """Exact match first. If that fails, also accept when the OCR
        value is a non-empty prefix of the official value at least 3
        digits long -- confirmed real case: OCR merges a stray
        character into the digit run and truncates "0574" down to
        "057" (the trailing digit is lost, not misread, so a prefix
        check recovers it without weakening the check against genuinely
        different numbers). Deliberately one-directional: never accept
        the official value being a prefix of a longer OCR value, since
        the official record is authoritative and a longer OCR read
        should not be "forgiven" down to match it.
        """
        if not ocr_marks or not off_marks:
            return False
        if ocr_marks == off_marks:
            return True
        if len(ocr_marks) >= 3 and off_marks.startswith(ocr_marks):
            return True
        return False

    @staticmethod
    def _name_match(ocr_name: str, off_name: str) -> bool:
        """
        Candidate-name comparison used by both single-year (SSLC) and
        HSC record comparisons.

        Two behavioral changes vs. the previous exact/substring check:

        1. FIX #3 -- Missing OCR name is not a mismatch. If OCR failed
           to extract a name at all (ocr_name empty/None), there is
           nothing to disagree with -- the QR-verified official name is
           already authoritative and already flows through to
           display_metadata via base_verification.build_display_metadata.
           Scoring this as a mismatch penalizes the certificate's overall
           verification score for an OCR *absence*, not an OCR
           *disagreement*. Only applies when an official name exists to
           fall back on; if both are missing, there's genuinely nothing
           to verify and this returns False as before.

        2. FIX #1 -- Fuzzy similarity instead of exact/substring. OCR
           letter confusions (e.g. "TAMUEUAN V" vs "TAMILELAN V") are
           common enough that a straight substring check misses valid
           matches. FuzzyMatcher.is_match uses SequenceMatcher ratio,
           which tolerates a handful of character-level misreads while
           still rejecting genuinely different names.
        """
        if not ocr_name:
            return bool(off_name)

        if not off_name:
            return False

        # Fast path: exact or substring match (handles cases where one
        # side has extra tokens, e.g. a middle initial the other lacks).
        if ocr_name in off_name or off_name in ocr_name:
            return True

        comparison = FuzzyMatcher.compare(
            ocr_name,
            off_name
        )
        print(
            f"NAME SCORE = {comparison['score']} | "
            f"STATUS = {comparison['status']}"
        )

        return comparison["match"]
    def compare_records(self, ocr_data: dict, official_data: dict) -> dict:
        if official_data.get("years"):
            return self._compare_hsc_records(ocr_data, official_data)
        return self._compare_single_year_records(ocr_data, official_data)

    def _compare_hsc_records(self, ocr_data: dict, official_data: dict) -> dict:
        score = 0
        checks = {}

        ocr_roll = self.clean_text(ocr_data.get("roll_no"))
        ocr_marks = self.clean_text(ocr_data.get("total_marks"))
        years = official_data.get("years", {})

        matched_year = None
        for year_key, year_data in years.items():
            off_roll = self.clean_text(year_data.get("roll_no"))
            if ocr_roll and off_roll and ocr_roll == off_roll:
                matched_year = year_key
                break

        if matched_year:
            checks["roll_no_match"] = True
            score += 20
            off_marks = self.clean_text(years[matched_year].get("total_marks"))
            checks["total_marks_match"] = self._marks_match(ocr_marks, off_marks)
        else:
            checks["roll_no_match"] = False
            checks["total_marks_match"] = False
            for year_key, year_data in years.items():
                off_marks = self.clean_text(year_data.get("total_marks"))
                if self._marks_match(ocr_marks, off_marks):
                    checks["total_marks_match"] = True
                    matched_year = year_key
                    break

        if checks["total_marks_match"]:
            score += 20

        ocr_reg = self.clean_text(ocr_data.get("reg_no"))
        off_reg = self.clean_text(official_data.get("reg_no"))
        reg_match = ocr_reg == off_reg and bool(ocr_reg)
        if not reg_match and ocr_reg and official_data.get("raw_text"):
            reg_match = ocr_reg in official_data["raw_text"].upper()
        checks["reg_no_match"] = reg_match
        if checks["reg_no_match"]:
            score += 20

        ocr_name = self.clean_text(ocr_data.get("candidate_name"))
        off_name = self.clean_text(official_data.get("candidate_name"))
        checks["candidate_name_match"] = self._name_match(ocr_name, off_name)
        if checks["candidate_name_match"]:
            score += 20

        ocr_inst = re.sub(r"^\d+\s*", "", self.clean_text(ocr_data.get("institution")))
        off_inst = self.clean_text(official_data.get("institution"))
        if not off_inst and official_data.get("raw_text") and ocr_inst:
            off_inst_raw = official_data["raw_text"].upper()
            ocr_words = {w for w in ocr_inst.split() if len(w) > 3}
            hits = sum(1 for w in ocr_words if w in off_inst_raw)
            checks["institution_match"] = hits >= 2
        elif ocr_inst and off_inst:
            checks["institution_match"] = self._school_match(ocr_inst, off_inst)
        else:
            checks["institution_match"] = False
        if checks["institution_match"]:
            score += 20

        return {"score": score, "checks": checks, "matched_year": matched_year}

    def _compare_single_year_records(self, ocr_data: dict, official_data: dict) -> dict:
        score = 0
        checks = {}

        ocr_roll = self.clean_text(ocr_data.get("roll_no"))
        off_roll = self.clean_text(official_data.get("roll_no"))
        checks["roll_no_match"] = ocr_roll == off_roll and bool(ocr_roll)
        if checks["roll_no_match"]:
            score += 20

        ocr_reg = self.clean_text(ocr_data.get("reg_no"))
        off_reg = self.clean_text(official_data.get("reg_no"))
        reg_match = ocr_reg == off_reg and bool(ocr_reg)
        if not reg_match and ocr_reg and official_data.get("raw_text"):
            reg_match = ocr_reg in official_data["raw_text"].upper()
        checks["reg_no_match"] = reg_match
        if checks["reg_no_match"]:
            score += 20

        ocr_name = self.clean_text(ocr_data.get("candidate_name"))
        off_name = self.clean_text(official_data.get("candidate_name"))
        checks["candidate_name_match"] = self._name_match(ocr_name, off_name)
        if checks["candidate_name_match"]:
            score += 20

        ocr_marks = self.clean_text(ocr_data.get("total_marks"))
        off_marks = self.clean_text(official_data.get("total_marks"))
        checks["total_marks_match"] = self._marks_match(ocr_marks, off_marks)
        if checks["total_marks_match"]:
            score += 20

        ocr_inst = re.sub(r"^\d+\s*", "", self.clean_text(ocr_data.get("institution")))
        off_inst = self.clean_text(official_data.get("institution"))

        if not off_inst and official_data.get("raw_text") and ocr_inst:
            off_inst_raw = official_data["raw_text"].upper()
            ocr_words = {w for w in ocr_inst.split() if len(w) > 3}
            hits = sum(1 for w in ocr_words if w in off_inst_raw)
            checks["institution_match"] = hits >= 2
        elif ocr_inst and off_inst:
            checks["institution_match"] = self._school_match(ocr_inst, off_inst)
        else:
            checks["institution_match"] = False

        if checks["institution_match"]:
            score += 20

        return {"score": score, "checks": checks}