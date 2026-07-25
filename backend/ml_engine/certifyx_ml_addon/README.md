# CertifyX ML Addon

Adds a real ML decision layer to CertifyX: a CNN (transfer-learned
MobileNetV3-Small) for image-level tamper detection, plus a RandomForest /
XGBoost classifier that makes the final genuine/suspicious/fake call using
the CNN's output combined with your existing OCR/QR/official-record signals.

## Why this design, given 5-20 real images

There's no public dataset of forged TN SSLC certificates, and you can't
ethically create real forged ones at scale. So the approach is:

1. **`augment.py` / `dataset_builder.py`** — turn your handful of genuine
   certs into hundreds of realistic "genuine" variants (scan noise,
   rotation, recompression) and hundreds of synthetically "tampered"
   variants (splice, text overwrite, seal blur, resave artifacts). This is
   an honest, explainable data strategy — say exactly this in your pitch.

2. **`train_cnn.py`** — transfer learning on that dataset. Not trained from
   scratch (impossible with this little data), fine-tunes a pretrained
   backbone, which is standard practice for small datasets.

3. **`train_tabular.py`** — extracts the SAME features your app already
   computes (SSIM/ELA tamper score, QR authenticity, per-field match
   booleans) plus the CNN's tamper probability, and trains RandomForest and
   XGBoost side by side, keeping whichever scores higher on held-out data.
   This is the actual ML decision-maker.

4. **`ml_verifier.py`** — inference wrapper for `main.py`, degrades to your
   existing hand-weighted formula if models aren't trained/available.

See `INTEGRATION.md` for exact setup steps and the `main.py` patch.

## Quick start

```bash
pip install -r requirements_additions.txt --break-system-packages

cd ml_engine
python dataset_builder.py --input /path/to/your/real_certs --output ./dataset
python train_cnn.py --data ./dataset --out cnn_tamper_model.pt
python train_tabular.py --dataset ./dataset --app-root ../../backend \
    --template ../../backend/templates/tn_10th_template.png --out tabular_model.joblib
```

Then follow `INTEGRATION.md` step 3 to wire it into `main.py`.

## What to say to judges

- "Where's the AI" → a CNN for image forensics + an ensemble classifier
  (RF/XGBoost) making the final call, not a hand-tuned formula
- "What did you train on" → real certificates augmented with realistic scan
  variance and synthetic tamper techniques (splice, overlay, seal removal,
  resave artifacts) modeling known forgery patterns — the honest answer,
  and a defensible one
- "How do you explain a decision" → `top_factors` in the API response are
  the model's own feature importances, ranked — that's a real, not
  decorative, explainability layer
