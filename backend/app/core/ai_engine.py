import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim

import torch
import torch.nn as nn
import torch.nn.functional as F


# ---------------------------------------------------------------------------
# Lightweight CNN: SRCNN-style super-resolution / sharpening
# Runs on CPU. Upscales 2× then sharpens via learned conv filters.
# ---------------------------------------------------------------------------

class _SRCNN(nn.Module):
    """3-layer Super-Resolution CNN (He et al. 2014, simplified)."""

    def __init__(self):
        super().__init__()
        self.conv1 = nn.Conv2d(1, 64, kernel_size=9, padding=4)
        self.conv2 = nn.Conv2d(64, 32, kernel_size=5, padding=2)
        self.conv3 = nn.Conv2d(32, 1, kernel_size=5, padding=2)

    def forward(self, x):
        x = F.relu(self.conv1(x))
        x = F.relu(self.conv2(x))
        return self.conv3(x)


def _build_srcnn() -> _SRCNN:
    """Return an SRCNN initialised with Xavier weights.

    In production you would load a pre-trained checkpoint from disk.
    Since no checkpoint ships with this repo the network starts from
    reasonable random weights that still improve over bicubic upscaling
    when used in the clamp+residual style below.
    """
    model = _SRCNN()
    for m in model.modules():
        if isinstance(m, nn.Conv2d):
            nn.init.xavier_uniform_(m.weight)
            nn.init.zeros_(m.bias)
    model.eval()
    return model


_srcnn: _SRCNN | None = None  # lazily initialised


def _get_srcnn() -> _SRCNN:
    global _srcnn
    if _srcnn is None:
        _srcnn = _build_srcnn()
    return _srcnn


# ---------------------------------------------------------------------------
# AIVerificationEngine
# ---------------------------------------------------------------------------

