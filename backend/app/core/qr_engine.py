import cv2
import numpy as np
import tempfile
import os
from urllib.parse import urlparse


class QREngine:

    ALLOWED_DOMAINS = [
        ".gov.in",
        "digilocker.gov.in",
        "verification.tn.gov.in",
        "certverify.tndge.org",
    ]

    def verify_domain(self, qr_data: str) -> dict:
        try:
            parsed = urlparse(qr_data)
            domain = parsed.netloc
            is_secure = parsed.scheme == "https"
            is_authentic = (
                any(domain.endswith(d) for d in self.ALLOWED_DOMAINS)
                or ".gov.in" in domain
            )
            return {
                "status": "SCANNED",
                "is_secure": is_secure,
                "data": qr_data,
                "domain": domain,
                "domain_authenticity": is_authentic,
            }
        except Exception:
            return {
                "status": "SCANNED",
                "is_secure": False,
                "data": qr_data,
                "domain": None,
                "domain_authenticity": False,
            }

    def _try(self, detector, image) -> str | None:
        try:
            qr_data, _, _ = detector.detectAndDecode(image)
            if qr_data and qr_data.strip():
                print("QR FOUND:", qr_data)
                return qr_data
        except Exception as e:
            print("QR decode error:", e)
        return None

    def scan_and_verify(self, img: np.ndarray) -> dict:
        detector = cv2.QRCodeDetector()
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Method 1 — original colour
        d = self._try(detector, img)
        if d:
            return self.verify_domain(d)

        # Method 2 — grayscale
        d = self._try(detector, gray)
        if d:
            return self.verify_domain(d)

        # Method 3 — adaptive threshold
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )
        d = self._try(detector, thresh)
        if d:
            return self.verify_domain(d)

        # Method 4 — 3× enlarge
        d = self._try(detector, cv2.resize(gray, None, fx=3, fy=3,
                                           interpolation=cv2.INTER_CUBIC))
        if d:
            return self.verify_domain(d)

        # Method 5 — sharpen
        kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
        d = self._try(detector, cv2.filter2D(gray, -1, kernel))
        if d:
            return self.verify_domain(d)

        # Method 6 — square-ish contour crops
        contours, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            if w * h < 5000:
                continue
            if not (0.7 < w / float(h) < 1.3):
                continue
            roi = gray[y:y + h, x:x + w]
            if roi.size == 0:
                continue
            roi = cv2.resize(roi, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
            d = self._try(detector, roi)
            if d:
                return self.verify_domain(d)

        # Method 7 — top-right region, detect then crop tight
        ih, iw = gray.shape
        top_right = gray[0:int(ih * 0.55), int(iw * 0.50):iw]
        retval, points = detector.detect(top_right)
        if retval and points is not None:
            pts = points[0].astype(int)
            x1, y1 = np.min(pts[:, 0]), np.min(pts[:, 1])
            x2, y2 = np.max(pts[:, 0]), np.max(pts[:, 1])
            crop = top_right[max(0, y1 - 20):y2 + 20, max(0, x1 - 20):x2 + 20]
            if crop.size > 0:
                crop = cv2.resize(crop, None, fx=8, fy=8, interpolation=cv2.INTER_CUBIC)
                d = self._try(detector, crop)
                if d:
                    return self.verify_domain(d)

        # Method 8 — multi-scale top-right
        for scale in (2, 3, 4):
            d = self._try(detector, cv2.resize(top_right, None, fx=scale, fy=scale,
                                               interpolation=cv2.INTER_CUBIC))
            if d:
                return self.verify_domain(d)

        # Method 9 — blur + upscale
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        for scale in (2, 3, 4):
            d = self._try(detector, cv2.resize(blur, None, fx=scale, fy=scale,
                                               interpolation=cv2.INTER_CUBIC))
            if d:
                return self.verify_domain(d)

        # Method 10 — full-page 4× upscale
        d = self._try(detector, cv2.resize(gray, None, fx=4, fy=4,
                                           interpolation=cv2.INTER_CUBIC))
        if d:
            return self.verify_domain(d)

        print("QR NOT FOUND")
        return {
            "status": "NOT_FOUND",
            "is_secure": False,
            "data": None,
            "domain": None,
            "domain_authenticity": False,
        }
