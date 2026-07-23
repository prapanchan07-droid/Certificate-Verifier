"""
Synthetic data augmentation for CertifyX ML training.

With only a handful of real genuine certificates, we can't collect real
forged examples (that's the whole point of the problem). Instead we:

  1. Augment genuine images with realistic scan/camera variance
     ("genuine" class — still label 0)
  2. Programmatically tamper genuine images in ways that mimic real
     forgery techniques ("tampered" class — label 1)

This is a legitimate, defensible approach for a hackathon: judges will
ask "what data did you train on" and "synthetically augmented real
certificates" is an honest, correct answer — as opposed to claiming a
CNN trained on a forged-document dataset that doesn't exist.
"""

import cv2
import numpy as np
import random


# ---------------------------------------------------------------------
# GENUINE augmentation — simulates natural scan/photo variance.
# These must NEVER change the actual content of the certificate.
# ---------------------------------------------------------------------

def random_geometric(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    angle = random.uniform(-3, 3)
    scale = random.uniform(0.96, 1.04)
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, scale)
    out = cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REPLICATE)

    # mild perspective jitter
    src = np.float32([[0, 0], [w, 0], [0, h], [w, h]])
    jitter = w * 0.01
    dst = src + np.random.uniform(-jitter, jitter, src.shape).astype(np.float32)
    Mp = cv2.getPerspectiveTransform(src, dst)
    out = cv2.warpPerspective(out, Mp, (w, h), borderMode=cv2.BORDER_REPLICATE)
    return out


def simulate_recapture(img: np.ndarray) -> np.ndarray:
    out = img.copy().astype(np.float32)

    # brightness / contrast jitter -- narrower range
    alpha = random.uniform(0.92, 1.08)
    beta = random.uniform(-8, 8)
    out = np.clip(out * alpha + beta, 0, 255)

    # gaussian noise (sensor noise) -- lower ceiling, keeps text legible
    noise = np.random.normal(0, random.uniform(1, 3), out.shape)
    out = np.clip(out + noise, 0, 255).astype(np.uint8)

    # mild blur -- rarer, smallest kernel only
    if random.random() < 0.2:
        out = cv2.GaussianBlur(out, (3, 3), 0)

    # single JPEG recompression -- higher quality floor
    q = random.randint(80, 95)
    _, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, q])
    out = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    return out


def make_genuine_variant(img: np.ndarray) -> np.ndarray:
    out = img
    if random.random() < 0.8:
        out = random_geometric(out)
    out = simulate_recapture(out)
    return out


# ---------------------------------------------------------------------
# TAMPERED synthesis — mimics real forgery techniques seen on doctored
# certificates: field splicing, text overwrite, seal removal, resave
# artifacts from photo-editing tools.
# ---------------------------------------------------------------------

def tamper_splice(img: np.ndarray) -> np.ndarray:
    """Copy a rectangular patch from elsewhere in the image and paste it
    over another region — simulates copy-paste field forgery."""
    out = img.copy()
    h, w = out.shape[:2]
    pw, ph = int(w * random.uniform(0.12, 0.25)), int(h * random.uniform(0.03, 0.06))

    def rand_box():
        x = random.randint(0, max(1, w - pw))
        y = random.randint(0, max(1, h - ph))
        return x, y

    sx, sy = rand_box()
    dx, dy = rand_box()
    patch = out[sy:sy + ph, sx:sx + pw].copy()
    if patch.size == 0:
        return out
    # slight resize mismatch, a common tell in real splices
    patch = cv2.resize(patch, (pw, ph))
    out[dy:dy + ph, dx:dx + pw] = patch
    return out


def tamper_text_overlay(img: np.ndarray) -> np.ndarray:
    """Overwrite a field region with new text in a mismatched font —
    simulates altering a name / roll number / marks value."""
    out = img.copy()
    h, w = out.shape[:2]
    x = random.randint(int(w * 0.15), int(w * 0.55))
    y = random.randint(int(h * 0.35), int(h * 0.75))
    box_w, box_h = int(w * 0.22), int(h * 0.035)

    # blank out the region with a sampled background color first
    bg = out[max(0, y - 2):y, x:x + box_w]
    fill = tuple(int(v) for v in bg.mean(axis=(0, 1))) if bg.size else (255, 255, 255)
    cv2.rectangle(out, (x, y), (x + box_w, y + box_h), fill, -1)

    fake_text = "".join(random.choices("0123456789", k=random.randint(3, 7)))
    cv2.putText(out, fake_text, (x + 2, y + box_h - 3),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (30, 30, 30), 1, cv2.LINE_AA)
    return out


def tamper_seal_or_qr(img: np.ndarray) -> np.ndarray:
    """Blur or blank a security element region (seal / QR corner) —
    simulates forgery attempts that damage or remove verification marks."""
    out = img.copy()
    h, w = out.shape[:2]
    # top-right corner, where QR/seal usually sits on these certs
    x0, y0 = int(w * 0.62), int(h * 0.02)
    x1, y1 = int(w * 0.98), int(h * 0.30)
    region = out[y0:y1, x0:x1]
    if region.size == 0:
        return out
    if random.random() < 0.5:
        region = cv2.GaussianBlur(region, (25, 25), 0)
    else:
        region[:] = 255
    out[y0:y1, x0:x1] = region
    return out


def tamper_double_compress(img: np.ndarray) -> np.ndarray:
    """Resave-at-low-quality twice with an intermediate resize — the
    classic artifact left by photo editors (Photoshop/GIMP round trip)."""
    out = img.copy()
    h, w = out.shape[:2]
    _, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 40])
    out = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    out = cv2.resize(out, (int(w * 0.9), int(h * 0.9)))
    out = cv2.resize(out, (w, h))
    _, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 55])
    out = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    return out


_TAMPER_FNS = [tamper_splice, tamper_text_overlay, tamper_seal_or_qr, tamper_double_compress]


def make_tampered_variant(img: np.ndarray) -> np.ndarray:
    out = img
    # apply 1-2 tamper techniques stacked, like a real forger would
    n = random.choice([1, 1, 2])
    for fn in random.sample(_TAMPER_FNS, n):
        out = fn(out)
    # tampered documents still get rescanned/rephotographed afterward
    if random.random() < 0.7:
        out = simulate_recapture(out)
    return out
