import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim


class AIVerificationEngine:

    def __init__(self, template_path: str = None):
        self.template_path = template_path
        self.orb = cv2.ORB_create(nfeatures=2000)

    def deskew(self, img: np.ndarray) -> np.ndarray:
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(
                gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
            )
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 5))
            dilated = cv2.dilate(thresh, kernel, iterations=1)

            contours, _ = cv2.findContours(
                dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            angles = []
            h, w = img.shape[:2]
            min_area = h * w * 0.001

            for cnt in contours:
                if cv2.contourArea(cnt) < min_area:
                    continue
                rect = cv2.minAreaRect(cnt)
                angle = rect[2]
                if angle < -45:
                    angle += 90
                angles.append(angle)

            if not angles:
                return img

            median_angle = float(np.median(angles))
            print(f"DESKEW: {median_angle:.2f}°")

            if abs(median_angle) < 0.5:
                return img

            centre = (w / 2.0, h / 2.0)
            M = cv2.getRotationMatrix2D(centre, median_angle, 1.0)
            return cv2.warpAffine(
                img, M, (w, h),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE,
            )
        except Exception as e:
            print("DESKEW ERROR:", e)
            return img

    def enhance(self, img: np.ndarray, is_pdf: bool = False) -> np.ndarray:
        try:
            if not is_pdf:
                h, w = img.shape[:2]
                img = cv2.resize(
                    img,
                    (int(w * 1.5), int(h * 1.5)),
                    interpolation=cv2.INTER_CUBIC,
                )
            blurred = cv2.GaussianBlur(img, (0, 0), sigmaX=2)
            sharpened = cv2.addWeighted(img, 1.5, blurred, -0.5, 0)
            print("ENHANCE: done")
            return sharpened
        except Exception as e:
            print("ENHANCE ERROR:", e)
            return img

    def align_to_template(self, input_img: np.ndarray, template_img: np.ndarray):
        gray_input = cv2.cvtColor(input_img, cv2.COLOR_BGR2GRAY)
        gray_template = cv2.cvtColor(template_img, cv2.COLOR_BGR2GRAY)

        kp1, des1 = self.orb.detectAndCompute(gray_input, None)
        kp2, des2 = self.orb.detectAndCompute(gray_template, None)

        if des1 is None or des2 is None:
            return None

        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = sorted(bf.match(des1, des2), key=lambda x: x.distance)
        good = matches[:100]

        if len(good) < 10:
            return None

        src_pts = np.float32(
            [kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst_pts = np.float32(
            [kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

        M, _ = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        if M is None:
            return None

        h, w = gray_template.shape
        return cv2.warpPerspective(input_img, M, (w, h))

    def calculate_tamper_score(self, input_img: np.ndarray, template_img: np.ndarray):
        aligned = self.align_to_template(input_img, template_img)
        if aligned is None:
            print("TAMPER: alignment failed — neutral score")
            return 0.5, 0.5

        gray_aligned = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY)
        gray_template = cv2.cvtColor(template_img, cv2.COLOR_BGR2GRAY)

        ssim_score, _ = ssim(gray_aligned, gray_template, full=True)

        _, buf = cv2.imencode(".jpg", aligned, [cv2.IMWRITE_JPEG_QUALITY, 75])
        recompressed = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
        ela_mean = float(cv2.absdiff(gray_aligned, recompressed).mean())

        lap_var = float(cv2.Laplacian(gray_aligned, cv2.CV_64F).var())

        ela_penalty = min(ela_mean / 10.0, 0.3)
        lap_bonus = min(lap_var / 5000.0, 0.1)

        tamper = float(np.clip(
            (1.0 - ssim_score) * 0.4
            + ela_penalty * 0.4
            - lap_bonus * 0.2,
            0.0,
            1.0,
        ))
        ai_score = float(np.clip(1.0 - tamper, 0.0, 1.0))

        print(f"TAMPER: ssim={ssim_score:.3f} ela={ela_mean:.2f} → tamper={tamper:.3f}")
        return ai_score, tamper
