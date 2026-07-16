import os
from dotenv import load_dotenv

load_dotenv()
import datetime
import hashlib
import secrets
from fastapi import FastAPI, Depends, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional

from .database import engine, Base, get_db
from . import models, schemas
from .ws_manager import manager

# Import Integrations
from .integrations.email.service import email_service
from .integrations.website.router import router as website_router
from .integrations.email.router import router as email_router
from .integrations.whatsapp.router import router as whatsapp_router
from .integrations.instagram.router import router as instagram_router
from .integrations.facebook.router import router as facebook_router

# Initialize database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Sales OS API")

# Mount integrations
app.include_router(website_router)
app.include_router(email_router)
app.include_router(whatsapp_router)
app.include_router(instagram_router)
app.include_router(facebook_router)

@app.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket, token: str = None, db: Session = Depends(get_db)):
    # Note: Real auth requires verifying token. For now, we connect.
    await manager.connect_admin(websocket)
    try:
        while True:
            # Dashboard can also send messages (replying to a conversation)
            data = await websocket.receive_text()
            import json
            import datetime
            payload = json.loads(data)
            
            if payload.get("type") == "reply":
                conversation_id = payload.get("conversation_id")
                customer_id = payload.get("customer_id")
                text = payload.get("text")
                
                conversation = db.query(models.Conversation).filter(models.Conversation.id == conversation_id).first()
                if conversation and text:
                    conversation.status = "Replied"
                    conversation.last_message_text = text
                    conversation.last_message_time = datetime.datetime.utcnow().isoformat() + "Z"
                    
                    new_msg = models.Message(
                        conversation_id=conversation.id,
                        sender="human",
                        text=text,
                        timestamp=conversation.last_message_time
                    )
                    db.add(new_msg)
                    db.commit()
                    db.refresh(new_msg)
                    
                    msg_obj = {
                        "id": new_msg.id,
                        "sender": new_msg.sender,
                        "text": new_msg.text,
                        "timestamp": new_msg.timestamp
                    }
                    
                    # Broadcast to admins so other admins see it
                    await manager.broadcast_to_admins({
                        "type": "new_message",
                        "conversation_id": conversation.id,
                        "customer_id": customer_id,
                        "message": msg_obj
                    })
                    
                    # Send to customer
                    await manager.send_to_customer(customer_id, {
                        "type": "new_message",
                        "message": msg_obj
                    })
    except WebSocketDisconnect:
        manager.disconnect_admin(websocket)


# ── Auth Helpers ──────────────────────────────────────────────

def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

def verify_password(pw: str, pw_hash: str) -> bool:
    return hash_password(pw) == pw_hash

