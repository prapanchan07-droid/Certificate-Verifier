from __future__ import annotations

import re

from ..utils.tamil_extractor import TamilExtractor
from ..utils.name_validator import NameValidator
from ..utils.parser_confidence import ParserConfidence
from .base_parser import BaseParser
_MARKS_WORDS = {
    "ZERO": "0",
    "ONE": "1",
    "TWO": "2",
    "THREE": "3",
    "FOUR": "4",
    "FIVE": "5",
    "SIX": "6",
    "SEVEN": "7",
    "EIGHT": "8",
    "NINE": "9",
}


class HSCParser(BaseParser):

    ####################################################################
    # Helper Functions
    ####################################################################

    def _clean_name_line(self, s: str) -> str:
        s = s.upper()
        s = s.replace("MARK CERTIFICATE", "")
        s = s.replace("YEAR OF ISSUE", "")
        s = s.replace("AND YEAR OF ISSUE", "")
        s = s.replace("YEAROF ISSUEOF", "")

        REMOVE = [
            "MARK CERTIFICATE",
            "CERTIFICATE",
            "YEAR OF ISSUE",
            "AND YEAR OF ISSUE",
            "YEAR OF ISSUE OF",
            "DATE OF BIRTH",
            "NAME OF THE CANDIDATE",
        ]

        for r in REMOVE:
            s = s.replace(r, "")

        s = re.sub(r"[^A-Z.\s]", " ", s)
        s = re.sub(r"\s+", " ", s)
        s = re.sub(r"\b\d+\b", " ", s)   # Remove standalone numbers like 2280
        return s.strip()

    def _trim_to_name(self, words: list) -> list:
        """
        Trim OCR noise after a candidate name.

        Examples:
            PRAPANCHAN V MARK CERTIFICATE
                -> PRAPANCHAN V

            ARULMURUGAN P DATE OF BIRTH
                -> ARULMURUGAN P

            MUTHU KRISHNAN N
                -> MUTHU KRISHNAN N

            MOHAMMED ABDUL RAHMAN
                -> MOHAMMED ABDUL RAHMAN

            SRI VIGNESH KUMAR R
                -> SRI VIGNESH KUMAR R
        """

        STOP_WORDS = {
            "MARK",
            "MARKS",
            "CERTIFICATE",
            "STATE",
            "BOARD",
            "DATE",
            "BIRTH",
            "REGISTER",
            "NUMBER",
            "ROLL",
            "SESSION",
            "YEAR",
            "GROUP",
            "MEDIUM",
            "SCHOOL",
            "TOTAL",
            "AUTHORITY",
            "GOVERNMENT",
            "EXAMINATION",
            "EXAMINATIONS",
            "SUBJECT",
            "PASS",
            "PASSED",
            "THE",
            "OF",
            "ISSUE",
            "AND",
            "PERMANENT",
        }

        trimmed = []

        for word in words:

            # Stop when OCR has entered the next heading
            if word in STOP_WORDS:
                break

            # OCR may merge YEAR with other text
            if word.startswith("YEAR"):
                break

            # Stop on OCR fragments of CERTIFICATE
            if (
                "CERT" in word
                or "TIAIC" in word
                or "TIFIC" in word
                or "IFICATE" in word
                or word.startswith("CLI")
            ):
                break

            trimmed.append(word)

        return trimmed

    def _bad_name_line(self, s: str) -> bool:
        if not s:
            return True

        s = s.upper().strip()

        BAD_WORDS = [
            "NAME OF THE CANDIDATE",
            "MARK CERTIFICATE",
            "CERTIFICATE",
            "DATE OF BIRTH",
            "PERMANENT REGISTER",
            "REGISTER NUMBER",
            "ROLL",
            "TOTAL MARKS",
            "GROUP",
            "MEDIUM",
            "SCHOOL",
            "BOARD",
            "GOVERNMENT",
            "SESSION",
            "YEAR",
            "ISSUE",
            "YEAR OF ISSUE",
            "AND YEAR",
            "ISSUED UNDER",
            "AUTHORITY",
            "EXAMINATION",
            "COURSE",
        ]

        return any(word in s for word in BAD_WORDS)

    ####################################################################
    # Candidate Name Extraction
    ####################################################################

    def extract_candidate_name(self, lines):

        start = None
        end = None

        for i, line in enumerate(lines):

            u = line.upper()

            if "NAME OF THE CANDIDATE" in u:
                start = i

            if start is not None and "DATE OF BIRTH" in u:
                end = i
                break

        # Fallback anchor: OCR sometimes drops/mangles the word "NAME"
        # itself (confirmed case: "NAME" misread as garbled digits),
        # so the full "NAME OF THE CANDIDATE" phrase never appears even
        # though "OF THE CANDIDATE" does. Only used when the primary
        # anchor fails entirely, since it's a weaker, shorter match.
        if start is None:
            for i, line in enumerate(lines):
                u = line.upper()
                if "OF THE CANDIDATE" in u:
                    start = i
                if start is not None and "DATE OF BIRTH" in u:
                    end = i
                    break

        if start is None:
            return None

        if end is None:
            end = min(len(lines), start + 8)

        candidates = []

        for line in lines[start:end]:
            english = re.sub(r"[\u0B80-\u0BFF]+", " ", line)

            m = re.search(r"NAME\s+OF\s+THE\s+CANDIDATE", english, flags=re.I)
            if m:
                english = english[m.end():]
            else:
                m = re.search(r"OF\s+THE\s+CANDIDATE", english, flags=re.I)
                if m:
                    english = english[m.end():]

            cleaned = self._clean_name_line(english)
            words = cleaned.split()

            words = self._trim_to_name(words)

            # _clean_name_line intentionally keeps periods (for tokens
            # like initials), but that means a valid single-letter
            # initial can come through as "V." rather than "V" -- which
            # then fails the isalpha()-or-length-1 check below even
            # though it's a perfectly valid name token. Strip trailing
            # periods before validating/joining rather than rejecting
            # the whole candidate over punctuation.
            words = [w.rstrip(".") for w in words]
            words = [w for w in words if w]

            cleaned = " ".join(words)

            print("NAME LINE :", repr(line))
            print("CLEANED   :", cleaned)
            print("WORDS     :", words)

            if self._bad_name_line(cleaned):
                continue

            if (
                2 <= len(words) <= 6
                and any(len(w) >= 5 for w in words)
                and all(w.isalpha() or len(w) == 1 for w in words)
            ):
                candidates.append(cleaned)

        if not candidates:
            return None

        return candidates[-1]
    
    ####################################################################
    # Main Parser
    ####################################################################

    def parse(self, text: str, lines: list):

        print("\n========== HSC LINES ==========")

        for i, line in enumerate(lines):
            print(f"{i:02d}: {repr(line)}")

        print("===============================\n")

        result = {
            "candidate_name": None,
            "dob": None,
            "roll_no": None,
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

        ###############################################################
        # CERTIFICATE TYPE
        ###############################################################

        if (
            "FIRST YEAR MARK CERTIFICATE" in upper
            or "FIRST YEAR" in upper
        ):
            result["certificate_type"] = "HSF"

        elif (
            "SECOND YEAR MARK CERTIFICATE" in upper
            or "SECOND YEAR" in upper
        ):
            result["certificate_type"] = "HSS"

        ###############################################################
        # NAME
        ###############################################################

        result["candidate_name"] = self.extract_candidate_name(lines)

        ###############################################################
        # DOB
        ###############################################################

        dob = re.search(
            r"\b\d{2}/\d{2}/\d{4}\b",
            text,
        )

        if dob:
            result["dob"] = dob.group()

        ###############################################################
        # REGISTER NUMBER
        ###############################################################

        reg_no = None

        for i, line in enumerate(lines):
            if "PERMANENT REGISTER" in line.upper():
                block = " ".join(lines[i:i + 5])
                m = re.search(r"\b\d{10}\b", block)
                if m:
                    reg_no = m.group()
                break

        if reg_no is None:
            m = re.search(r"\b\d{10}\b", text)
            if m:
                reg_no = m.group()

        if reg_no is None:
            m = re.search(r"\b[A-Z]{1,4}\d{7,12}\b", upper)
            if m:
                reg_no = m.group()

        result["reg_no"] = reg_no

        ###############################################################
        # ROLL NUMBER
        ###############################################################

        roll = None

        matches = re.findall(
            r"\b(\d{7})\s+MAR\s+\d{4}\b",
            upper,
        )

        if matches:

            matches = [
                x
                for x in matches
                if not x.startswith("101")
            ]

            if matches:

                from collections import Counter

                roll = Counter(matches).most_common(1)[0][0]

        result["roll_no"] = roll

        ###############################################################
        # TOTAL MARKS
        ###############################################################

        total_marks = None

        for line in lines:

            u = line.upper()

            if "TOTAL" in u and "MARK" in u:

                digit_words = re.findall(
                    r"ZERO|ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE",
                    u,
                )

                if len(digit_words) >= 4:

                    total_marks = "".join(
                        _MARKS_WORDS[w]
                        for w in digit_words[:4]
                    )

                    break

                nums = re.findall(r"\b\d{3,4}\b", u)

                if nums:

                    total_marks = nums[-1]

                    break

        if total_marks is None:

            nums = re.findall(r"\b\d{3,4}\b", upper)

            valid = [
                n
                for n in nums
                if 150 <= int(n) <= 1200
            ]

            if valid:
                total_marks = valid[-1]

        result["total_marks"] = total_marks

        ###############################################################
        # MEDIUM
        ###############################################################

        for i, line in enumerate(lines):

            block = " ".join(lines[i:i + 5]).upper()

            if (

                "MEDIUM OF INSTRUCTION" in block

                or "MEOIUM OF INSTRUCTION" in block

                or "MEDIUM OF" in block

            ):

                search = " ".join(lines[i:i + 10]).upper()

                if (

                    "ENGLISH" in search

                    or "ENGUSH" in search

                    or "ENCLISH" in search

                ):

                    result["medium"] = "ENGLISH"

                    break

                if (

                    "TAMIL" in search

                    or "TAME" in search

                    or "TAMI" in search

                    or "TAML" in search

                ):

                    result["medium"] = "TAMIL"

                    break

        ###############################################################
        # GROUP
        ###############################################################

        for i, line in enumerate(lines):

            block = " ".join(lines[i:i + 12]).upper()

            # Normalize OCR spacing
            block = re.sub(r"\s+", " ", block)
            compact = block.replace(" ", "")

            if (

                "GROUP CODE" in block

                or "GROUP" in block

            ):

                if "VOCATIONALEDUCATION" in compact:

                    result["group"] = "VOCATIONAL EDUCATION"

                    break

                if (
                    "GENERALEDUCATION" in compact
                    or "GENERAL EDUCATION" in block
                    or "OAEDUCATION" in compact
                    or "EDUCATON" in compact
                ):
                    result["group"] = "GENERAL EDUCATION"
                    break

                m = re.search(
                    r"BASIC\s+[A-Z ]+ENGINEERING",
                    block,
                )

                if m:

                    result["group"] = m.group().strip()

                    break

        ###############################################################
        # SCHOOL
        ###############################################################
        # Anchor on the SINGLE line that actually contains the label,
        # not a 3-line lookahead window. The window version checked
        # `"NAME OF THE SCHOOL" in " ".join(lines[i:i+3])`, which
        # triggers as soon as ANY of those 3 lines contains the phrase
        # -- so it could fire up to 2 lines before the real label line,
        # anchoring `i` too early and making `lines[i+1:i+6]` scan
        # completely unrelated lines (confirmed: it was capturing the
        # TOTAL MARKS line as "school" content). A single-line check
        # anchors precisely on the label itself.

        school = None

        for i, line in enumerate(lines):

            if "NAME OF THE SCHOOL" not in line.upper():
                continue

            print("\nFOUND SCHOOL HEADER")

            parts = []

            for nxt in lines[i + 1:i + 6]:

                print("RAW SCHOOL:", repr(nxt))

                english = re.sub(r"[\u0B80-\u0BFF]+", " ", nxt)
                english = " ".join(english.split())

                if len(re.findall(r"[A-Z]", english)) < 5:
                    print("SKIP TAMIL")
                    continue

                s = english.upper()

                if "GROUP CODE" in s:
                    print("STOP GROUP")
                    break

                if "MEDIUM" in s:
                    print("STOP MEDIUM")
                    break

                if "EMIS" in s:
                    print("STOP EMIS")
                    break

                s = re.sub(r"\b\d{6,}\b", "", s)
                s = re.sub(r"[^A-Z ]", " ", s)
                s = " ".join(s.split())

                if "TOTAL MARK" in s:
                    continue

                if "NAME OF THE SCHOOL" in s:
                    continue

                if len(s.split()) < 3:
                    continue

                print("CLEAN SCHOOL:", s)

                if not (
                    "SCHOOL" in s
                    or "GOVT" in s
                    or "GOVERNMENT" in s
                    or "VIDYA" in s
                    or "PUBLIC" in s
                    or "ACADEMY" in s
                    or "HIGHER" in s
                    or "HR" in s
                    or "MATRIC" in s
                    or "SECONDARY" in s
                    or "HIGH" in s
                ):
                    continue

                parts.append(s)

            print("PARTS:", parts)

            if parts:

                combined = " ".join(parts)

                print("COMBINED:", combined)

                combined = re.sub(r"^[A-Z]\s+", "", combined)
                combined = " ".join(combined.split())

                school = combined
                break

        result["institution"] = school

        ###############################################################
        # SESSION
        ###############################################################

        m = re.search(
            r"(MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+20\d{2}",
            upper,
        )

        if m:
            result["session"] = m.group()

        ###############################################################
        # FINAL CLEANUP
        ###############################################################

        for key, value in result.items():

            if isinstance(value, str):

                value = re.sub(r"\s+", " ", value)

                value = value.strip()

                if value == "":
                    value = None

                result[key] = value

        print("\n========== HSC PARSED ==========")

        for k, v in result.items():
            print(f"{k:20}: {v}")

        print("================================\n")

        return result