import os
from dotenv import load_dotenv

load_dotenv()
import datetime
import hashlib
import secrets
import bcrypt
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
    await manager.connect_admin(websocket)
    try:
        while True:
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
                    
                    await manager.broadcast_to_admins({
                        "type": "new_message",
                        "conversation_id": conversation.id,
                        "customer_id": customer_id,
                        "message": msg_obj
                    })
                    
                    await manager.send_to_customer(customer_id, {
                        "type": "new_message",
                        "message": msg_obj
                    })
    except WebSocketDisconnect:
        manager.disconnect_admin(websocket)

# ── Auth Helpers ──────────────────────────────────────────────

def hash_password(pw: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pw.encode('utf-8'), salt).decode('utf-8')

def verify_password(pw: str, pw_hash: str) -> bool:
    try:
        if len(pw_hash) == 64 and not pw_hash.startswith("$2b$"):
            return hashlib.sha256(pw.encode("utf-8")).hexdigest() == pw_hash
        return bcrypt.checkpw(pw.encode('utf-8'), pw_hash.encode('utf-8'))
    except Exception:
        return False

def get_current_admin(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    admin = db.query(models.Admin).filter(models.Admin.session_token == token).first()
    if not admin:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return admin

# ── Lead Scoring Helpers ─────────────────────────────────────

def calculate_lead_status(deal, customer) -> str:
    fields = [customer.name, customer.buyer_company_name, deal.interested_product, deal.quantity, deal.budget, customer.city]
    completed_count = sum(1 for f in fields if f is not None and f != "" and f != 0)
    
    budget = deal.budget or 0.0
    quantity = deal.quantity or 0

    if budget >= 10000.0 or (budget >= 5000.0 and quantity >= 50):
        return "Hot"
    elif budget >= 2000.0 or quantity >= 10 or completed_count >= 4:
        return "Warm"
    else:
        return "Cold"

def calculate_lead_score(deal, customer) -> int:
    fields = [customer.name, customer.buyer_company_name, customer.phone, customer.email, customer.city, deal.interested_product, deal.quantity, deal.budget]
    score = sum(10 for f in fields if f is not None and f != "" and f != 0)
    
    status = calculate_lead_status(deal, customer)
    if status == "Hot":
        score += 20
    elif status == "Warm":
        score += 10
        
    return min(score, 100)

# Seed database function
def seed_database(db: Session):
    if db.query(models.Company).count() == 0:
        company = models.Company(name="GarmentX Manufacturing")
        db.add(company)
        db.commit()
        db.refresh(company)

        admin = models.Admin(
            company_id=company.id,
            username="admin",
            password_hash=hash_password("admin123"),
            name="Sarah Connor",
            email="sarah@garmentx.com",
            phone="+1 (555) 000-0001",
            role="Admin"
        )
        db.add(admin)

        settings = models.Settings(
            company_id=company.id,
            business_name="GarmentX Manufacturing",
            business_description="We manufacture premium ethnic and western wear for B2B wholesale.",
            timezone="IST",
            currency="INR"
        )
        db.add(settings)

        tm1 = models.TeamMember(company_id=company.id, name="Marcus Reid", email="marcus@garmentx.com", role="Manager")
        tm2 = models.TeamMember(company_id=company.id, name="Elena Voss", email="elena@garmentx.com", role="Sales Executive")
        db.add_all([tm1, tm2])
        db.commit()

        # Seed Customers and Deals
        c1 = models.Customer(company_id=company.id, name="Jane Cooper", buyer_company_name="Acme Boutique", email="jane@acme.com", city="Mumbai")
        db.add(c1)
        db.commit()

        d1 = models.Deal(
            company_id=company.id,
            customer_id=c1.id,
            interested_product="Kurti Catalog A (500 pcs)",
            quantity=500,
            budget=250000.0,
            stage="Quotation Sent",
            lead_score=85
        )
        db.add(d1)
        db.commit()

        conv1 = models.Conversation(
            customer_id=c1.id,
            deal_id=d1.id,
            channel="WhatsApp",
            status="Open",
            unread=False,
            last_message_text="Can you send the invoice?",
            last_message_time=datetime.datetime.utcnow().isoformat() + "Z"
        )
        db.add(conv1)
        db.commit()

        m1 = models.Message(conversation_id=conv1.id, sender="customer", text="Hi, interested in Kurti Catalog A", timestamp=datetime.datetime.utcnow().isoformat() + "Z")
        m2 = models.Message(conversation_id=conv1.id, sender="ai", text="Hello Jane! What is your MOQ requirement?", timestamp=datetime.datetime.utcnow().isoformat() + "Z")
        m3 = models.Message(conversation_id=conv1.id, sender="customer", text="500 pcs. Can you send the invoice?", timestamp=datetime.datetime.utcnow().isoformat() + "Z")
        db.add_all([m1, m2, m3])
        db.commit()

@app.on_event("startup")
def on_startup():
    db = next(get_db())
    seed_database(db)
    email_service.start()

# ── Endpoints ──────────────────────────────────────────────

@app.post("/login")
def login(req: schemas.LoginRequest, response: Response, db: Session = Depends(get_db)):
    admin = db.query(models.Admin).filter(models.Admin.username == req.username).first()
    if not admin or not verify_password(req.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    token = secrets.token_hex(32)
    admin.session_token = token
    db.commit()
    
    response.set_cookie(key="session_token", value=token, httponly=True, samesite="lax")
    return {"status": "success", "admin": {"name": admin.name, "role": admin.role}}

@app.post("/signup")
def signup(req: schemas.SignupRequest, response: Response, db: Session = Depends(get_db)):
    existing_admin = db.query(models.Admin).filter(models.Admin.username == req.username).first()
    if existing_admin:
        raise HTTPException(status_code=400, detail="Username already registered")
        
    company = models.Company(
        name=req.company_name,
        created_at=datetime.datetime.utcnow().isoformat() + "Z"
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    
    token = secrets.token_hex(32)
    admin = models.Admin(
        company_id=company.id,
        username=req.username,
        password_hash=hash_password(req.password),
        name=req.name,
        role="Admin",
        session_token=token
    )
    db.add(admin)
    
    settings = models.Settings(
        company_id=company.id,
        business_name=req.company_name,
        business_description=f"We manufacture premium products for B2B wholesale.",
        timezone="IST",
        currency="INR"
    )
    db.add(settings)
    db.commit()
    
    response.set_cookie(key="session_token", value=token, httponly=True, samesite="lax")
    return {"status": "success", "admin": {"name": admin.name, "role": admin.role}}

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

@app.get("/admin/profile")
def get_profile(admin = Depends(get_current_admin)):
    return {
        "id": admin.id,
        "username": admin.username,
        "name": admin.name,
        "email": admin.email,
        "phone": admin.phone,
        "role": admin.role
    }

@app.get("/settings", response_model=schemas.SettingsResponse)
def get_settings(admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    settings = db.query(models.Settings).filter(models.Settings.company_id == admin.company_id).first()
    if not settings:
        settings = models.Settings(company_id=admin.company_id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings

@app.put("/settings", response_model=schemas.SettingsResponse)
def update_settings(update: schemas.SettingsUpdate, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    settings = db.query(models.Settings).filter(models.Settings.company_id == admin.company_id).first()
    for key, value in update.model_dump(exclude_unset=True).items():
        setattr(settings, key, value)
    db.commit()
    db.refresh(settings)
    return settings

@app.get("/api/branding")
def get_branding(request: Request, db: Session = Depends(get_db)):
    # Try to get branding for logged-in user's company, fallback to first
    token = request.cookies.get("session_token")
    settings = None
    if token:
        admin = db.query(models.Admin).filter(models.Admin.session_token == token).first()
        if admin:
            settings = db.query(models.Settings).filter(models.Settings.company_id == admin.company_id).first()
    if not settings:
        settings = db.query(models.Settings).first()
    if settings:
        return {
            "company_name": settings.business_name,
            "business_logo": settings.business_logo
        }
    return {"company_name": "AI Sales OS", "business_logo": None}

@app.get("/team-members", response_model=List[schemas.TeamMemberResponse])
def get_team_members(admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    return db.query(models.TeamMember).filter(models.TeamMember.company_id == admin.company_id).all()

@app.post("/team-members", response_model=schemas.TeamMemberResponse)
def create_team_member(member: schemas.TeamMemberCreate, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    new_member = models.TeamMember(
        company_id=admin.company_id,
        **member.model_dump(),
        created_at=datetime.datetime.now().isoformat(),
    )
    db.add(new_member)
    db.commit()
    db.refresh(new_member)
    return new_member

@app.get("/customers", response_model=List[schemas.CustomerResponse])
def get_customers(admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    customers_list = db.query(models.Customer).filter(
        models.Customer.company_id == admin.company_id
    ).all()
    res = []
    for c in customers_list:
        conv = c.conversations[0] if c.conversations else None
        deal = c.deals[0] if c.deals else None
        
        res.append({
            "id": c.id,
            "company_id": c.company_id,
            "name": c.name,
            "buyer_company_name": c.buyer_company_name,
            "phone": c.phone,
            "email": c.email,
            "city": c.city,
            "internal_notes": c.internal_notes,
            "interested_product": deal.interested_product if deal else None,
            "quantity": deal.quantity if deal else None,
            "budget": deal.budget if deal else None,
            "lead_status": calculate_lead_status(deal, c) if deal else "Cold",
            "lead_score": deal.lead_score if deal else 10,
            "ai_summary": deal.ai_summary if deal else None,
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
def get_customer(customer_id: int, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    c = db.query(models.Customer).filter(
        models.Customer.id == customer_id,
        models.Customer.company_id == admin.company_id
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")
    conv = c.conversations[0] if c.conversations else None
    deal = c.deals[0] if c.deals else None
    return {
        "id": c.id,
        "company_id": c.company_id,
        "name": c.name,
        "buyer_company_name": c.buyer_company_name,
        "phone": c.phone,
        "email": c.email,
        "city": c.city,
        "internal_notes": c.internal_notes,
        "interested_product": deal.interested_product if deal else None,
        "quantity": deal.quantity if deal else None,
        "budget": deal.budget if deal else None,
        "lead_status": calculate_lead_status(deal, c) if deal else "Cold",
        "lead_score": deal.lead_score if deal else 10,
        "ai_summary": deal.ai_summary if deal else None,
        "channel": conv.channel if conv else "Website",
        "status": conv.status if conv else "New",
        "unread": conv.unread if conv else False,
        "last_message_time": conv.last_message_time if conv else None,
        "last_message_text": conv.last_message_text if conv else None,
        "is_ai_managed": conv.is_ai_managed if conv else True,
        "simulation_stage": conv.simulation_stage if conv else 0
    }

@app.put("/customers/{customer_id}", response_model=schemas.CustomerResponse)
def update_customer(customer_id: int, update_data: schemas.CustomerUpdate, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    c = db.query(models.Customer).filter(
        models.Customer.id == customer_id,
        models.Customer.company_id == admin.company_id
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    if update_data.name is not None: c.name = update_data.name
    if update_data.buyer_company_name is not None: c.buyer_company_name = update_data.buyer_company_name
    if update_data.phone is not None: c.phone = update_data.phone
    if update_data.email is not None: c.email = update_data.email
    if update_data.city is not None: c.city = update_data.city
    if update_data.internal_notes is not None: c.internal_notes = update_data.internal_notes

    deal = c.deals[0] if c.deals else None
    if deal:
        if update_data.interested_product is not None: deal.interested_product = update_data.interested_product
        if update_data.quantity is not None: deal.quantity = update_data.quantity
        if update_data.budget is not None: deal.budget = update_data.budget
        if update_data.ai_summary is not None: deal.ai_summary = update_data.ai_summary
        deal.lead_score = calculate_lead_score(deal, c)
    
    db.commit()
    db.refresh(c)
    if deal: db.refresh(deal)
    
    return get_customer(customer_id, admin=admin, db=db)

@app.get("/messages/{customer_id}", response_model=List[schemas.MessageResponse])
def get_messages(customer_id: int, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    # Verify customer belongs to this company
    customer = db.query(models.Customer).filter(
        models.Customer.id == customer_id,
        models.Customer.company_id == admin.company_id
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    conv = db.query(models.Conversation).filter(models.Conversation.customer_id == customer_id).first()
    if not conv:
        return []
    if conv.unread:
        conv.unread = False
        db.commit()
    return db.query(models.Message).filter(models.Message.conversation_id == conv.id).all()

@app.post("/messages")
def send_message(msg_in: schemas.MessageCreate, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    # Verify customer belongs to this company
    customer = db.query(models.Customer).filter(
        models.Customer.id == msg_in.customer_id,
        models.Customer.company_id == admin.company_id
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    conv = db.query(models.Conversation).filter(models.Conversation.customer_id == msg_in.customer_id).first()
    if not conv:
        conv = models.Conversation(customer_id=msg_in.customer_id)
        db.add(conv)
        db.commit()

    new_msg = models.Message(
        conversation_id=conv.id,
        sender=msg_in.sender,
        text=msg_in.text,
        timestamp=msg_in.timestamp
    )
    db.add(new_msg)
    
    conv.last_message_text = msg_in.text
    conv.last_message_time = msg_in.timestamp
    conv.unread = False
    if msg_in.sender == "human":
        conv.is_ai_managed = False
    
    db.commit()
    return {"status": "success"}

@app.get("/api/analytics")
def get_analytics(admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    company_id = admin.company_id
    customers = db.query(models.Customer).filter(models.Customer.company_id == company_id).all()
    deals = db.query(models.Deal).filter(models.Deal.company_id == company_id).all()
    
    total_pipeline = sum(d.budget or 0 for d in deals)
    scores = [d.lead_score or 0 for d in deals]
    avg_score = int(sum(scores) / len(scores)) if scores else 0
    
    hot = warm = cold = 0
    for d in deals:
        c = db.query(models.Customer).filter(models.Customer.id == d.customer_id).first()
        if c:
            status = calculate_lead_status(d, c)
            if status == "Hot": hot += 1
            elif status == "Warm": warm += 1
            else: cold += 1
    
    total_messages = 0
    msg_customer = msg_ai = msg_human = 0
    ai_managed = human_managed = 0
    for c in customers:
        for conv in c.conversations:
            if conv.is_ai_managed: ai_managed += 1
            else: human_managed += 1
            msgs = db.query(models.Message).filter(models.Message.conversation_id == conv.id).all()
            total_messages += len(msgs)
            for m in msgs:
                if m.sender == "customer": msg_customer += 1
                elif m.sender == "ai": msg_ai += 1
                else: msg_human += 1
    
    stages = {"New Inquiry": 0, "Qualifying": 0, "Quotation Sent": 0, "Closed Won": 0, "Closed Lost": 0}
    for d in deals:
        if d.stage in stages: stages[d.stage] += 1
    
    return {
        "summary": {
            "total_customers": len(customers),
            "total_pipeline": total_pipeline,
            "hot_pipeline": sum(d.budget or 0 for d in deals if db.query(models.Customer).filter(models.Customer.id == d.customer_id).first() and calculate_lead_status(d, db.query(models.Customer).filter(models.Customer.id == d.customer_id).first()) == "Hot"),
            "warm_pipeline": sum(d.budget or 0 for d in deals if db.query(models.Customer).filter(models.Customer.id == d.customer_id).first() and calculate_lead_status(d, db.query(models.Customer).filter(models.Customer.id == d.customer_id).first()) == "Warm"),
            "total_messages": total_messages,
            "avg_lead_score": avg_score
        },
        "lead_distribution": {"hot": hot, "warm": warm, "cold": cold},
        "conversation_management": {"ai_managed": ai_managed, "human_managed": human_managed},
        "message_breakdown": {"customer": msg_customer, "ai": msg_ai, "human": msg_human},
        "funnel": [{"stage": s, "count": c} for s, c in stages.items()],
        "top_customers": [],
        "products": {}
    }

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
