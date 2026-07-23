# Wiring the ML models into `main.py`

## 1. Where files go

Copy the `ml_engine/` folder into your backend, next to `app/`:

```
backend/
├── app/
│   ├── main.py
│   └── core/...
├── ml_engine/              ← this folder
│   ├── augment.py
│   ├── dataset_builder.py
│   ├── train_cnn.py
│   ├── train_tabular.py
│   ├── ml_verifier.py
│   ├── cnn_tamper_model.pt        ← produced by train_cnn.py
│   └── tabular_model.joblib       ← produced by train_tabular.py
├── Dockerfile
└── requirements.txt
```

## 2. Training order (run locally, not in Docker)

```bash
cd backend/ml_engine

# 1. Turn your 5-20 real certs into a labeled dataset
python dataset_builder.py --input /path/to/real_certs --output ./dataset --per-image 25

# 2. Train the CNN first (tabular model uses its output as a feature)
python train_cnn.py --data ./dataset --epochs 12 --out cnn_tamper_model.pt

# 3. Train RandomForest + XGBoost, auto-picks the better one
python train_tabular.py --dataset ./dataset --app-root .. \
    --template ../templates/tn_10th_template.png --out tabular_model.joblib
```

Commit `cnn_tamper_model.pt` and `tabular_model.joblib` to the repo (or
upload them as part of the Render deploy) — they're the trained weights,
not something regenerated at runtime.

## 3. Patch `main.py`

Add near the top, with the other engine initializations:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ml_engine"))
from ml_verifier import MLVerifier

ml_verifier = MLVerifier()  # .available is False if models aren't trained yet
```

Then, inside `verify_certificate`, right after the existing confidence /
final_verdict block (after `ai_score, tamper_score = ai_engine.calculate_tamper_score(...)`
and the QR/official-record checks are computed), add:

```python
ml_block = None
if ml_verifier.available:
    features = ml_verifier.build_features(
        img, ai_score, tamper_score, qr_results, comparison, ocr_results
    )
    ml_verdict, ml_confidence, contributions = ml_verifier.predict(features)
    ml_block = {
        "verdict": ml_verdict,
        "confidence": round(ml_confidence * 100),
        "top_factors": contributions,   # feed straight into your XAI display
    }
    # Let the trained model be the final decision-maker when available,
    # but keep your existing formula as the fallback/sanity-check.
    final_verdict = ml_verdict
    confidence = ml_block["confidence"]
```

And add `"ml_verification": ml_block` to the returned response dict, so the
frontend can show a "Model reasoning" panel (top_factors is already sorted
by feature importance — that's your explainability layer for free).

**Important**: keep the existing hand-weighted formula code in place as the
`else` path. If `ml_verifier.available` is `False` (models missing, e.g. a
fresh clone before training), the app must keep working exactly as it does
today. Never let a missing model file break the endpoint.

## 4. Add the natural-language explanation (Gemini)

Set your key as an environment variable — locally in a `.env` you don't
commit, and in Render under Environment Variables:

```
GEMINI_API_KEY=your-key-here
```

Import it alongside `MLVerifier` in `main.py`:

```python
from explanation_engine import explain_verdict
```

Right after the `ml_block` is built (step 3 above), add:

```python
if ml_block:
    explanation = explain_verdict(
        verdict=ml_block["verdict"],
        confidence=ml_block["confidence"],
        checks=comparison["checks"] if comparison else {},
        qr_authentic=qr_results.get("domain_authenticity", False),
        tamper_score=tamper_score,
        top_factors=ml_block["top_factors"],
        ocr_results=ocr_results,
    )
    ml_block["explanation"] = explanation["explanation"]
    ml_block["explanation_source"] = explanation["source"]  # "gemini" or "template"
```

`explain_verdict` never raises and never blocks the response — if the API
key is missing or the request fails, it silently falls back to a
template-built sentence from the same raw signals, so `explanation_source`
lets you see in the UI (or your own testing) which path was used. Show
`ml_block["explanation"]` directly under the verdict in the frontend —
that's your "why" answer to judges instead of a bare percentage.

## 4. Deploying the CNN on Render

`torch` + `torchvision` (CPU wheels) add real weight to the Docker image and
to memory at boot — on Render's free tier this can be tight alongside
OpenCV, Tesseract, and Poppler already in the image. If the container starts
OOMing, the two off-ramps are: switch to `torch` CPU-only wheels explicitly
in `requirements.txt` (`--index-url https://download.pytorch.org/whl/cpu`),
or move the CNN inference to a separate lightweight worker/route so the
main API doesn't pay its memory cost when the model isn't needed.
