# CertifyX — Certificate Verification

AI-powered Tamil Nadu SSLC & HSC certificate verification.

## Project structure

```
certifyx/
├── backend/          ← FastAPI  (deploy to Render)
│   ├── app/
│   │   ├── main.py
│   │   └── core/
│   │       ├── ai_engine.py        ← deskew + CNN enhance + SSIM tamper
│   │       ├── ocr_engine.py       ← Tesseract OCR (eng+tam)
│   │       ├── qr_engine.py        ← 10-method QR scanner
│   │       ├── official_verifier.py
│   │       └── report_generator.py
│   ├── templates/
│   │   └── tn_10th_template.png   ← ⚠ ADD THIS FILE MANUALLY
│   ├── Dockerfile
│   ├── render.yaml
│   └── requirements.txt
└── frontend/         ← React + Vite  (deploy to Vercel)
    ├── src/
    │   ├── components/
    │   └── lib/api.js
    ├── vercel.json
    └── vite.config.js
```

---

## Backend → Render

### One-time setup

1. Push to GitHub (the `backend/` folder as its own repo root, or monorepo).
2. Go to [render.com](https://render.com) → **New → Web Service**.
3. Connect your repo. Set:
   - **Runtime**: Docker
   - **Dockerfile path**: `./Dockerfile`
4. Under **Environment Variables** add:
   | Key | Value |
   |-----|-------|
   | `ALLOWED_ORIGINS` | `https://your-app.vercel.app` |
   | `POPPLER_PATH` | *(leave blank — system poppler is installed)* |
5. Click **Deploy**.

### Template image

Upload `tn_10th_template.png` to the `templates/` folder in your repo.
The backend reads it at `templates/tn_10th_template.png` relative to the
`backend/` root. Without it the AI score defaults to neutral (0.5, 0.5).

---

## Frontend → Vercel

1. Push `frontend/` to GitHub.
2. Go to [vercel.com](https://vercel.com) → **New Project** → import repo.
3. Framework: **Vite** (auto-detected).
4. Under **Environment Variables** add:
   | Key | Value |
   |-----|-------|
   | `VITE_API_BASE_URL` | `https://your-backend.onrender.com` |
5. Click **Deploy**.

---

## Local development

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend (separate terminal)
cd frontend
npm install
npm run dev        # proxies /api → localhost:8000 via vite.config.js
```

---

## What the AI pipeline does

| Step | Tool | Purpose |
|------|------|---------|
| **Deskew** | OpenCV contour analysis | Detect & correct rotation/tilt |
| **CNN Enhance** | SRCNN (PyTorch, CPU) | Sharpen + upscale before OCR |
| **QR scan** | OpenCV (10 methods) | Locate & decode board QR code |
| **OCR** | Tesseract eng+tam | Extract name, roll, reg, marks, school |
| **Official check** | requests + BeautifulSoup | Compare OCR vs board website |
| **Tamper detect** | ORB align + SSIM + ELA + Laplacian | Structural & noise-pattern analysis |

---

## Known limitations

- The SRCNN ships with **random weights** (no pre-trained checkpoint in this
  repo). It still improves sharpness over bicubic but will benefit greatly
  from fine-tuning on real certificate scans.
- HSC mark certificates use a different layout; add an `tn_12th_template.png`
  and extend `main.py` to select the right template by certificate type.
