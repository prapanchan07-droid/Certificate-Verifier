import re

from typing import Optional
from .base_parser import BaseParser


class HSCParser(BaseParser):

    def parse(self, text: str, lines: list):

        result = {
            "candidate_name": None,
            "dob": None,
            "reg_no": None,
            "certificate_no": None,
            "total_marks": None,
            "institution": None,
            "medium": None,
            "group": None,
            "session": None,
            "certificate_type": None,
            "raw_text": text,
        }

        upper = text.upper()

        #######################################################
        # CERTIFICATE TYPE
        #######################################################

        if "FIRST YEAR MARK CERTIFICATE" in upper:
            result["certificate_type"] = "HSF"

        elif "SECOND YEAR MARK CERTIFICATE" in upper:
            result["certificate_type"] = "HSS"

        #######################################################
        # NAME
        #######################################################

        m = re.search(
            r"NAME OF THE CANDIDATE\s+([A-Z .]+)",
            upper
        )

        if m:
            result["candidate_name"] = m.group(1).strip()

        #######################################################
        # DOB
        #######################################################

        m = re.search(
            r"DATE OF BIRTH\s*(\d{2}/\d{2}/\d{4})",
            upper
        )

        if m:
            result["dob"] = m.group(1)

        #######################################################
        # PERMANENT REGISTER NUMBER
        #######################################################

        m = re.search(
            r"PERMANENT REGISTER NUMBER\s*(\d{10})",
            upper
        )

        if m:
            result["reg_no"] = m.group(1)

        #######################################################
        # CERTIFICATE NUMBER
        #######################################################

        m = re.search(
            r"CERTIFICATE SL\.?\s*NO\.?\s*:\s*(\d+)",
            upper
        )

        if m:
            result["certificate_no"] = m.group(1)

        #######################################################
        # TOTAL MARKS
        #######################################################

        m = re.search(
            r"TOTAL MARKS\s*[:\-]?\s*(\d{3,4})",
            upper
        )

        if m:
            result["total_marks"] = m.group(1)

        #######################################################
        # MEDIUM
        #######################################################

        m = re.search(
            r"MEDIUM OF INSTRUCTION\s*([A-Z ]+)",
            upper
        )

        if m:
            result["medium"] = m.group(1).strip()

        #######################################################
        # GROUP
        #######################################################

        m = re.search(
            r"GROUP CODE AND NAME\s*([A-Z ]+)",
            upper
        )

        if m:
            result["group"] = m.group(1).strip()

        #######################################################
        # SCHOOL
        #######################################################

        m = re.search(
            r"NAME OF THE SCHOOL\s*([A-Z0-9 .,&()-]+)",
            upper
        )

        if m:
            result["institution"] = m.group(1).strip()

        #######################################################
        # SESSION
        #######################################################

        m = re.search(
            r"(MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+20\d{2}",
            upper
        )

        if m:
            result["session"] = m.group(0)

        return result