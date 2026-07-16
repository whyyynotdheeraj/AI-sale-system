from fastapi import APIRouter

router = APIRouter(prefix="/integrations/whatsapp", tags=["WhatsApp Integration"])

@router.post("/webhook")
def whatsapp_webhook():
    # Placeholder for WhatsApp Business API webhook
    return {"status": "success", "message": "WhatsApp webhook placeholder"}