def get_current_admin(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    admin = db.query(models.Admin).filter(models.Admin.session_token == token).first()
    if not admin:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return admin

# ── Lead Scoring Helpers ─────────────────────────────────────

# Dynamically calculate lead status based on customer data completeness and parameters
def calculate_lead_status(customer) -> str:
    # 6 key onboarding questionnaire fields
    fields = [customer.name, customer.company, customer.interested_product, customer.quantity, customer.budget, customer.city]
    completed_count = sum(1 for f in fields if f is not None and f != "" and f != 0)
    
    budget = customer.budget or 0.0
    quantity = customer.quantity or 0

    # Hot: high budget (>= $10,000) OR medium budget with high volume (budget >= $5,000 and qty >= 50)
    if budget >= 10000.0 or (budget >= 5000.0 and quantity >= 50):
        return "Hot"
    # Warm: mid-tier budget (>= $2,000) OR some quantity (qty >= 10) OR most details captured (completed >= 4 fields)
    elif budget >= 2000.0 or quantity >= 10 or completed_count >= 4:
        return "Warm"
    # Cold: low budget, low volume, or minimal details captured
    else:
        return "Cold"

# Calculate lead score based on profile completion and lead status
def calculate_lead_score(customer) -> int:
    fields = [customer.name, customer.company, customer.phone, customer.email, customer.city, customer.interested_product, customer.quantity, customer.budget]
    # Each filled field adds 10 points (up to 80 points)
    score = sum(10 for f in fields if f is not None and f != "" and f != 0)
    
    # Status bonus
    status = customer.lead_status
    if status == "Hot":
        score += 20
    elif status == "Warm":
        score += 10
        
    return min(score, 100)

# Seed database function
def seed_database(db: Session):
    customers_data = []
    if db.query(models.Customer).count() == 0:
        print("Seeding SQLite database with 15 realistic conversations (Version 2)...")

        customers_data = [
        {
            "name": "Jane Cooper",
            "company": "Acme Corp",
            "phone": "+1 (555) 234-5678",
            "email": "jane.cooper@acme.com",
            "city": "Chicago",
            "channel": "Website Chat",
            "interested_product": "AI Sales OS Enterprise Plan",
            "quantity": 50,
            "budget": 12000.0,
            "ai_summary": "Jane Cooper from Acme Corp is looking for 50 licenses of AI Sales OS Enterprise with a budget of $12,000, located in Chicago. High buying intent.",
            "internal_notes": "Needs API customization options. Spoke about a potential demo on next Tuesday.",
            "unread": False,
            "last_message_time": "10:06 AM",
            "last_message_text": "Here is a summary of your inquiry:\n- **Product**: AI Sales OS Enterprise Plan\n- **Quantity**: 50\n- **Budget**: $12,000.00\n- **Location**: Chicago",
            "is_ai_managed": True,
            "simulation_stage": 7,
            "messages": [
                {"sender": "customer", "text": "Hi, I'm interested in your enterprise software.", "timestamp": "10:00 AM"},
                {"sender": "ai", "text": "Hello! Thank you for contacting us. May I know your name?", "timestamp": "10:00 AM"},
                {"sender": "customer", "text": "Jane Cooper", "timestamp": "10:01 AM"},
                {"sender": "ai", "text": "Nice to meet you, Jane! Which company are you representing?", "timestamp": "10:01 AM"},
                {"sender": "customer", "text": "Acme Corp", "timestamp": "10:02 AM"},
                {"sender": "ai", "text": "Got it, Acme Corp. Which product are you interested in?", "timestamp": "10:02 AM"},
                {"sender": "customer", "text": "AI Sales OS Enterprise Plan", "timestamp": "10:03 AM"},
                {"sender": "ai", "text": "Excellent choice! How many licenses/quantity do you need?", "timestamp": "10:03 AM"},
                {"sender": "customer", "text": "50", "timestamp": "10:04 AM"},
                {"sender": "ai", "text": "And what is your approximate annual budget for this?", "timestamp": "10:04 AM"},
                {"sender": "customer", "text": "$12,000", "timestamp": "10:05 AM"},
                {"sender": "ai", "text": "Understood. Where is your company located (delivery location/city)?", "timestamp": "10:05 AM"},
                {"sender": "customer", "text": "Chicago", "timestamp": "10:06 AM"},
                {"sender": "ai", "text": "Thank you, Jane! I have updated your profile in our system. A sales representative will contact you shortly.\n\nHere is a summary of your inquiry:\n- **Product**: AI Sales OS Enterprise Plan\n- **Quantity**: 50\n- **Budget**: $12,000.00\n- **Location**: Chicago", "timestamp": "10:06 AM"}
            ]
        },
        {
            "name": "Alex Rivera",
            "company": "PixelCraft",
            "phone": "+1 (555) 876-5432",
            "email": "arivera@pixelcraft.io",
            "city": None,
            "channel": "Website Chat",
            "interested_product": None,
            "quantity": None,
            "budget": None,
            "ai_summary": "Lead is currently in the onboarding stage. Name and company captured.",
            "internal_notes": "First touch point. No previous interactions.",
            "unread": False,
            "last_message_time": "10:16 AM",
            "last_message_text": "Nice to meet you, Alex! Which company are you representing?",
            "is_ai_managed": True,
            "simulation_stage": 2,
            "messages": [
                {"sender": "customer", "text": "Hi, do you support custom integrations?", "timestamp": "10:15 AM"},
                {"sender": "ai", "text": "Hello! Thank you for contacting us. May I know your name?", "timestamp": "10:15 AM"},
                {"sender": "customer", "text": "Alex Rivera", "timestamp": "10:16 AM"},
                {"sender": "ai", "text": "Nice to meet you, Alex! Which company are you representing?", "timestamp": "10:16 AM"}
            ]
        },
        {
            "name": "Marcus Vance",
            "company": "Apex Labs",
            "phone": "+1 (555) 912-3456",
            "email": "m.vance@apexlabs.com",
            "city": None,
            "channel": "Website Chat",
            "interested_product": None,
            "quantity": None,
            "budget": None,
            "ai_summary": "New lead reached out asking about starter plans. Chat bot flow not started.",
            "internal_notes": "Needs quick follow-up to start onboarding.",
            "unread": True,
            "last_message_time": "10:20 AM",
            "last_message_text": "Hey there! I want to know about your starter plans.",
            "is_ai_managed": True,
            "simulation_stage": 0,
            "messages": [
                {"sender": "customer", "text": "Hey there! I want to know about your starter plans.", "timestamp": "10:20 AM"}
            ]
        },
        {
            "name": "Sarah Jenkins",
            "company": "BuildFlow",
            "phone": "+1 (555) 345-6789",
            "email": "s.jenkins@buildflow.co",
            "city": "Boston",
            "channel": "Website Chat",
            "interested_product": "Team Plan",
            "quantity": 200,
            "budget": 24000.0,
            "ai_summary": "Sarah Jenkins from BuildFlow requires 200 user seats of the Team Plan, budget $24,000, based in Boston. High intent client.",
            "internal_notes": "Marcus sent custom proposal today. Awaiting client signature.",
            "unread": False,
            "last_message_time": "10:35 AM",
            "last_message_text": "Hi Sarah, I'm Marcus from the enterprise sales team. I have just emailed you the custom proposal for 200 seats.",
            "is_ai_managed": False,
            "simulation_stage": 7,
            "messages": [
                {"sender": "customer", "text": "Hello, looking for a team solution.", "timestamp": "10:25 AM"},
                {"sender": "ai", "text": "Hello! Thank you for contacting us. May I know your name?", "timestamp": "10:25 AM"},
                {"sender": "customer", "text": "Sarah Jenkins", "timestamp": "10:26 AM"},
                {"sender": "ai", "text": "Nice to meet you, Sarah! Which company are you representing?", "timestamp": "10:26 AM"},
                {"sender": "customer", "text": "BuildFlow", "timestamp": "10:27 AM"},
                {"sender": "ai", "text": "Got it, BuildFlow. Which product are you interested in?", "timestamp": "10:27 AM"},
                {"sender": "customer", "text": "Team Plan", "timestamp": "10:28 AM"},
                {"sender": "ai", "text": "Excellent choice! How many licenses/quantity do you need?", "timestamp": "10:28 AM"},
                {"sender": "customer", "text": "200", "timestamp": "10:29 AM"},
                {"sender": "ai", "text": "And what is your approximate annual budget for this?", "timestamp": "10:30 AM"},
                {"sender": "customer", "text": "$24,000", "timestamp": "10:31 AM"},
                {"sender": "ai", "text": "Understood. Where is your company located (delivery location/city)?", "timestamp": "10:31 AM"},
                {"sender": "customer", "text": "Boston", "timestamp": "10:32 AM"},
                {"sender": "ai", "text": "Thank you, Sarah! I have updated your profile in our system. A sales representative will contact you shortly.", "timestamp": "10:32 AM"},
                {"sender": "human", "text": "Hi Sarah, I'm Marcus from the enterprise sales team. I have just emailed you the custom proposal for 200 seats.", "timestamp": "10:35 AM"}
            ]
        },
        {
            "name": "David Kim",
            "company": "Nexus Retail",
            "phone": "+1 (555) 456-7890",
            "email": "dkim@nexusretail.com",
            "city": None,
            "channel": "Website Chat",
            "interested_product": "POS Sync Module",
            "quantity": 15,
            "budget": None,
            "ai_summary": "David Kim from Nexus Retail needs POS Sync for 15 locations. Pending budget and location information.",
            "internal_notes": "Needs sync details for Clover/Square POS hardware.",
            "unread": False,
            "last_message_time": "10:45 AM",
            "last_message_text": "Understood. What is your approximate annual budget for this?",
            "is_ai_managed": True,
            "simulation_stage": 5,
            "messages": [
                {"sender": "customer", "text": "Need retail POS integrations.", "timestamp": "10:40 AM"},
                {"sender": "ai", "text": "Hello! Thank you for contacting us. May I know your name?", "timestamp": "10:40 AM"},
                {"sender": "customer", "text": "David Kim", "timestamp": "10:41 AM"},
                {"sender": "ai", "text": "Nice to meet you, David! Which company are you representing?", "timestamp": "10:41 AM"},
                {"sender": "customer", "text": "Nexus Retail", "timestamp": "10:42 AM"},
                {"sender": "ai", "text": "Got it, Nexus Retail. Which product are you interested in?", "timestamp": "10:42 AM"},
                {"sender": "customer", "text": "POS Sync Module", "timestamp": "10:43 AM"},
                {"sender": "ai", "text": "Excellent choice! How many licenses/quantity do you need?", "timestamp": "10:43 AM"},
                {"sender": "customer", "text": "15 locations", "timestamp": "10:44 AM"},
                {"sender": "ai", "text": "Understood. What is your approximate annual budget for this?", "timestamp": "10:45 AM"}
            ]
        },
        {
            "name": "Emily Watson",
            "company": "Nova SaaS",
            "phone": "+1 (555) 567-8901",
            "email": "emily@novasaas.co",
            "city": "San Francisco",
            "channel": "Website Chat",
            "interested_product": "AI Sales OS Pro",
            "quantity": 10,
            "budget": 3000.0,
            "ai_summary": "Emily Watson from Nova SaaS bought 10 seats of Pro Plan ($3,000 budget) in San Francisco. Successfully closed.",
            "internal_notes": "Customer onboarded. Handed over to Customer Success team.",
            "unread": False,
            "last_message_time": "10:55 AM",
            "last_message_text": "Welcome aboard Emily! Your instance is ready.",
            "is_ai_managed": False,
            "simulation_stage": 7,
            "messages": [
                {"sender": "customer", "text": "Hi, setting up sales inbox.", "timestamp": "10:48 AM"},
                {"sender": "ai", "text": "Hello! Thank you for contacting us. May I know your name?", "timestamp": "10:48 AM"},
                {"sender": "customer", "text": "Emily Watson", "timestamp": "10:49 AM"},
                {"sender": "ai", "text": "Nice to meet you, Emily! Which company are you representing?", "timestamp": "10:49 AM"},
                {"sender": "customer", "text": "Nova SaaS", "timestamp": "10:50 AM"},
                {"sender": "ai", "text": "Got it, Nova SaaS. Which product are you interested in?", "timestamp": "10:50 AM"},
                {"sender": "customer", "text": "AI Sales OS Pro", "timestamp": "10:51 AM"},
                {"sender": "ai", "text": "Excellent choice! How many licenses/quantity do you need?", "timestamp": "10:51 AM"},
                {"sender": "customer", "text": "10", "timestamp": "10:52 AM"},
                {"sender": "ai", "text": "And what is your approximate annual budget for this?", "timestamp": "10:52 AM"},
                {"sender": "customer", "text": "$3,000", "timestamp": "10:53 AM"},
                {"sender": "ai", "text": "Understood. Where is your company located (delivery location/city)?", "timestamp": "10:53 AM"},
                {"sender": "customer", "text": "San Francisco", "timestamp": "10:54 AM"},
                {"sender": "ai", "text": "Thank you, Emily! I have updated your profile in our system.", "timestamp": "10:54 AM"},
                {"sender": "human", "text": "Welcome aboard Emily! Your instance is ready.", "timestamp": "10:55 AM"}
            ]
        },
        {
            "name": "Michael Chang",
            "company": "Zenith Corp",
            "phone": None,
            "email": "mchang@zenithcorp.org",
            "city": None,
            "channel": "Website Chat",
            "interested_product": None,
            "quantity": None,
            "budget": None,
            "ai_summary": "New visitor message on Website Chat.",
            "internal_notes": None,
            "unread": True,
            "last_message_time": "11:02 AM",
            "last_message_text": "Do you have an offline version?",
            "is_ai_managed": True,
            "simulation_stage": 0,
            "messages": [
                {"sender": "customer", "text": "Do you have an offline version?", "timestamp": "11:02 AM"}
            ]
        },
        {
            "name": "Sophia Martinez",
            "company": "Bloom Flora",
            "phone": "+52 (55) 1234-5678",
            "email": "sophia@bloomflora.mx",
            "city": "Mexico City",
            "channel": "WhatsApp",
            "interested_product": "WhatsApp API Bot",
            "quantity": 1,
            "budget": 1200.0,
            "ai_summary": "Sophia from Bloom Flora wants a WhatsApp API bot, $1,200 budget, Mexico City.",
            "internal_notes": "Needs localization support in Spanish.",
            "unread": False,
            "last_message_time": "11:15 AM",
            "last_message_text": "Here is the summary of your request: WhatsApp API Bot, budget $1,200.",
            "is_ai_managed": True,
            "simulation_stage": 7,
            "messages": [
                {"sender": "customer", "text": "Looking for API access.", "timestamp": "11:08 AM"},
                {"sender": "ai", "text": "Hello! Thank you for contacting us. May I know your name?", "timestamp": "11:08 AM"},
                {"sender": "customer", "text": "Sophia Martinez", "timestamp": "11:09 AM"},
                {"sender": "ai", "text": "Nice to meet you, Sophia! Which company are you representing?", "timestamp": "11:09 AM"},
                {"sender": "customer", "text": "Bloom Flora", "timestamp": "11:10 AM"},
                {"sender": "ai", "text": "Got it, Bloom Flora. Which product are you interested in?", "timestamp": "11:10 AM"},
                {"sender": "customer", "text": "WhatsApp API Bot", "timestamp": "11:11 AM"},
                {"sender": "ai", "text": "Excellent choice! How many licenses/quantity do you need?", "timestamp": "11:11 AM"},
                {"sender": "customer", "text": "1", "timestamp": "11:12 AM"},
                {"sender": "ai", "text": "And what is your approximate annual budget for this?", "timestamp": "11:12 AM"},
                {"sender": "customer", "text": "$1,200", "timestamp": "11:13 AM"},
                {"sender": "ai", "text": "Understood. Where is your company located (delivery location/city)?", "timestamp": "11:13 AM"},
                {"sender": "customer", "text": "Mexico City", "timestamp": "11:14 AM"},
                {"sender": "ai", "text": "Thank you, Sophia! I have updated your profile in our system. A sales representative will contact you shortly.\n\nHere is a summary of your inquiry:\n- **Product**: WhatsApp API Bot\n- **Quantity**: 1\n- **Budget**: $1,200.00\n- **Location**: Mexico City", "timestamp": "11:15 AM"}
            ]
        },
        {
            "name": "Daniel O'Connor",
            "company": "Dublin Brews",
            "phone": "+353 1 496 0123",
            "email": "doconnor@dublinbrews.ie",
            "city": None,
            "channel": "WhatsApp",
            "interested_product": "Supply Chain Tracker",
            "quantity": None,
            "budget": None,
            "ai_summary": "Daniel O'Connor from Dublin Brews. Product identified. Budget pending.",
            "internal_notes": "Interested in shipping updates webhook integrations.",
            "unread": False,
            "last_message_time": "11:25 AM",
            "last_message_text": "Got it, Dublin Brews. Which product are you interested in?",
            "is_ai_managed": True,
            "simulation_stage": 3,
            "messages": [
                {"sender": "customer", "text": "Hi, need supply chain tracking.", "timestamp": "11:21 AM"},
                {"sender": "ai", "text": "Hello! Thank you for contacting us. May I know your name?", "timestamp": "11:21 AM"},
                {"sender": "customer", "text": "Daniel O'Connor", "timestamp": "11:22 AM"},
                {"sender": "ai", "text": "Nice to meet you, Daniel! Which company are you representing?", "timestamp": "11:23 AM"},
                {"sender": "customer", "text": "Dublin Brews", "timestamp": "11:24 AM"},
                {"sender": "ai", "text": "Got it, Dublin Brews. Which product are you interested in?", "timestamp": "11:25 AM"}
            ]
        },
        {
            "name": "Olivia Fisher",
            "company": "FinTech Pro",
            "phone": "+1 (555) 789-0123",
            "email": "olivia.fisher@fintechpro.com",
            "city": "New York",
            "channel": "Instagram",
            "interested_product": "AI Sales OS Pro",
            "quantity": 15,
            "budget": 4500.0,
            "ai_summary": "Olivia Fisher from FinTech Pro. 15 seats Pro ($4,500 budget), New York.",
            "internal_notes": "Security vetting document sent by email.",
            "unread": False,
            "last_message_time": "11:36 AM",
            "last_message_text": "Thank you, Olivia! I have updated your profile in our system. A sales representative will contact you shortly.",
            "is_ai_managed": True,
            "simulation_stage": 7,
            "messages": [
                {"sender": "customer", "text": "Heard about AI Sales OS on Twitter.", "timestamp": "11:30 AM"},
                {"sender": "ai", "text": "Hello! Thank you for contacting us. May I know your name?", "timestamp": "11:30 AM"},
                {"sender": "customer", "text": "Olivia Fisher", "timestamp": "11:31 AM"},
                {"sender": "ai", "text": "Nice to meet you, Olivia! Which company are you representing?", "timestamp": "11:31 AM"},
                {"sender": "customer", "text": "FinTech Pro", "timestamp": "11:32 AM"},
                {"sender": "ai", "text": "Got it, FinTech Pro. Which product are you interested in?", "timestamp": "11:32 AM"},
                {"sender": "customer", "text": "AI Sales OS Pro", "timestamp": "11:33 AM"},
                {"sender": "ai", "text": "Excellent choice! How many licenses/quantity do you need?", "timestamp": "11:33 AM"},
                {"sender": "customer", "text": "15", "timestamp": "11:34 AM"},
                {"sender": "ai", "text": "And what is your approximate annual budget for this?", "timestamp": "11:34 AM"},
                {"sender": "customer", "text": "$4,500", "timestamp": "11:35 AM"},
                {"sender": "ai", "text": "Understood. Where is your company located (delivery location/city)?", "timestamp": "11:35 AM"},
                {"sender": "customer", "text": "New York", "timestamp": "11:36 AM"},
                {"sender": "ai", "text": "Thank you, Olivia! I have updated your profile in our system. A sales representative will contact you shortly.\n\nHere is a summary of your inquiry:\n- **Product**: AI Sales OS Pro\n- **Quantity**: 15\n- **Budget**: $4,500.00\n- **Location**: New York", "timestamp": "11:36 AM"}
            ]
        },
        {
            "name": "Liam Carter",
            "company": "Aero Space",
            "phone": None,
            "email": None,
            "city": None,
            "channel": "Instagram",
            "interested_product": None,
            "quantity": None,
            "budget": None,
            "ai_summary": "Visitor asked for a demo video via Instagram.",
            "internal_notes": "Send link to product walkthrough.",
            "unread": True,
            "last_message_time": "11:42 AM",
            "last_message_text": "Is there a demo video?",
            "is_ai_managed": True,
            "simulation_stage": 0,
            "messages": [
                {"sender": "customer", "text": "Is there a demo video?", "timestamp": "11:42 AM"}
            ]
        },
        {
            "name": "Emma Taylor",
            "company": "Green Solutions",
            "phone": "+44 20 7946 0958",
            "email": "emma@greensolutions.org.uk",
            "city": "London",
            "channel": "Email",
            "interested_product": "Sustainable Hosting OS",
            "quantity": 1,
            "budget": 5000.0,
            "ai_summary": "Emma Taylor from Green Solutions looking for sustainable hosting packages. Disqualified because we sell CRM SaaS, not bare metal cloud.",
            "internal_notes": "Politely rejected. No potential match.",
            "unread": False,
            "last_message_time": "11:58 AM",
            "last_message_text": "Hi Emma, we only provide cloud software, not bare metal hosting.",
            "is_ai_managed": False,
            "simulation_stage": 7,
            "messages": [
                {"sender": "customer", "text": "Need sustainable hosting info.", "timestamp": "11:48 AM"},
                {"sender": "ai", "text": "Hello! Thank you for contacting us. May I know your name?", "timestamp": "11:48 AM"},
                {"sender": "customer", "text": "Emma Taylor", "timestamp": "11:49 AM"},
                {"sender": "ai", "text": "Nice to meet you, Emma! Which company are you representing?", "timestamp": "11:49 AM"},
                {"sender": "customer", "text": "Green Solutions", "timestamp": "11:50 AM"},
                {"sender": "ai", "text": "Got it, Green Solutions. Which product are you interested in?", "timestamp": "11:50 AM"},
                {"sender": "customer", "text": "Sustainable Hosting OS", "timestamp": "11:51 AM"},
                {"sender": "ai", "text": "Excellent choice! How many licenses/quantity do you need?", "timestamp": "11:51 AM"},
                {"sender": "customer", "text": "1", "timestamp": "11:52 AM"},
                {"sender": "ai", "text": "And what is your approximate annual budget for this?", "timestamp": "11:52 AM"},
                {"sender": "customer", "text": "$5,000", "timestamp": "11:53 AM"},
                {"sender": "ai", "text": "Understood. Where is your company located (delivery location/city)?", "timestamp": "11:53 AM"},
                {"sender": "customer", "text": "London", "timestamp": "11:54 AM"},
                {"sender": "ai", "text": "Thank you, Emma! I have updated your profile in our system.", "timestamp": "11:54 AM"},
                {"sender": "human", "text": "Hi Emma, we only provide cloud software, not bare metal hosting.", "timestamp": "11:58 AM"}
            ]
        },
        {
            "name": "Noah Davis",
            "company": "NextGen AI",
            "phone": "+1 (555) 901-2345",
            "email": "noah.davis@nextgen.ai",
            "city": None,
            "channel": "Email",
            "interested_product": "Cognitive Sales Agent API",
            "quantity": None,
            "budget": None,
            "ai_summary": "Noah Davis from NextGen AI is looking for AI Agent API integrations. Budget and City pending.",
            "internal_notes": "Needs tech docs on websocket streaming backend.",
            "unread": False,
            "last_message_time": "12:10 PM",
            "last_message_text": "Excellent choice! How many licenses/quantity do you need?",
            "is_ai_managed": True,
            "simulation_stage": 4,
            "messages": [
                {"sender": "customer", "text": "Hi, interested in AI agent modules.", "timestamp": "12:05 PM"},
                {"sender": "ai", "text": "Hello! Thank you for contacting us. May I know your name?", "timestamp": "12:05 PM"},
                {"sender": "customer", "text": "Noah Davis", "timestamp": "12:06 PM"},
                {"sender": "ai", "text": "Nice to meet you, Noah! Which company are you representing?", "timestamp": "12:06 PM"},
                {"sender": "customer", "text": "NextGen AI", "timestamp": "12:07 PM"},
                {"sender": "ai", "text": "Got it, NextGen AI. Which product are you interested in?", "timestamp": "12:07 PM"},
                {"sender": "customer", "text": "Cognitive Sales Agent API", "timestamp": "12:08 PM"},
                {"sender": "ai", "text": "Excellent choice! How many licenses/quantity do you need?", "timestamp": "12:10 PM"}
            ]
        },
        {
            "name": "Isabella Rossi",
            "company": "Milano Fashion",
            "phone": None,
            "email": None,
            "city": None,
            "channel": "Website Chat",
            "interested_product": None,
            "quantity": None,
            "budget": None,
            "ai_summary": "New lead inquiring about language localization options.",
            "internal_notes": "Translators team assignment pending.",
            "unread": True,
            "last_message_time": "12:18 PM",
            "last_message_text": "Ciaoo, do you support Italian language?",
            "is_ai_managed": True,
            "simulation_stage": 0,
            "messages": [
                {"sender": "customer", "text": "Ciaoo, do you support Italian language?", "timestamp": "12:18 PM"}
            ]
        },
        {
            "name": "Lucas Meyer",
            "company": "Berlin Logistics",
            "phone": "+49 30 8924 012",
            "email": "lmeyer@berlinlogistics.de",
            "city": "Berlin",
            "channel": "Website Chat",
            "interested_product": "Fleet Routing API",
            "quantity": 12,
            "budget": 7200.0,
            "ai_summary": "Lucas Meyer from Berlin Logistics. 12 units Fleet Routing API, budget $7,200, Berlin. Mid-market routing segment.",
            "internal_notes": "Set call reminder next Thursday 9AM CET.",
            "unread": False,
            "last_message_time": "12:35 PM",
            "last_message_text": "Here is a summary of your inquiry:\n- **Product**: Fleet Routing API\n- **Quantity**: 12\n- **Budget**: $7,200.00\n- **Location**: Berlin",
            "is_ai_managed": True,
            "simulation_stage": 7,
            "messages": [
                {"sender": "customer", "text": "Guten Tag, interested in fleet routing API.", "timestamp": "12:25 PM"},
                {"sender": "ai", "text": "Hello! Thank you for contacting us. May I know your name?", "timestamp": "12:25 PM"},
                {"sender": "customer", "text": "Lucas Meyer", "timestamp": "12:26 PM"},
                {"sender": "ai", "text": "Nice to meet you, Lucas! Which company are you representing?", "timestamp": "12:26 PM"},
                {"sender": "customer", "text": "Berlin Logistics", "timestamp": "12:27 PM"},
                {"sender": "ai", "text": "Got it, Berlin Logistics. Which product are you interested in?", "timestamp": "12:27 PM"},
                {"sender": "customer", "text": "Fleet Routing API", "timestamp": "12:28 PM"},
                {"sender": "ai", "text": "Excellent choice! How many licenses/quantity do you need?", "timestamp": "12:28 PM"},
                {"sender": "customer", "text": "12", "timestamp": "12:29 PM"},
                {"sender": "ai", "text": "And what is your approximate annual budget for this?", "timestamp": "12:30 PM"},
                {"sender": "customer", "text": "$7,200", "timestamp": "12:31 PM"},
                {"sender": "ai", "text": "Understood. Where is your company located (delivery location/city)?", "timestamp": "12:31 PM"},
                {"sender": "customer", "text": "Berlin", "timestamp": "12:32 PM"},
                {"sender": "ai", "text": "Thank you, Lucas! I have updated your profile in our system. A sales representative will contact you shortly.\n\nHere is a summary of your inquiry:\n- **Product**: Fleet Routing API\n- **Quantity**: 12\n- **Budget**: $7,200.00\n- **Location**: Berlin", "timestamp": "12:35 PM"}
            ]
        }
    ]

    for item in customers_data:
        msgs = item.pop("messages")
        unread = item.pop("unread")
        last_message_time = item.pop("last_message_time")
        last_message_text = item.pop("last_message_text")
        is_ai_managed = item.pop("is_ai_managed")
        channel = item.pop("channel", "Website")
        simulation_stage = item.pop("simulation_stage")

        cust = models.Customer(**item)
        # Seed automatic lead status and score calculation
        cust.lead_status = calculate_lead_status(cust)
        cust.lead_score = calculate_lead_score(cust)

        db.add(cust)
        db.commit()
        db.refresh(cust)

        conv = models.Conversation(
            customer_id=cust.id,
            channel=channel,
            unread=unread,
            last_message_time=last_message_time,
            last_message_text=last_message_text,
            is_ai_managed=is_ai_managed,
            simulation_stage=simulation_stage
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)

        for m in msgs:
            msg = models.Message(conversation_id=conv.id, **m)
            db.add(msg)
        db.commit()

    # ── Seed Admin, Settings, Team Members ────────────────────
    if db.query(models.Admin).count() == 0:
        admin = models.Admin(
            username="admin",
            password_hash=hash_password("admin123"),
            name="Sarah Connor",
            email="sarah@aisalesos.com",
            phone="+1 (555) 000-0001",
            company_name="AI Sales OS",
            role="Admin",
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)

        settings = models.Settings(
            admin_id=admin.id,
            company_name="AI Sales OS",
            business_name="AI Sales OS",
        )
        db.add(settings)
        db.commit()

        now_str = datetime.datetime.now().isoformat()
        team_members = [
            models.TeamMember(name="Marcus Reid", email="marcus@aisalesos.com", role="Manager", status="Active", created_at=now_str),
            models.TeamMember(name="Elena Voss", email="elena@aisalesos.com", role="Sales Executive", status="Active", created_at=now_str),
            models.TeamMember(name="James Chen", email="james@aisalesos.com", role="Sales Executive", status="Active", created_at=now_str),
        ]
        db.add_all(team_members)
        db.commit()

# Create active DB session startup trigger
@app.on_event("startup")
def startup_event():
    db = next(get_db())
    seed_database(db)
    
    # Start Email IMAP Polling
    email_service.start()

# ══════════════════════════════════════════════════════════════
# API ENDPOINTS
# ══════════════════════════════════════════════════════════════

# ── Auth Endpoints ────────────────────────────────────────────

@app.post("/login")
def login(req: schemas.LoginRequest, response: Response, db: Session = Depends(get_db)):
    admin = db.query(models.Admin).filter(models.Admin.username == req.username).first()
    if not admin or not verify_password(req.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = secrets.token_hex(32)
    admin.session_token = token
    db.commit()

    response.set_cookie(key="session_token", value=token, httponly=True, samesite="lax")
    return {
        "status": "success",
        "admin": {
            "id": admin.id,
            "username": admin.username,
            "name": admin.name,
            "email": admin.email,
            "phone": admin.phone,
            "company_name": admin.company_name,
            "business_address": admin.business_address,
            "profile_photo": admin.profile_photo,
            "role": admin.role,
        },
    }

@app.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get("session_token")
    if token:
        admin = db.query(models.Admin).filter(models.Admin.session_token == token).first()
        if admin:
            admin.session_token = None
            db.commit()
    response.delete_cookie("session_token")
    return {"status": "success"}

@app.post("/signup")
def signup(req: schemas.SignupRequest, response: Response, db: Session = Depends(get_db)):
    existing_admin = db.query(models.Admin).filter(models.Admin.username == req.username).first()
    if existing_admin:
        raise HTTPException(status_code=400, detail="Username already exists")
        
    admin = models.Admin(
        username=req.username,
        password_hash=hash_password(req.password),
        name=req.name,
        company_name=req.company_name,
        role="Admin"
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    
    settings = models.Settings(
        admin_id=admin.id,
        company_name=req.company_name,
        business_name=req.company_name,
    )
    db.add(settings)
    db.commit()

    token = secrets.token_hex(32)
    admin.session_token = token
    db.commit()

    response.set_cookie(key="session_token", value=token, httponly=True, samesite="lax")
    return {"status": "success"}

@app.post("/forgot-password")
def forgot_password(req: schemas.ForgotPasswordRequest):
    # Mock endpoint for forgot password
    return {"status": "success", "message": "If that email exists, a reset link has been sent."}

# ── Admin Profile Endpoints ───────────────────────────────────

@app.get("/admin/profile")
def get_profile(admin=Depends(get_current_admin)):
    return {
        "id": admin.id,
        "username": admin.username,
        "name": admin.name,
        "email": admin.email,
        "phone": admin.phone,
        "company_name": admin.company_name,
        "business_address": admin.business_address,
        "profile_photo": admin.profile_photo,
        "role": admin.role,
    }

@app.put("/admin/profile")
def update_profile(update: schemas.AdminUpdate, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    update_data = update.model_dump(exclude_unset=True)

    # Handle password change separately
    new_password = update_data.pop("password", None)
    if new_password:
        admin.password_hash = hash_password(new_password)

    for key, value in update_data.items():
        setattr(admin, key, value)

    db.commit()
    db.refresh(admin)

    return {
        "id": admin.id,
        "username": admin.username,
        "name": admin.name,
        "email": admin.email,
        "phone": admin.phone,
        "company_name": admin.company_name,
        "business_address": admin.business_address,
        "profile_photo": admin.profile_photo,
        "role": admin.role,
    }

# ── Settings Endpoints ───────────────────────────────────────

@app.get("/settings")
def get_settings(admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    settings = db.query(models.Settings).filter(models.Settings.admin_id == admin.id).first()
    if not settings:
        settings = models.Settings(admin_id=admin.id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return {
        "id": settings.id,
        "company_name": settings.company_name,
        "business_name": settings.business_name,
        "business_logo": settings.business_logo,
        "business_description": settings.business_description,
        "business_address": settings.business_address,
        "business_phone": settings.business_phone,
        "business_email": settings.business_email,
        "website_url": settings.website_url,
        "social_media_links": settings.social_media_links,
        "working_hours": settings.working_hours,
        "timezone": settings.timezone,
        "language": settings.language,
        "currency": settings.currency,
        "ai_enabled": settings.ai_enabled,
        "greeting_message": settings.greeting_message,
        "ai_reply_delay": settings.ai_reply_delay,
        "max_followups": settings.max_followups,
        "desktop_notifications": settings.desktop_notifications,
        "email_notifications": settings.email_notifications,
        "sound_notifications": settings.sound_notifications,
        "unread_alerts": settings.unread_alerts,
        "theme": settings.theme,
        "primary_color": settings.primary_color,
        "font_size": settings.font_size,
    }

@app.put("/settings")
def update_settings(update: schemas.SettingsUpdate, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    settings = db.query(models.Settings).filter(models.Settings.admin_id == admin.id).first()
    if not settings:
        settings = models.Settings(admin_id=admin.id)
        db.add(settings)
        db.commit()
        db.refresh(settings)

    for key, value in update.model_dump(exclude_unset=True).items():
        setattr(settings, key, value)

    db.commit()
    db.refresh(settings)

    return {
        "id": settings.id,
        "company_name": settings.company_name,
        "business_name": settings.business_name,
        "business_logo": settings.business_logo,
        "business_description": settings.business_description,
        "business_address": settings.business_address,
        "business_phone": settings.business_phone,
        "business_email": settings.business_email,
        "website_url": settings.website_url,
        "social_media_links": settings.social_media_links,
        "working_hours": settings.working_hours,
        "timezone": settings.timezone,
        "language": settings.language,
        "currency": settings.currency,
        "ai_enabled": settings.ai_enabled,
        "greeting_message": settings.greeting_message,
        "ai_reply_delay": settings.ai_reply_delay,
        "max_followups": settings.max_followups,
        "desktop_notifications": settings.desktop_notifications,
        "email_notifications": settings.email_notifications,
        "sound_notifications": settings.sound_notifications,
        "unread_alerts": settings.unread_alerts,
        "theme": settings.theme,
        "primary_color": settings.primary_color,
        "font_size": settings.font_size,
    }

@app.get("/api/branding")
def get_branding(db: Session = Depends(get_db)):
    settings = db.query(models.Settings).first()
    if settings:
        return {
            "company_name": settings.company_name,
            "business_logo": settings.business_logo
        }
    return {
        "company_name": "AI Sales OS",
        "business_logo": None
    }

# ── Team Member Endpoints ────────────────────────────────────

@app.get("/team-members", response_model=List[schemas.TeamMemberResponse])
def get_team_members(admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    return db.query(models.TeamMember).all()

@app.post("/team-members", response_model=schemas.TeamMemberResponse)
def create_team_member(member: schemas.TeamMemberCreate, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    new_member = models.TeamMember(
        name=member.name,
        email=member.email,
        phone=member.phone,
        role=member.role,
        status=member.status,
        created_at=datetime.datetime.now().isoformat(),
    )
    db.add(new_member)
    db.commit()
    db.refresh(new_member)
    return new_member

@app.put("/team-members/{member_id}", response_model=schemas.TeamMemberResponse)
def update_team_member(member_id: int, update: schemas.TeamMemberUpdate, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    member = db.query(models.TeamMember).filter(models.TeamMember.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Team member not found")

    for key, value in update.model_dump(exclude_unset=True).items():
        setattr(member, key, value)

    db.commit()
    db.refresh(member)
    return member

@app.delete("/team-members/{member_id}")
def delete_team_member(member_id: int, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    member = db.query(models.TeamMember).filter(models.TeamMember.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Team member not found")

    db.delete(member)
    db.commit()
    return {"status": "success", "message": f"Team member {member_id} deleted."}

# ── Customer Endpoints ────────────────────────────────────────

@app.get("/customers", response_model=List[schemas.CustomerResponse])
def get_customers(db: Session = Depends(get_db)):
    customers_list = db.query(models.Customer).all()
    res = []
    for c in customers_list:
        conv = c.conversations[0] if c.conversations else None
        res.append({
            "id": c.id,
            "name": c.name,
            "company": c.company,
            "phone": c.phone,
            "email": c.email,
            "city": c.city,
            "interested_product": c.interested_product,
            "quantity": c.quantity,
            "budget": c.budget,
            "lead_status": c.lead_status,
            "lead_score": c.lead_score,
            "ai_summary": c.ai_summary,
            "internal_notes": c.internal_notes,
            "channel": conv.channel if conv else "Website",
            "status": conv.status if conv else "New",
            "unread": conv.unread if conv else False,
            "last_message_time": conv.last_message_time if conv else None,
            "last_message_text": conv.last_message_text if conv else None,
            "is_ai_managed": conv.is_ai_managed if conv else True,
            "simulation_stage": conv.simulation_stage if conv else 0
        })
    return res

@app.get("/customers/{customer_id}", response_model=schemas.CustomerResponse)
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    cust = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    conv = cust.conversations[0] if cust.conversations else None
    return {
        "id": cust.id,
        "name": cust.name,
        "company": cust.company,
        "phone": cust.phone,
        "email": cust.email,
        "city": cust.city,
        "interested_product": cust.interested_product,
        "quantity": cust.quantity,
        "budget": cust.budget,
        "lead_status": cust.lead_status,
        "lead_score": cust.lead_score,
        "ai_summary": cust.ai_summary,
        "internal_notes": cust.internal_notes,
        "channel": conv.channel if conv else "Website",
        "status": conv.status if conv else "New",
        "unread": conv.unread if conv else False,
        "last_message_time": conv.last_message_time if conv else None,
        "last_message_text": conv.last_message_text if conv else None,
        "is_ai_managed": conv.is_ai_managed if conv else True,
        "simulation_stage": conv.simulation_stage if conv else 0
    }

@app.put("/customers/{customer_id}", response_model=schemas.CustomerResponse)
def update_customer(customer_id: int, update_data: schemas.CustomerUpdate, db: Session = Depends(get_db)):
    cust = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    for key, value in update_data.model_dump(exclude_unset=True).items():
        setattr(cust, key, value)
    
    # Recalculate lead status and score automatically
    cust.lead_status = calculate_lead_status(cust)
    cust.lead_score = calculate_lead_score(cust)
    
    db.commit()
    db.refresh(cust)
    
    conv = cust.conversations[0] if cust.conversations else None
    return {
        "id": cust.id,
        "name": cust.name,
        "company": cust.company,
        "phone": cust.phone,
        "email": cust.email,
        "city": cust.city,
        "channel": conv.channel if conv else "Website",
        "interested_product": cust.interested_product,
        "quantity": cust.quantity,
        "budget": cust.budget,
        "lead_status": cust.lead_status,
        "lead_score": cust.lead_score,
        "ai_summary": cust.ai_summary,
        "internal_notes": cust.internal_notes,
        "unread": conv.unread if conv else False,
        "last_message_time": conv.last_message_time if conv else None,
        "last_message_text": conv.last_message_text if conv else None,
        "is_ai_managed": conv.is_ai_managed if conv else True,
        "simulation_stage": conv.simulation_stage if conv else 0
    }

@app.delete("/customers/{customer_id}")
def delete_customer(customer_id: int, db: Session = Depends(get_db)):
    cust = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    db.delete(cust)
    db.commit()
    return {"status": "success", "message": f"Customer {customer_id} deleted."}

# ── Message Endpoints ─────────────────────────────────────────

@app.get("/messages/{customer_id}", response_model=List[schemas.MessageResponse])
def get_messages(customer_id: int, db: Session = Depends(get_db)):
    cust = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    conv = db.query(models.Conversation).filter(models.Conversation.customer_id == customer_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Reset unread state upon viewing
    if conv.unread:
        conv.unread = False
        db.commit()
        db.refresh(conv)

    return db.query(models.Message).filter(models.Message.conversation_id == conv.id).all()

@app.post("/messages")
def send_message(msg_in: schemas.MessageCreate, db: Session = Depends(get_db)):
    cust = db.query(models.Customer).filter(models.Customer.id == msg_in.customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    conv = db.query(models.Conversation).filter(models.Conversation.customer_id == msg_in.customer_id).first()
    if not conv:
        conv = models.Conversation(customer_id=msg_in.customer_id, unread=False, is_ai_managed=True, simulation_stage=0)
        db.add(conv)
        db.commit()
        db.refresh(conv)

    # Save the input message
    new_msg = models.Message(
        conversation_id=conv.id,
        sender=msg_in.sender,
        text=msg_in.text,
        timestamp=msg_in.timestamp
    )
    db.add(new_msg)
    db.commit()
    db.refresh(new_msg)

    # Update conversation details
    conv.last_message_text = msg_in.text
    conv.last_message_time = msg_in.timestamp
    conv.unread = False
    
    # Mark manual override
    if msg_in.sender == "human":
        conv.is_ai_managed = False
        
    db.commit()

    ai_reply_msg = None

    # Process chatbot state machine if simulation active and customer sent it
    if msg_in.sender == "customer" and msg_in.simulation_mode:
        ai_reply_text = ""
        current_stage = conv.simulation_stage

        if current_stage == 0:
            ai_reply_text = "Hello! Thank you for contacting us. May I know your name?"
            conv.simulation_stage = 1
        elif current_stage == 1:
            cust.name = msg_in.text
            ai_reply_text = f"Nice to meet you, {msg_in.text}! Which company are you representing?"
            conv.simulation_stage = 2
        elif current_stage == 2:
            cust.company = msg_in.text
            ai_reply_text = f"Got it, {msg_in.text}. Which product are you interested in?"
            conv.simulation_stage = 3
        elif current_stage == 3:
            cust.interested_product = msg_in.text
            ai_reply_text = f"Great choice! How many units or licenses of {msg_in.text} do you need?"
            conv.simulation_stage = 4
        elif current_stage == 4:
            try:
                qty_str = "".join(filter(str.isdigit, msg_in.text))
                qty = int(qty_str) if qty_str else 1
            except:
                qty = 1
            cust.quantity = qty
            ai_reply_text = "Understood. What is your approximate annual budget for this order?"
            conv.simulation_stage = 5
        elif current_stage == 5:
            try:
                budget_str = "".join(filter(lambda c: c.isdigit() or c == ".", msg_in.text))
                budget = float(budget_str) if budget_str else 0.0
            except:
                budget = 0.0
            cust.budget = budget
            ai_reply_text = "And what is your city or delivery location?"
            conv.simulation_stage = 6
        elif current_stage == 6:
            cust.city = msg_in.text
            
            # Update profile summary
            formatted_budget = f"${cust.budget:,.2f}" if cust.budget else "Not specified"
            summary = f"{cust.name} from {cust.company} is looking for {cust.quantity} units of {cust.interested_product} with a budget of {formatted_budget} in {cust.city}."
            cust.ai_summary = summary
            
            ai_reply_text = f"Thank you, {cust.name}! I have updated your profile in our system. A sales representative will contact you shortly.\n\nHere is a summary of your inquiry:\n- **Product**: {cust.interested_product}\n- **Quantity**: {cust.quantity}\n- **Budget**: {formatted_budget}\n- **Location**: {cust.city}"
            conv.simulation_stage = 7
        else:
            ai_reply_text = "Thank you! A sales representative has been notified and will get back to you soon."

        # Re-evaluate lead status and score dynamically
        cust.lead_status = calculate_lead_status(cust)
        cust.lead_score = calculate_lead_score(cust)

        if ai_reply_text:
            # Save AI response
            now_time = datetime.datetime.now().strftime("%I:%M %p")
            ai_reply_msg = models.Message(
                conversation_id=conv.id,
                sender="ai",
                text=ai_reply_text,
                timestamp=now_time
            )
            db.add(ai_reply_msg)
            conv.last_message_text = ai_reply_text
            conv.last_message_time = now_time

        db.commit()
        if ai_reply_msg:
            db.refresh(ai_reply_msg)

    # If human replies and channel is Email, actually send the email out via SMTP
    if msg_in.sender == "human" and conv.channel == "Email":
        email_service.send_email(
            to_email=cust.email,
            subject="Re: Your Inquiry",
            body=msg_in.text
        )

    return {
        "status": "success",
        "message": new_msg,
        "ai_reply": ai_reply_msg
    }

# ── Analytics Endpoint ────────────────────────────────────────

@app.get("/api/analytics")
def get_analytics(admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    customers = db.query(models.Customer).all()
    conversations = db.query(models.Conversation).all()
    messages = db.query(models.Message).all()
    
    total_customers = len(customers)
    total_conversations = len(conversations)
    total_messages = len(messages)
    
    hot_leads = sum(1 for c in customers if c.lead_status == 'Hot')
    warm_leads = sum(1 for c in customers if c.lead_status == 'Warm')
    cold_leads = sum(1 for c in customers if c.lead_status == 'Cold')
    
    ai_managed = sum(1 for c in conversations if c.is_ai_managed)
    human_managed = total_conversations - ai_managed
    
    total_pipeline = sum(c.budget or 0 for c in customers)
    hot_pipeline = sum(c.budget or 0 for c in customers if c.lead_status == 'Hot')
    warm_pipeline = sum(c.budget or 0 for c in customers if c.lead_status == 'Warm')
    
    avg_lead_score = round(sum(c.lead_score or 0 for c in customers) / max(total_customers, 1), 1)
    
    customer_messages = sum(1 for m in messages if m.sender == 'customer')
    ai_messages = sum(1 for m in messages if m.sender == 'ai')
    human_messages = sum(1 for m in messages if m.sender == 'human')
    
    unread_count = sum(1 for c in conversations if c.unread)
    
    platforms = {}
    for c in customers:
        p = c.conversations[0].channel if c.conversations else 'Unknown'
        platforms[p] = platforms.get(p, 0) + 1
    
    cities = {}
    for c in customers:
        if c.city:
            cities[c.city] = cities.get(c.city, 0) + 1
    top_cities = sorted(cities.items(), key=lambda x: x[1], reverse=True)[:5]
    
    products = {}
    for c in customers:
        if c.interested_product:
            products[c.interested_product] = products.get(c.interested_product, 0) + 1
    
    stage_names = ['Initial Contact', 'Name Given', 'Company Given', 'Product Interest', 'Quantity Set', 'Budget Set', 'City Given', 'Completed']
    funnel = [0] * 8
    for conv in conversations:
        stage = min(conv.simulation_stage, 7)
        funnel[stage] += 1
    funnel_data = [{'stage': stage_names[i], 'count': funnel[i]} for i in range(8)]
    
    top_customers = sorted(
        [{'name': c.name, 'company': c.company or 'N/A', 'budget': c.budget or 0, 'status': c.lead_status, 'score': c.lead_score}
         for c in customers if c.budget],
        key=lambda x: x['budget'], reverse=True
    )[:5]
    
    return {
        'summary': {
            'total_customers': total_customers,
            'total_conversations': total_conversations,
            'total_messages': total_messages,
            'avg_lead_score': avg_lead_score,
            'unread_count': unread_count,
            'total_pipeline': total_pipeline,
            'hot_pipeline': hot_pipeline,
            'warm_pipeline': warm_pipeline,
        },
        'lead_distribution': {'hot': hot_leads, 'warm': warm_leads, 'cold': cold_leads},
        'conversation_management': {'ai_managed': ai_managed, 'human_managed': human_managed},
        'message_breakdown': {'customer': customer_messages, 'ai': ai_messages, 'human': human_messages},
        'platforms': platforms,
        'top_cities': [{'city': c[0], 'count': c[1]} for c in top_cities],
        'products': products,
        'funnel': funnel_data,
        'top_customers': top_customers
    }

# ── Static File Serving ───────────────────────────────────────

# Service Mounting Setup
current_dir = os.path.dirname(os.path.realpath(__file__))
frontend_dir = os.path.join(os.path.dirname(current_dir), "frontend")

if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
else:
    print(f"Warning: Frontend directory not found at {frontend_dir}.")
