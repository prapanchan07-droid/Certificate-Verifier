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

_SCHOOL_KEYWORDS = ["GOVT", "GOVERNMENT", "HR SEC", "HIGH SCHOOL",
                    "MATRICULATION", "AIDED", "SCHOOL", "COLLEGE"]


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

            # Register number
            m = re.search(r"\bJ\d{7}\b", page_text)
            if m:
                result["reg_no"] = m.group()
            if not result["reg_no"]:
                m = re.search(r"\b\d{10}\b", page_text)
                if m:
                    result["reg_no"] = m.group()
            if not result["reg_no"]:
                m = re.search(r"\b[A-Z]{1,3}\d{5,}\b", page_text)
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

            # Institution — find actual school name, skip board headers
            lines = page_text.split(" . ")

            # First try: anchor on "NAME OF THE SCHOOL"
            for i, line in enumerate(lines):
                if "NAME OF THE SCHOOL" in line:
                    for j in range(i, min(i + 3, len(lines))):
                        seg = lines[j].strip()
                        if any(kw in seg for kw in _SCHOOL_KEYWORDS) and \
                           not any(noise in seg for noise in _BOARD_NOISE):
                            result["institution"] = seg
                            break
                    if result["institution"]:
                        break

            # Fallback: any school-keyword line not in noise list
            if not result["institution"]:
                for line in lines:
                    if any(kw in line for kw in _SCHOOL_KEYWORDS) and \
                       not any(noise in line for noise in _BOARD_NOISE):
                        result["institution"] = line.strip()
                        break

            print("OFFICIAL DATA EXTRACTED:", result)
            return result

        except Exception as e:
            return {"success": False, "error": str(e)}

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

        # Register number
        ocr_reg = self.clean_text(ocr_data.get("reg_no"))
        off_reg = self.clean_text(official_data.get("reg_no"))
        checks["reg_no_match"] = ocr_reg == off_reg and bool(ocr_reg)
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

        # Institution — compare actual school names
        ocr_inst = re.sub(r"^\d+\s*", "", self.clean_text(ocr_data.get("institution")))
        off_inst = self.clean_text(official_data.get("institution"))

        if ocr_inst and off_inst:
            # Partial match — school names often have OCR noise
            ocr_words = set(ocr_inst.split())
            off_words = set(off_inst.split())
            common = ocr_words & off_words
            # Need at least 2 meaningful words in common
            meaningful = {w for w in common if len(w) > 3}
            checks["institution_match"] = len(meaningful) >= 2
        else:
            checks["institution_match"] = False

        if checks["institution_match"]:
            score += 20

        return {"score": score, "checks": checks}
