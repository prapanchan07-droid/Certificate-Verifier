from fastapi import APIRouter, UploadFile, File

from app.services.sslc_service import SSLCVerificationService
from app.services.hsc_service import HSCVerificationService

router = APIRouter(
    prefix="/api/academic",
    tags=["Academic Documents"]
)

sslc_service = SSLCVerificationService()
hsc_service = HSCVerificationService()

@router.post("/sslc")
async def verify_sslc(
    file: UploadFile = File(...)
):
    return await sslc_service.verify(file)

@router.post("/hsc")
async def verify_hsc(
    file: UploadFile = File(...)
):
    return await hsc_service.verify(file)