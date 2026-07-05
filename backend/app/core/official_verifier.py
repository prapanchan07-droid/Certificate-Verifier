import requests
from bs4 import BeautifulSoup
import re

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


class OfficialVerifier:

    def extract_official_data(self, qr_url: str) -> dict:
        try:
            response = requests.get(qr_url, timeout=15)
            if response.status_code != 200:
                return {"success": False, "error": f"HTTP {response.status_code}"}

            soup = BeautifulSoup(response.text, "html.parser")
            page_text = soup.get_text(separator=" ", strip=True).upper()

            result = {
                "success": True,
                "candidate_name": None,
                "roll_no": None,
                "reg_no": None,
                "total_marks": None,
                "institution": None,
                "raw_text": page_text,
            }

            # Roll number (7 digits)
            m = re.search(r"\b\d{7}\b", page_text)
            if m:
                result["roll_no"] = m.group()

            # Register number — J-prefix first
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

            # Total marks
            m = re.search(r"TOTAL\s+MARKS.*?(\d{3,4})", page_text, re.IGNORECASE)
            if m:
                result["total_marks"] = m.group(1)

            # Candidate name
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

            # Institution — search full raw text directly
            # Official page has: "NAME OF THE SCHOOL பள்ளியின் பெயர் ... T V S GOVT HR SEC SCHOOL THIRUKKURUNGUDI"
            result["institution"] = self._extract_institution_from_text(page_text)

            print("OFFICIAL DATA EXTRACTED:", result)
            return result

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _extract_institution_from_text(self, page_text: str) -> str | None:
        """Extract school name from flat official page text."""

        # Strategy 1: after NAME OF THE SCHOOL anchor
        m = re.search(
            r"NAME OF THE SCHOOL[^A-Z]*([A-Z][A-Z\s]{5,60}?)(?:\s+IP ADDRESS|\s+DATE|\s*$)",
            page_text,
            re.DOTALL,
        )
        if m:
            candidate = m.group(1).strip()
            candidate = re.sub(r'\s+', ' ', candidate)
            if any(kw in candidate for kw in _SCHOOL_KEYWORDS) and \
               not any(noise in candidate for noise in _BOARD_NOISE):
                return candidate

        # Strategy 2: find school name pattern directly in text
        # Matches "T V S GOVT HR SEC SCHOOL THIRUKKURUNGUDI" style
        for pattern in [
            r'\b([A-Z][A-Z\s]*(?:GOVT|GOVERNMENT)[A-Z\s]*(?:HR SEC|HIGH SCHOOL|SCHOOL)[A-Z\s]{3,40})\b',
            r'\b([A-Z][A-Z\s]*(?:HR SEC|MATRICULATION|AIDED)[A-Z\s]*SCHOOL[A-Z\s]{3,40})\b',
        ]:
            m = re.search(pattern, page_text)
            if m:
                candidate = re.sub(r'\s+', ' ', m.group(1).strip())
                if not any(noise in candidate for noise in _BOARD_NOISE):
                    return candidate

        return None

    @staticmethod
    def clean_text(text) -> str:
        if not text:
            return ""
        return re.sub(r"\s+", " ", str(text).strip().upper())

    def compare_records(self, ocr_data: dict, official_data: dict) -> dict:
        score = 0
        checks = {}

        # Roll number
        ocr_roll = self.clean_text(ocr_data.get("roll_no"))
        off_roll = self.clean_text(official_data.get("roll_no"))
        checks["roll_no_match"] = ocr_roll == off_roll and bool(ocr_roll)
        if checks["roll_no_match"]:
            score += 20

        # Register number — compare the permanent reg from OCR vs J-code from official
        # Both identify the same student so we cross-match too
        ocr_reg = self.clean_text(ocr_data.get("reg_no"))
        off_reg = self.clean_text(official_data.get("reg_no"))
        # Direct match
        reg_match = ocr_reg == off_reg and bool(ocr_reg)
        # Also check if OCR permanent reg matches what's in official raw text
        if not reg_match and ocr_reg and official_data.get("raw_text"):
            reg_match = ocr_reg in official_data["raw_text"].upper()
        checks["reg_no_match"] = reg_match
        if checks["reg_no_match"]:
            score += 20

        # Candidate name
        ocr_name = self.clean_text(ocr_data.get("candidate_name"))
        off_name = self.clean_text(official_data.get("candidate_name"))
        checks["candidate_name_match"] = bool(ocr_name) and (
            ocr_name in off_name or off_name in ocr_name
        )
        if checks["candidate_name_match"]:
            score += 20

        # Total marks
        ocr_marks = self.clean_text(ocr_data.get("total_marks"))
        off_marks = self.clean_text(official_data.get("total_marks"))
        checks["total_marks_match"] = ocr_marks == off_marks and bool(ocr_marks)
        if checks["total_marks_match"]:
            score += 20

        # Institution — word overlap between OCR and official
        ocr_inst = re.sub(r"^\d+\s*", "", self.clean_text(ocr_data.get("institution")))
        off_inst = self.clean_text(official_data.get("institution"))

        # Fallback: search OCR institution words in official raw text
        if not off_inst and official_data.get("raw_text") and ocr_inst:
            off_inst_raw = official_data["raw_text"].upper()
            ocr_words = {w for w in ocr_inst.split() if len(w) > 3}
            hits = sum(1 for w in ocr_words if w in off_inst_raw)
            checks["institution_match"] = hits >= 2
        elif ocr_inst and off_inst:
            ocr_words = set(ocr_inst.split())
            off_words = set(off_inst.split())
            meaningful = {w for w in (ocr_words & off_words) if len(w) > 3}
            checks["institution_match"] = len(meaningful) >= 2
        else:
            checks["institution_match"] = False

        if checks["institution_match"]:
            score += 20

        return {"score": score, "checks": checks}