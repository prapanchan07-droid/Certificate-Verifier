"""
Inference-time ML verifier. Wraps the trained CNN (image-level tamper
probability) and the trained tabular classifier (final genuine/fake
decision using CNN score + your existing CV/OCR/QR signals).

Import this from main.py. It degrades gracefully: if model files are
missing (e.g. not trained yet), .available is False and main.py should
fall back to the existing hand-weighted formula.
"""

from __future__ import annotations
import os
import numpy as np
import cv2
import joblib
import pandas as pd
from typing import Optional


_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CNN_PATH = os.path.join(_HERE, "cnn_tamper_model.pt")
DEFAULT_TABULAR_PATH = os.path.join(_HERE, "tabular_model.joblib")

# Feature order MUST match train_tabular.py's FEATURE_NAMES exactly.
FEATURE_NAMES = [
    "ai_score",
    "tamper_score",
    "cnn_tamper_prob",
    "qr_present",
    "qr_authentic",
    "qr_secure",
    "roll_no_match",
    "reg_no_match",
    "candidate_name_match",
    "total_marks_match",
    "institution_match",
    "ocr_fields_extracted",
    "laplacian_var_norm",
]


class MLVerifier:
    def __init__(self, cnn_path=DEFAULT_CNN_PATH, tabular_path=DEFAULT_TABULAR_PATH):
        self.available = False
        self._cnn = None
        self._cnn_transform = None
        self._device = None
        self.tabular_model = None

        try:
            import torch
            from torchvision import models, transforms

            if os.path.exists(cnn_path):
                self._device = torch.device("cpu")  # CPU inference on Render
                ckpt = torch.load(cnn_path, map_location=self._device)
                model = models.mobilenet_v3_small(weights=None)
                in_features = model.classifier[-1].in_features
                model.classifier[-1] = torch.nn.Linear(in_features, 2)
                model.load_state_dict(ckpt["state_dict"])
                model.eval()
                self._cnn = model
                self._cnn_transform = transforms.Compose([
                    transforms.ToTensor(),
                    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                         std=[0.229, 0.224, 0.225]),
                ])
                self._torch = torch
        except Exception as e:
            print("ML CNN load skipped:", e)

        try:
            if os.path.exists(tabular_path):
                self.tabular_model = joblib.load(tabular_path)
        except Exception as e:
            print("ML tabular load skipped:", e)

        self.available = self._cnn is not None and self.tabular_model is not None

    def cnn_tamper_prob(self, img: np.ndarray) -> float:
        """Returns P(tampered) in [0,1] from the CNN, or 0.5 (neutral) if unavailable."""
        if self._cnn is None:
            return 0.5
        import cv2 as _cv2
        resized = _cv2.resize(img, (224, 224))
        rgb = _cv2.cvtColor(resized, _cv2.COLOR_BGR2RGB)
        tensor = self._cnn_transform(rgb).unsqueeze(0)
        with self._torch.no_grad():
            logits = self._cnn(tensor)
            prob = self._torch.softmax(logits, dim=1)[0, 1].item()  # class 1 = tampered
        return float(prob)

    def build_features(
        self,
        img: np.ndarray,
        ai_score: float,
        tamper_score: float,
        qr_results: dict,
        comparison: Optional[dict],
        ocr_results: dict,
    ) -> dict:
        cnn_prob = self.cnn_tamper_prob(img)

        checks = comparison["checks"] if comparison else {}
        ocr_fields = sum(
            1 for k in ("candidate_name", "roll_no", "reg_no", "total_marks", "institution")
            if ocr_results.get(k)
        )

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        lap_norm = min(lap_var / 2000.0, 1.0)

        return {
            "ai_score": ai_score,
            "tamper_score": tamper_score,
            "cnn_tamper_prob": cnn_prob,
            "qr_present": 1.0 if qr_results.get("data") else 0.0,
            "qr_authentic": 1.0 if qr_results.get("domain_authenticity") else 0.0,
            "qr_secure": 1.0 if qr_results.get("is_secure") else 0.0,
            "roll_no_match": 1.0 if checks.get("roll_no_match") else 0.0,
            "reg_no_match": 1.0 if checks.get("reg_no_match") else 0.0,
            "candidate_name_match": 1.0 if checks.get("candidate_name_match") else 0.0,
            "total_marks_match": 1.0 if checks.get("total_marks_match") else 0.0,
            "institution_match": 1.0 if checks.get("institution_match") else 0.0,
            "ocr_fields_extracted": ocr_fields / 5.0,
            "laplacian_var_norm": lap_norm,
        }

    def predict(self, features: dict):
        """Returns (verdict, probability_genuine, sorted_feature_contributions)."""

        feature_df = pd.DataFrame(
            [[features[name] for name in FEATURE_NAMES]],
            columns=FEATURE_NAMES
        )
        
        print("=" * 60)
        print("FEATURE VECTOR")
        for col in FEATURE_NAMES:
            print(f"{col:25}: {feature_df.iloc[0][col]}")
        print("=" * 60)

        proba = self.tabular_model.predict_proba(feature_df)[0]

        print("=" * 50)
        print("predict_proba:", proba)
        print("sum:", np.sum(proba))
        print("type:", type(proba))
        print("=" * 50)

        p_tampered = float(proba[1])
        p_genuine = float(proba[0])
        
        print(self.tabular_model.classes_)

        if p_tampered >= 0.65:
            verdict = "FAKE"
        elif p_tampered >= 0.35:
            verdict = "SUSPICIOUS"
        else:
            verdict = "GENUINE"

        contributions = self._explain(features)

        return (
            verdict,
            p_genuine,
            contributions,
            features["cnn_tamper_prob"],
            p_genuine,
        )

    def _explain(self, features: dict):
        """Feature-importance-weighted contributions, for the explainability layer."""
        importances = getattr(self.tabular_model, "feature_importances_", None)
        if importances is None:
            return []
        scored = []
        for name, importance in zip(FEATURE_NAMES, importances):
            value = features[name]
            # for match/boolean features, low value with high importance = red flag
            scored.append({
                "feature": name,
                "value": round(value, 3),
                "importance": round(float(importance), 3),
            })
        scored.sort(key=lambda x: x["importance"], reverse=True)
        return scored[:6]
