import os
import requests
import datetime
import logging
from sqlalchemy.orm import Session
from ... import models
from ...database import SessionLocal
from ...ai_service import generate_sales_reply
from ...ws_manager import manager

logger = logging.getLogger("whatsapp_service")

class WhatsAppService:
    def send_whatsapp_message(self, db: Session, settings: models.Settings, to_phone: str, text: str) -> bool:
        """Sends a text message using Meta's WhatsApp Cloud API."""
        if not settings.whatsapp_phone_number_id or not settings.whatsapp_api_key:
            logger.error("[WhatsApp] Missing configuration (Phone ID or API Key) for company %d", settings.company_id)
            return False

        phone_id = settings.whatsapp_phone_number_id.strip()
        token = settings.whatsapp_api_key.strip()
        
        # Format the phone number (strip '+' or spaces, ensure country code)
        cleaned_phone = to_phone.strip().replace("+", "").replace(" ", "").replace("-", "")

        url = f"https://graph.facebook.com/v18.0/{phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": cleaned_phone,
            "type": "text",
            "text": {
                "body": text
            }
        }

        try:
            logger.info("[WhatsApp] Sending message to %s (Phone ID: %s)", cleaned_phone, phone_id)
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            res_data = response.json()
            if response.status_code == 200 or "messages" in res_data:
                logger.info("[WhatsApp] Message successfully sent to %s", cleaned_phone)
                return True
            else:
                logger.error("[WhatsApp] Error response from Meta: %s", res_data)
                return False
        except Exception as e:
            logger.error("[WhatsApp] Failed to send API request: %s", e)
            return False

    def process_incoming_webhook(self, data: dict):
        """Parses Meta incoming Webhook payloads and routes them to customer conversations."""
        # Validate structure
        if not data.get("object") == "whatsapp_business_account":
            return
            
        entries = data.get("entry", [])
        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                metadata = value.get("metadata", {})
                phone_id = metadata.get("phone_number_id")
                
                if not phone_id:
                    continue

                db = SessionLocal()
                try:
                    # Find the company settings matching this phone ID
                    settings = db.query(models.Settings).filter(
                        models.Settings.whatsapp_phone_number_id == phone_id
                    ).first()

                    if not settings:
                        logger.warning("[WhatsApp Webhook] Received message for unknown phone_number_id: %s", phone_id)
                        continue

                    company_id = settings.company_id

                    # Parse contacts
                    contacts = value.get("contacts", [])
                    contact_name = "WhatsApp Customer"
                    if contacts:
                        contact_name = contacts[0].get("profile", {}).get("name", "WhatsApp Customer")

                    # Parse messages
                    messages = value.get("messages", [])
                    for msg in messages:
                        sender_phone = msg.get("from") # E.g. "15550244123"
                        msg_type = msg.get("type")
                        
                        if msg_type != "text" or not sender_phone:
                            # We only process text messages for B2B wholesale conversation logic
                            continue
                            
                        body = msg.get("text", {}).get("body", "").strip()
                        if not body:
                            continue

                        logger.info("[WhatsApp Webhook] Incoming message from %s: '%s'", sender_phone, body[:50])

                        # 1. Find or create Customer record
                        customer = db.query(models.Customer).filter(
                            models.Customer.phone == sender_phone,
                            models.Customer.company_id == company_id
                        ).first()

                        if not customer:
                            customer = models.Customer(
                                company_id=company_id,
                                name=contact_name,
                                phone=sender_phone
                            )
                            db.add(customer)
                            db.commit()
                            db.refresh(customer)

                        # 2. Find or create Conversation
                        conversation = db.query(models.Conversation).filter(
                            models.Conversation.customer_id == customer.id,
                            models.Conversation.channel == "WhatsApp"
                        ).first()

                        if not conversation:
                            deal = models.Deal(
                                company_id=company_id,
                                customer_id=customer.id,
                                stage="New Inquiry"
                            )
                            db.add(deal)
                            db.commit()
                            db.refresh(deal)

                            conversation = models.Conversation(
                                customer_id=customer.id,
                                deal_id=deal.id,
                                channel="WhatsApp",
                                status="Open",
                                is_ai_managed=True,
                                unread=True
                            )
                            db.add(conversation)
                            db.commit()
                            db.refresh(conversation)

                        # 3. Save incoming message
                        iso_time = datetime.datetime.utcnow().isoformat() + "Z"
                        new_msg = models.Message(
                            conversation_id=conversation.id,
                            sender="customer",
                            text=body,
                            timestamp=iso_time
                        )
                        db.add(new_msg)

                        conversation.unread = True
                        conversation.last_message_text = body[:120] + ("..." if len(body) > 120 else "")
                        conversation.last_message_time = iso_time
                        conversation.status = "Open"
                        db.commit()
                        db.refresh(new_msg)

                        # Broadcast message to live Dashboard UI via WebSocket
                        msg_payload = {
                            "id": new_msg.id,
                            "sender": new_msg.sender,
                            "text": new_msg.text,
                            "timestamp": new_msg.timestamp
                        }
                        
                        # Use background task to execute async WebSocket send safely
                        import asyncio
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            loop.create_task(manager.broadcast_to_admins({
                                "type": "new_message",
                                "conversation_id": conversation.id,
                                "customer_id": customer.id,
                                "message": msg_payload
                            }))

                        # 4. Trigger AI Auto-reply if active
                        if conversation.is_ai_managed and settings.ai_enabled:
                            logger.info("[WhatsApp][AI] Generating reply for customer %s", customer.phone)
                            reply_text = generate_sales_reply(settings, customer, conversation, body, db=db)
                            
                            # Send WhatsApp message
                            sent = self.send_whatsapp_message(db, settings, customer.phone, reply_text)
                            
                            if sent:
                                ai_msg = models.Message(
                                    conversation_id=conversation.id,
                                    sender="ai" if settings.ai_auto_send else "ai_draft",
                                    text=reply_text,
                                    timestamp=datetime.datetime.utcnow().isoformat() + "Z"
                                )
                                db.add(ai_msg)
                                if settings.ai_auto_send:
                                    conversation.status = "Replied"
                                    conversation.last_message_text = reply_text[:120]
                                else:
                                    conversation.status = "Open"
                                conversation.last_message_time = ai_msg.timestamp
                                db.commit()
                                db.refresh(ai_msg)
                                
                                # Broadcast AI response to UI
                                loop.create_task(manager.broadcast_to_admins({
                                    "type": "new_message",
                                    "conversation_id": conversation.id,
                                    "customer_id": customer.id,
                                    "message": {
                                        "id": ai_msg.id,
                                        "sender": ai_msg.sender,
                                        "text": ai_msg.text,
                                        "timestamp": ai_msg.timestamp
                                    }
                                }))
                except Exception as e:
                    logger.error("[WhatsApp Webhook] DB error processing incoming webhook payload: %s", e)
                    db.rollback()
                finally:
                    db.close()

whatsapp_service = WhatsAppService()
