"""
Extract tabular features from the dataset/ folder (built by dataset_builder.py)
and train RandomForest + XGBoost final-decision classifiers. Keeps whichever
scores better on held-out data.

This reuses your EXISTING app.core modules (ai_engine, ocr_engine, qr_engine,
official_verifier) so the features here are exactly what production will see
at inference time — no train/serve skew.

Usage:
    python train_tabular.py --dataset ./dataset --app-root ../backend --template ../backend/templates/tn_10th_template.png --out tabular_model.joblib

Optional --use-official-check makes a REAL network call to the government
verification site for every training image (to get real roll/name/marks/
institution match booleans). This is the most informative signal but is
slow (one HTTP request per image) and only works for the genuine-derived
variants whose QR still decodes. Off by default.

Requires: scikit-learn, xgboost, joblib, pandas
    pip install scikit-learn xgboost joblib pandas --break-system-packages
"""

import argparse
import os
import sys
import glob
import cv2
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, accuracy_score, classification_report
import joblib

from ml_verifier import MLVerifier, FEATURE_NAMES


def load_app_modules(app_root: str):
    sys.path.insert(0, app_root)
    from app.core.ai_engine import AIVerificationEngine
    from app.core.ocr_engine import OCREngine
    from app.core.qr_engine import QREngine
    from app.core.official_verifier import OfficialVerifier
    return AIVerificationEngine(), OCREngine(), QREngine(), OfficialVerifier()


def extract_row(path, label, ai_engine, ocr_engine, qr_engine, official_verifier,
                 template, ml_verifier, use_official_check):
    img = cv2.imread(path)
    if img is None:
        return None

    ai_score, tamper_score = ai_engine.calculate_tamper_score(img, template)

    qr_results = qr_engine.scan_and_verify(img)

    success, encoded = cv2.imencode(".png", img)
    ocr_results = ocr_engine.extract_details(encoded.tobytes())

    comparison = None
    if use_official_check and qr_results.get("data") and qr_results.get("domain_authenticity"):
        try:
            official_data = official_verifier.extract_official_data(qr_results["data"])
            if official_data.get("success"):
                comparison = official_verifier.compare_records(ocr_results, official_data)
        except Exception as e:
            print("  official check failed:", e)

    features = ml_verifier.build_features(
        img, ai_score, tamper_score, qr_results, comparison, ocr_results
    )
    features["label"] = label
    features["path"] = path
    return features


def main(dataset_dir, app_root, template_path, out_path, use_official_check):
    ai_engine, ocr_engine, qr_engine, official_verifier = load_app_modules(app_root)
    template = cv2.imread(template_path)
    if template is None:
        raise SystemExit(f"Could not load template image at {template_path}")

    # ml_verifier only used here for its build_features() + cnn_tamper_prob();
    # if cnn_tamper_model.pt doesn't exist yet, cnn_tamper_prob() returns a
    # neutral 0.5 for every row -- train the CNN first for a real signal.
    ml_verifier = MLVerifier()
    if ml_verifier._cnn is None:
        print("WARNING: no trained CNN found — cnn_tamper_prob will be neutral (0.5) "
              "for all rows. Run train_cnn.py first for a real signal.")

    rows = []
    for label, subdir in [(0, "genuine"), (1, "tampered")]:
        paths = glob.glob(os.path.join(dataset_dir, subdir, "*"))
        print(f"Processing {len(paths)} {subdir} images...")
        for i, p in enumerate(paths):
            row = extract_row(p, label, ai_engine, ocr_engine, qr_engine,
                               official_verifier, template, ml_verifier, use_official_check)
            if row:
                rows.append(row)
            if (i + 1) % 25 == 0:
                print(f"  {i+1}/{len(paths)}")

    df = pd.DataFrame(rows)
    print("\nDataset shape:", df.shape)
    print(df["label"].value_counts())

    X = df[FEATURE_NAMES]
    y = df["label"]
    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )

    candidates = {}

    rf = RandomForestClassifier(
        n_estimators=300, max_depth=8, min_samples_leaf=3,
        class_weight="balanced", random_state=42,
    )
    rf.fit(X_train, y_train)
    candidates["random_forest"] = rf

    try:
        from xgboost import XGBClassifier
        xgb = XGBClassifier(
            n_estimators=300, max_depth=4, learning_rate=0.05,
            eval_metric="logloss", random_state=42,
        )
        xgb.fit(X_train, y_train)
        candidates["xgboost"] = xgb
    except ImportError:
        print("xgboost not installed — skipping (pip install xgboost --break-system-packages)")

    print("\n--- Model comparison ---")
    best_name, best_model, best_auc = None, None, -1
    for name, model in candidates.items():
        proba = model.predict_proba(X_val)[:, 1]
        preds = model.predict(X_val)
        auc = roc_auc_score(y_val, proba)
        acc = accuracy_score(y_val, preds)
        print(f"\n{name}: AUC={auc:.3f} ACC={acc:.3f}")
        print(classification_report(y_val, preds, target_names=["genuine", "tampered"]))
        if auc > best_auc:
            best_name, best_model, best_auc = name, model, auc

    print(f"\nBest model: {best_name} (AUC={best_auc:.3f}) -> saving to {out_path}")
    joblib.dump(best_model, out_path)

    print("\nFeature importances:")
    for name, imp in sorted(zip(FEATURE_NAMES, best_model.feature_importances_),
                             key=lambda x: -x[1]):
        print(f"  {name:28s} {imp:.4f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, help="Folder with genuine/ and tampered/ subfolders")
    ap.add_argument("--app-root", required=True, help="Path to your backend/ folder (contains app/)")
    ap.add_argument("--template", required=True, help="Path to tn_10th_template.png")
    ap.add_argument("--out", default="tabular_model.joblib")
    ap.add_argument("--use-official-check", action="store_true",
                     help="Make real network calls to the govt verification site during training (slow)")
    args = ap.parse_args()
    main(args.dataset, args.app_root, args.template, args.out, args.use_official_check)
