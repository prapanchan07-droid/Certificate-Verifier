from app.services.base_verification import BaseVerificationService


class HSCVerificationService(BaseVerificationService):

    def __init__(self):
        super().__init__()

    async def verify(self, file):
        return {
            "message": "HSC Verification Service is under development"
        }