from fastapi import FastAPI, Body, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.core.report_generator import generate_pdf_report
from app.routers.academic import router as academic_router

app = FastAPI(
    title="CertifyX - Certificate Verification API",
    version="2.0"
)

app.include_router(academic_router)

ALLOWED_ORIGINS = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def health():
    return {
        "status": "ok",
        "service": "CertifyX",
        "document_supported": ["SSLC"],
        "version": "2.0",
        "sslc_ml_available": academic_router.sslc_service.ml_verifier.available,
    }

@app.post("/api/report")
async def download_report(data: dict = Body(...)):
    try:
        pdf_buffer = generate_pdf_report(data)

        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition":
                "attachment; filename=verification_report.pdf"
            },
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )