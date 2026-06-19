import requests
from bs4 import BeautifulSoup
import re


class OfficialVerifier:

    def extract_official_data(self, qr_url):

        try:

            response = requests.get(
                qr_url,
                timeout=15
            )

            if response.status_code != 200:

                return {
                    "success": False,
                    "error": "Official page not reachable"
                }

            soup = BeautifulSoup(
                response.text,
                "html.parser"
            )

            page_text = soup.get_text(
                separator=" ",
                strip=True
            ).upper()

            result = {
                "success": True,
                "candidate_name": None,
                "roll_no": None,
                "reg_no": None,
                "total_marks": None,
                "raw_text": page_text
            }

            # Roll Number
            roll_match = re.search(
                r"\b\d{7}\b",
                page_text
            )

            if roll_match:
                result["roll_no"] = roll_match.group()

            # Register Number
            reg_match = re.search(
                r"\b[A-Z]\d{7,}\b",
                page_text
            )

            if reg_match:
                result["reg_no"] = reg_match.group()

            # Total Marks

            marks_match = re.search(
                r"TOTAL\s+MARKS.*?(\d{3})",
                page_text,
                re.IGNORECASE
            )

            if marks_match:
                result["total_marks"] = marks_match.group(1)
                
            print("TOTAL MARKS FOUND:")
            print(result["total_marks"])

            # Candidate Name
            name_match = re.search(
                r'NAME OF THE CANDIDATE.*?([A-Z]+\s+[A-Z]+\s+[A-Z])',
                page_text.upper(),
                re.DOTALL
            )

            if name_match:
                result["candidate_name"] = name_match.group(1)
            
            result["institution"] = None

            for line in page_text.split(" . "):

                if (
                    "STATE BOARD" in line
                    or "SCHOOL" in line
                    or "COLLEGE" in line
                ):
                    result["institution"] = line.strip()
                    break

            print("OCR EXTRACTED:")
            print(result)
            return result

        except Exception as e:

            return {
                "success": False,
                "error": str(e)
            }

    def clean_text(self,text):
        if not text:
            return ""

        return re.sub(
            r"\s+",
            " ",
            str(text).strip().upper()
        )


    def compare_records(self,ocr_data, official_data):

        score = 0

        checks = {}

        # ==========================
        # Roll Number
        # ==========================
        if (
            self.clean_text(ocr_data.get("roll_no"))
            ==
            self.clean_text(official_data.get("roll_no"))
        ):
            score += 20
            checks["roll_no_match"] = True
        else:
            checks["roll_no_match"] = False

        # ==========================
        # Register Number
        # ==========================
        if (
            self.clean_text(ocr_data.get("reg_no"))
            ==
            self.clean_text(official_data.get("reg_no"))
        ):
            score += 20
            checks["reg_no_match"] = True
        else:
            checks["reg_no_match"] = False

        # ==========================
        # Candidate Name
        # ==========================
        ocr_name = self.clean_text(
            ocr_data.get("candidate_name")
        )

        official_name = self.clean_text(
            official_data.get("candidate_name")
        )

        if (
            ocr_name
            and
            ocr_name in official_name
        ):
            score += 20
            checks["candidate_name_match"] = True
        else:
            checks["candidate_name_match"] = False

        # ==========================
        # Total Marks
        # ==========================
        if (
            self.clean_text(ocr_data.get("total_marks"))
            ==
            self.clean_text(official_data.get("total_marks"))
        ):
            score += 20
            checks["total_marks_match"] = True
        else:
            checks["total_marks_match"] = False

        # ==========================
        # Institution
        # ==========================
        ocr_inst = self.clean_text(
            ocr_data.get("institution")
        )

        official_inst = self.clean_text(
            official_data.get("institution")
        )

        ocr_inst = re.sub(r'^\d+\s*', '', ocr_inst)

        if (
            "STATE BOARD OF SCHOOL EXAMINATIONS"
            in official_inst
        ):
            score += 20
            checks["institution_match"] = True
        else:
            checks["institution_match"] = False
        return {
    "score": score,
    "checks": checks
}