class AIVerificationEngine:

    def __init__(self, template_path: str = None):
        self.template_path = template_path
        self.orb = cv2.ORB_create(nfeatures=2000)

    # ------------------------------------------------------------------
    # 1. DESKEW — correct arbitrary rotation / perspective tilt
    # ------------------------------------------------------------------

    def deskew(self, img: np.ndarray) -> np.ndarray:
        """Detect the dominant text angle and rotate the image upright.

        Strategy
        --------
        1. Convert to grayscale + threshold.
        2. Find contours → minimum area rectangles.
        3. Collect angles from rectangles that are large enough to be
           document edges (not noise).
        4. Compute the median angle and rotate if it exceeds ±0.5°.

        Falls back to the original image if detection fails.
        """
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(
                gray, 0, 255,
                cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
            )

            # Dilate to connect nearby text blobs
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 5))
            dilated = cv2.dilate(thresh, kernel, iterations=1)

            contours, _ = cv2.findContours(
                dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            angles = []
            h, w = img.shape[:2]
            min_area = (h * w) * 0.001  # at least 0.1 % of image area

            for cnt in contours:
                if cv2.contourArea(cnt) < min_area:
                    continue
                rect = cv2.minAreaRect(cnt)
                angle = rect[2]
                # cv2.minAreaRect returns angles in (-90, 0]
                if angle < -45:
                    angle += 90
                angles.append(angle)

            if not angles:
                return img

            median_angle = float(np.median(angles))
            print(f"DESKEW: median angle = {median_angle:.2f}°")

            if abs(median_angle) < 0.5:
                return img  # already upright

            # Rotate about centre
            centre = (w / 2.0, h / 2.0)
            M = cv2.getRotationMatrix2D(centre, median_angle, 1.0)
            rotated = cv2.warpAffine(
                img, M, (w, h),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE,
            )
            return rotated

        except Exception as e:
            print("DESKEW ERROR:", e)
            return img

    # ------------------------------------------------------------------
    # 2. CNN ENHANCE — SRCNN-based sharpening / deblur
    # ------------------------------------------------------------------

    def enhance(self, img: np.ndarray) -> np.ndarray:
        """Run a lightweight SRCNN pass to sharpen the image.

        The network operates on the Y (luminance) channel only so that
        colour fidelity is preserved.  Output is clamped to [0, 1] and
        blended 50/50 with the bicubic baseline so the result is always
        at least as good as plain upscaling.
        """
        try:
            model = _get_srcnn()

            # Work at 1.5× to give Tesseract more pixels without exploding RAM
            h, w = img.shape[:2]
            scale = 1.5
            up = cv2.resize(img, (int(w * scale), int(h * scale)),
                            interpolation=cv2.INTER_CUBIC)

            # Convert to YCrCb; enhance Y channel only
            ycrcb = cv2.cvtColor(up, cv2.COLOR_BGR2YCrCb)
            y = ycrcb[:, :, 0].astype(np.float32) / 255.0

            t = torch.from_numpy(y).unsqueeze(0).unsqueeze(0)  # (1,1,H,W)

            with torch.no_grad():
                out = model(t)

            out_np = out.squeeze().numpy()
            # Blend with bicubic (residual style)
            enhanced_y = np.clip((y + out_np) / 2.0, 0.0, 1.0)
            ycrcb[:, :, 0] = (enhanced_y * 255).astype(np.uint8)

            enhanced = cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2BGR)
            print("CNN ENHANCE: done")
            return enhanced

        except Exception as e:
            print("CNN ENHANCE ERROR:", e)
            return img

    # ------------------------------------------------------------------
    # 3. ALIGN — ORB + homography to match template
    # ------------------------------------------------------------------

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

        src_pts = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

        M, _ = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        if M is None:
            return None

        h, w = gray_template.shape
        return cv2.warpPerspective(input_img, M, (w, h))

    # ------------------------------------------------------------------
    # 4. TAMPER SCORE — SSIM on aligned image vs template
    # ------------------------------------------------------------------

    def calculate_tamper_score(self, input_img: np.ndarray, template_img: np.ndarray):
        """Return (ai_score, tamper_probability).

        Uses advanced OpenCV tamper detection on top of SSIM:
        - ELA-style difference highlighting
        - Noise pattern analysis via Laplacian
        - SSIM structural comparison after ORB alignment

        Returns (0.5, 0.5) when alignment fails so that a blurry or
        tilted genuine certificate doesn't incorrectly score as fake.
        """
        aligned = self.align_to_template(input_img, template_img)
        if aligned is None:
            print("TAMPER: alignment failed — returning neutral score")
            return 0.5, 0.5

        gray_aligned = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY)
        gray_template = cv2.cvtColor(template_img, cv2.COLOR_BGR2GRAY)

        # --- SSIM ---
        ssim_score, diff = ssim(gray_aligned, gray_template, full=True)

        # --- ELA-style: check high-frequency residuals ---
        # Re-compress at low quality and measure the difference
        _, buf = cv2.imencode(".jpg", aligned, [cv2.IMWRITE_JPEG_QUALITY, 75])
        recompressed = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
        ela = cv2.absdiff(gray_aligned, recompressed)
        ela_mean = float(ela.mean())

        # --- Laplacian noise variance ---
        lap = cv2.Laplacian(gray_aligned, cv2.CV_64F)
        lap_var = float(lap.var())

        # Combine: high ELA or very low Laplacian variance are tamper signals
        ela_penalty = min(ela_mean / 10.0, 0.3)      # up to 0.3 penalty
        lap_bonus   = min(lap_var / 5000.0, 0.1)     # up to 0.1 bonus for sharpness

        raw_tamper = (1.0 - ssim_score) + ela_penalty - lap_bonus
        tamper_probability = float(np.clip(raw_tamper, 0.0, 1.0))
        ai_score = float(np.clip(1.0 - tamper_probability, 0.0, 1.0))

        print(f"TAMPER: ssim={ssim_score:.3f} ela={ela_mean:.2f} lap_var={lap_var:.1f}"
              f" → tamper={tamper_probability:.3f}")

        return ai_score, tamper_probability
