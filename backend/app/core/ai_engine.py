import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim

class AIVerificationEngine:
    def __init__(self, template_path: str = None):
        self.template_path = template_path
        self.orb = cv2.ORB_create(nfeatures=2000)

    def align_to_template(self, input_img, template_img):

        gray_input = cv2.cvtColor(
            input_img,
            cv2.COLOR_BGR2GRAY
        )

        gray_template = cv2.cvtColor(
            template_img,
            cv2.COLOR_BGR2GRAY
        )

        kp1, des1 = self.orb.detectAndCompute(
            gray_input,
            None
        )

        kp2, des2 = self.orb.detectAndCompute(
            gray_template,
            None
        )

        if des1 is None or des2 is None:
            return None

        bf = cv2.BFMatcher(
            cv2.NORM_HAMMING,
            crossCheck=True
        )

        matches = bf.match(
            des1,
            des2
        )

        matches = sorted(
            matches,
            key=lambda x: x.distance
        )

        good_matches = matches[:100]

        if len(good_matches) < 10:
            return None

        src_pts = np.float32(
            [
                kp1[m.queryIdx].pt
                for m in good_matches
            ]
        ).reshape(-1, 1, 2)

        dst_pts = np.float32(
            [
                kp2[m.trainIdx].pt
                for m in good_matches
            ]
        ).reshape(-1, 1, 2)

        M, mask = cv2.findHomography(
            src_pts,
            dst_pts,
            cv2.RANSAC,
            5.0
        )

        if M is None:
            return None

        h, w = gray_template.shape

        aligned_img = cv2.warpPerspective(
            input_img,
            M,
            (w, h)
        )

        return aligned_img

    def calculate_tamper_score(self, input_img, template_img):
        """Calculates structural variation to identify anomaly/tampering locations."""
        aligned = self.align_to_template(input_img, template_img)
        if aligned is None:
            return 0.0, 1.0  # No structural match -> High tampering probability

        gray_aligned = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY)
        gray_template = cv2.cvtColor(template_img, cv2.COLOR_BGR2GRAY)

        # Compute Structural Similarity Index (SSIM)
        score, diff = ssim(gray_aligned, gray_template, full=True)
        tamper_probability = 1.0 - score
        return float(score), float(tamper_probability)

    def verify_features(self, img):
        """Placeholder for fine-tuned Keras model evaluating deep layout authenticity."""
        # Genuine vs structural fake classifier validation score mock
        return 0.89