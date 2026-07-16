import json
import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session
from ...database import get_db
from ... import models, schemas
from ...ws_manager import manager
from pydantic import BaseModel

class StartChatRequest(BaseModel):
    name: str
    email: str

router = APIRouter(prefix="/integrations/website", tags=["Website Chat Integration"])

@router.post("/start_chat")
def start_chat(req: StartChatRequest, db: Session = Depends(get_db)):
    # Create a new customer record for this visitor
    company = db.query(models.Company).first()
    if not company:
        company = models.Company(name="Default Company")
        db.add(company)
        db.commit()

    customer = models.Customer(
        company_id=company.id,
        name=req.name,
        email=req.email
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    
    # Create the conversation
    # Create a Deal
    deal = models.Deal(
        company_id=company.id,
        customer_id=customer.id,
        stage="New Inquiry"
    )
    db.add(deal)
    db.commit()
    db.refresh(deal)

    conversation = models.Conversation(
        customer_id=customer.id,
        deal_id=deal.id,
        channel="Website",
        status="New",
        unread=False
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    
    return {"customer_id": customer.id, "conversation_id": conversation.id}

@router.websocket("/ws/{customer_id}")
async def websocket_endpoint(websocket: WebSocket, customer_id: int, db: Session = Depends(get_db)):
    # Verify customer exists
    customer = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    if not customer:
        await websocket.close()
        return

    await manager.connect_customer(websocket, customer_id)
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            text = message_data.get("text", "")
            
            if not text:
                continue

            # Find or create conversation
            conversation = db.query(models.Conversation).filter(
                models.Conversation.customer_id == customer_id,
                models.Conversation.channel == "Website"
            ).first()

            if not conversation:
                conversation = models.Conversation(
                    customer_id=customer_id,
                    channel="Website",
                    status="Open"
                )
                db.add(conversation)
                db.commit()
                db.refresh(conversation)
            
            # Update conversation status
            conversation.status = "Open"
            conversation.last_message_text = text
            conversation.last_message_time = datetime.datetime.utcnow().isoformat() + "Z"
            conversation.unread = True
            
            # Create message
            new_msg = models.Message(
                conversation_id=conversation.id,
                sender="customer",
                text=text,
                timestamp=conversation.last_message_time
            )
            db.add(new_msg)
            db.commit()
            db.refresh(new_msg)

            # Broadcast to admins
            await manager.broadcast_to_admins({
                "type": "new_message",
                "conversation_id": conversation.id,
                "customer_id": customer_id,
                "message": {
                    "id": new_msg.id,
                    "sender": new_msg.sender,
                    "text": new_msg.text,
                    "timestamp": new_msg.timestamp
                }
            })

            # Note: Auto-reply logic (AI) can be plugged in here if needed
            # For now, we just route messages.

    except WebSocketDisconnect:
        manager.disconnect_customer(customer_id)
