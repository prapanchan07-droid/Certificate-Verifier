import re

from typing import Optional
from .base_parser import BaseParser

from .parser_utils import (
    _looks_like_name,
    _is_english,
    _SESSIONS,
    _BOARD_NOISE,
    _SCHOOL_KEYWORDS,
    _validate_name,
)

class SSLCParser(BaseParser):

    def parse(self, text: str, lines: list):

        result = {
            "candidate_name": None,
            "roll_no": None,
            "reg_no": None,
            "total_marks": None,
            "institution": None,
            "raw_text": text,
        }

        result["candidate_name"] = self._extract_candidate_name(text, lines)

        result["roll_no"] = self._extract_roll_no(text, lines)

        if not result["roll_no"]:
            m = re.search(r"\b\d{7}\b", text)
            if m:
                result["roll_no"] = m.group(0)

        result["reg_no"] = self._extract_reg_no(text)

        result["total_marks"] = self._extract_total_marks(text, lines)

        mid = len(lines) // 2

        result["institution"] = self._extract_institution(lines[mid:])

        if not result["institution"]:
            result["institution"] = self._extract_institution(lines)

        return result
            
    def _extract_roll_no(self, text_dump: str, lines: list) -> Optional[str]:
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

    def _extract_reg_no(self, text_dump: str) -> Optional[str]:
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

    def _extract_total_marks(self, text_dump: str, lines: list) -> Optional[str]:
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

    def _extract_candidate_name(self, text_dump: str, lines: list) -> Optional[str]:
        """
        From the logs, the OCR produces this exact line:
        'ல MUTHU KRISHNAN N APR 2023'
        So the name and session are on the SAME line with garbage prefix.
        Pattern: strip garbage → extract name before session token.
        """
        session_re = re.compile(_SESSIONS + r'\s+\d{4}')

        # Pattern 1: name + session on the same line
        for line in lines:
            if session_re.search(line):
                cleaned = re.sub(r'^[^A-Z]+', '', line.strip())
                m2 = session_re.search(cleaned)
                name_part = cleaned[:m2.start()].strip() if m2 else cleaned
                name_part = re.sub(r'[^A-Z\s\.]', '', name_part).strip()
                name = _validate_name(name_part)
                if name:
                    print(f"NAME P1: {name}")
                    return name

        # Pattern 2: directly after NAME OF THE CANDIDATE label
        for i, line in enumerate(lines):
            if "NAME OF THE CANDIDATE" in line:
                after = re.sub(r'.*NAME OF THE CANDIDATE\s*[:\-/|]?\s*', '',
                            line).strip()
                after = re.sub(r'^[^A-Z]+', '', after).strip()
                after = session_re.sub('', after).strip()
                after = re.sub(r'[^A-Z\s\.]', '', after).strip()
                name = _validate_name(after)
                if name:
                    print(f"NAME P2a: {name}")
                    return name
                # Check next lines
                for j in range(i + 1, min(i + 5, len(lines))):
                    candidate = re.sub(r'^[^A-Z]+', '', lines[j].strip())
                    candidate = session_re.sub('', candidate).strip()
                    candidate = re.sub(r'[^A-Z\s\.]', '', candidate).strip()
                    name = _validate_name(candidate)
                    if name:
                        print(f"NAME P2b: {name}")
                        return name
                break

        # Pattern 3: scan all lines for name near session context
        for i, line in enumerate(lines):
            stripped = re.sub(r'^[^A-Z]+', '', line.strip())
            if not stripped:
                continue
            if re.search(r'\d', stripped):
                continue
            name = _validate_name(stripped)
            if name:
                prev = lines[i - 1].strip() if i > 0 else ""
                nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
                context = prev + " " + nxt
                if re.search(_SESSIONS, context) or "CANDIDATE" in context \
                        or "பெயர்" in context or "பருவம்" in context:
                    print(f"NAME P3: {name}")
                    return name

        return None

    def _extract_institution(self, lines: list) -> Optional[str]:
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

    


