import cv2
import numpy as np
from urllib.parse import urlparse
import os
import glob


class QREngine:

    def __init__(self):
        self.allowed_domains = [
            ".gov.in",
            "digilocker.gov.in",
            "verification.tn.gov.in",
            "certverify.tndge.org"
        ]

    def verify_domain(self, qr_data):

        try:
            parsed = urlparse(qr_data)

            domain = parsed.netloc

            is_secure = parsed.scheme == "https"

            is_authentic = (
                any(domain.endswith(d) for d in self.allowed_domains)
                or ".gov.in" in domain
            )

            return {
                "status": "SCANNED",
                "is_secure": is_secure,
                "data": qr_data,
                "domain": domain,
                "domain_authenticity": is_authentic
            }

        except Exception:

            return {
                "status": "SCANNED",
                "is_secure": False,
                "data": qr_data,
                "domain": None,
                "domain_authenticity": False
            }

    def try_decode(self, detector, image):

        try:
            qr_data, bbox, _ = detector.detectAndDecode(image)

            if qr_data and len(qr_data.strip()) > 0:
                print("QR FOUND:", qr_data)
                return qr_data

        except Exception as e:
            print("Decode Error:", e)

        return None

    def scan_and_verify(self, img):
        try:
            detector = cv2.QRCodeDetector()

            # ===============================
            # METHOD 1 : ORIGINAL
            # ===============================

            print("METHOD 1")

            qr_data = self.try_decode(detector, img)

            if qr_data:
                return self.verify_domain(qr_data)

            # ===============================
            # METHOD 2 : GRAYSCALE
            # ===============================

            print("METHOD 2")

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            qr_data = self.try_decode(detector, gray)

            if qr_data:
                return self.verify_domain(qr_data)

            # ===============================
            # METHOD 3 : THRESHOLD
            # ===============================

            print("METHOD 3")

            thresh = cv2.adaptiveThreshold(
                gray,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                11,
                2
            )

            cv2.imwrite("debug_thresh.png", thresh)

            qr_data = self.try_decode(detector, thresh)

            if qr_data:
                return self.verify_domain(qr_data)

            # ===============================
            # METHOD 4 : ENLARGED
            # ===============================

            print("METHOD 4")

            enlarged = cv2.resize(
                gray,
                None,
                fx=3,
                fy=3,
                interpolation=cv2.INTER_CUBIC
            )

            qr_data = self.try_decode(detector, enlarged)

            if qr_data:
                return self.verify_domain(qr_data)

            # ===============================
            # METHOD 5 : SHARPENED
            # ===============================

            print("METHOD 5")

            kernel = np.array([
                [-1, -1, -1],
                [-1, 9, -1],
                [-1, -1, -1]
            ])

            sharpened = cv2.filter2D(gray, -1, kernel)

            cv2.imwrite("debug_sharpened.png", sharpened)

            qr_data = self.try_decode(detector, sharpened)

            if qr_data:
                return self.verify_domain(qr_data)

            # ===============================
            # METHOD 6 : FIND QR REGION
            # ===============================

            print("METHOD 6")

            contours, _ = cv2.findContours(
                thresh,
                cv2.RETR_LIST,
                cv2.CHAIN_APPROX_SIMPLE
            )

            count = 0

            for cnt in contours:

                x, y, w, h = cv2.boundingRect(cnt)

                area = w * h

                if area < 5000:
                    continue

                ratio = w / float(h)

                if ratio < 0.7 or ratio > 1.3:
                    continue

                roi = gray[y:y+h, x:x+w]

                if roi.size == 0:
                    continue

                roi = cv2.resize(
                    roi,
                    None,
                    fx=4,
                    fy=4,
                    interpolation=cv2.INTER_CUBIC
                )

                cv2.imwrite(
                    f"debug_qr_{count}.jpg",
                    roi
                )

                count += 1

                qr_data = self.try_decode(detector, roi)

                if qr_data:
                    return self.verify_domain(qr_data)

            # ===============================
            # METHOD 7 : TOP RIGHT SEARCH
            # ===============================

            print("METHOD 7")

            h, w = gray.shape

            top_right = gray[
                0:int(h * 0.55),
                int(w * 0.50):w
            ]

            cv2.imwrite(
                "top_right_debug.jpg",
                top_right
            )

            retval, points = detector.detect(top_right)

            print("QR DETECTED:", retval)
            print("POINTS:", points)

            if retval:

                pts = points[0].astype(int)

                x1 = np.min(pts[:, 0])
                y1 = np.min(pts[:, 1])

                x2 = np.max(pts[:, 0])
                y2 = np.max(pts[:, 1])

                qr_crop = top_right[
                    max(0, y1 - 20):y2 + 20,
                    max(0, x1 - 20):x2 + 20
                ]

                cv2.imwrite(
                    "debug_qr_detected.png",
                    qr_crop
                )

                qr_crop = cv2.resize(
                    qr_crop,
                    None,
                    fx=8,
                    fy=8,
                    interpolation=cv2.INTER_CUBIC
                )

                qr_data = self.try_decode(
                    detector,
                    qr_crop
                )

                if qr_data:
                    return self.verify_domain(qr_data)

            # ===============================
            # METHOD 8 : MULTI SCALE TOP RIGHT
            # ===============================

            print("METHOD 8")

            for scale in [2, 3, 4]:

                enlarged = cv2.resize(
                    top_right,
                    None,
                    fx=scale,
                    fy=scale,
                    interpolation=cv2.INTER_CUBIC
                )

                cv2.imwrite(
                    f"top_right_scale_{scale}.png",
                    enlarged
                )

                qr_data = self.try_decode(
                    detector,
                    enlarged
                )

                if qr_data:
                    return self.verify_domain(qr_data)

            # ===============================
            # METHOD 9 : BLUR + UPSCALE
            # ===============================

            print("METHOD 9")

            blur = cv2.GaussianBlur(
                gray,
                (5, 5),
                0
            )

            for scale in [2, 3, 4]:

                enlarged = cv2.resize(
                    blur,
                    None,
                    fx=scale,
                    fy=scale,
                    interpolation=cv2.INTER_CUBIC
                )

                qr_data = self.try_decode(
                    detector,
                    enlarged
                )

                if qr_data:
                    return self.verify_domain(qr_data)

            # ===============================
            # METHOD 10 : WHOLE PAGE UPSCALE
            # ===============================

            print("METHOD 10")

            huge = cv2.resize(
                gray,
                None,
                fx=4,
                fy=4,
                interpolation=cv2.INTER_CUBIC
            )

            cv2.imwrite(
                "huge_debug.jpg",
                huge
            )

            qr_data = self.try_decode(
                detector,
                huge
            )

            if qr_data:
                return self.verify_domain(qr_data)

            # ===============================
            # QR NOT FOUND
            # ===============================

            print("QR NOT FOUND")

            return {
                "status": "NOT_FOUND",
                "is_secure": False,
                "data": None,
                "domain": None,
                "domain_authenticity": False,
                "qr_location": None
            }
        finally:

            self.cleanup_debug_files()
            
    def cleanup_debug_files(self):

        import glob
        import os

        files = []

        files.extend(glob.glob("debug_*"))
        files.extend(glob.glob("top_right_*"))
        files.extend(glob.glob("huge_*"))

        for file in files:

            try:
                os.remove(file)
                print("DELETED:", file)

            except Exception as e:
                print("DELETE ERROR:", e)