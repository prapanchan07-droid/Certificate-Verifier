"""
Build a labeled image dataset from a small folder of genuine certificates.

Usage:
    python dataset_builder.py --input ./real_certs --output ./dataset --per-image 25

Expects --input to contain your 5-20 real genuine certificate images
(jpg/png). Produces:

    dataset/
      genuine/   *.jpg   (label 0)
      tampered/  *.jpg   (label 1)

Run this BEFORE train_cnn.py and train_tabular.py.
"""

import argparse
import os
import cv2
from augment import make_genuine_variant, make_tampered_variant

IMG_EXTS = (".jpg", ".jpeg", ".png")


def build(input_dir: str, output_dir: str, per_image: int):
    genuine_dir = os.path.join(output_dir, "genuine")
    tampered_dir = os.path.join(output_dir, "tampered")
    os.makedirs(genuine_dir, exist_ok=True)
    os.makedirs(tampered_dir, exist_ok=True)

    files = [f for f in os.listdir(input_dir) if f.lower().endswith(IMG_EXTS)]
    if not files:
        raise SystemExit(f"No images found in {input_dir}")

    print(f"Found {len(files)} source images. Generating {per_image} variants "
          f"each for genuine + tampered classes...")

    count_g, count_t = 0, 0
    for fname in files:
        path = os.path.join(input_dir, fname)
        img = cv2.imread(path)
        if img is None:
            print(f"  skip (unreadable): {fname}")
            continue
        stem = os.path.splitext(fname)[0]

        # keep one untouched original in the genuine set
        cv2.imwrite(os.path.join(genuine_dir, f"{stem}_orig.jpg"), img)
        count_g += 1

        for i in range(per_image):
            g = make_genuine_variant(img)
            cv2.imwrite(os.path.join(genuine_dir, f"{stem}_g{i}.jpg"), g)
            count_g += 1

            t = make_tampered_variant(img)
            cv2.imwrite(os.path.join(tampered_dir, f"{stem}_t{i}.jpg"), t)
            count_t += 1

    print(f"Done. genuine={count_g} tampered={count_t}  -> {output_dir}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Folder of real genuine certificate images")
    ap.add_argument("--output", default="./dataset", help="Output dataset folder")
    ap.add_argument("--per-image", type=int, default=25, help="Variants to generate per source image, per class")
    args = ap.parse_args()
    build(args.input, args.output, args.per_image)
