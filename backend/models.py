from sqlalchemy import Column, Integer, String, Float, Text, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base

class Company(Base):
    """The central tenant model (Garment Manufacturer)."""
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    subscription_plan = Column(String, default="Free")
    created_at = Column(String, nullable=True)

    admins = relationship("Admin", back_populates="company", cascade="all, delete-orphan")
    customers = relationship("Customer", back_populates="company", cascade="all, delete-orphan")
    deals = relationship("Deal", back_populates="company", cascade="all, delete-orphan")
    team_members = relationship("TeamMember", back_populates="company", cascade="all, delete-orphan")
    settings = relationship("Settings", back_populates="company", cascade="all, delete-orphan", uselist=False)

class Admin(Base):
    __tablename__ = "admins"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"))
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    name = Column(String, default="Admin")
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    role = Column(String, default="Admin")
    session_token = Column(String, nullable=True)

    company = relationship("Company", back_populates="admins")

class Customer(Base):
    """The contact person at the buyer's end."""
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"))
    name = Column(String, index=True)
    buyer_company_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    city = Column(String, nullable=True)
    internal_notes = Column(Text, nullable=True)

    company = relationship("Company", back_populates="customers")
    deals = relationship("Deal", back_populates="customer", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="customer", cascade="all, delete-orphan")

class Deal(Base):
    """A specific sales opportunity."""
    __tablename__ = "deals"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"))
    interested_product = Column(String, nullable=True) # E.g. "Kurti Catalog A"
    quantity = Column(Integer, nullable=True)
    budget = Column(Float, nullable=True)
    stage = Column(String, default="New Inquiry") # New Inquiry, Qualifying, Quotation Sent, Closed Won, Closed Lost
    lead_score = Column(Integer, default=10)
    lead_score_reasons = Column(Text, nullable=True) # JSON list of reasons
    opportunity_tags = Column(String, nullable=True) # E.g. "Upsell, Bulk Order, High Value"
    detected_intent = Column(String, nullable=True)
    sentiment = Column(String, nullable=True)
    next_best_action = Column(Text, nullable=True)
    ai_summary = Column(Text, nullable=True)

    company = relationship("Company", back_populates="deals")
    customer = relationship("Customer", back_populates="deals")
    conversations = relationship("Conversation", back_populates="deal")

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    deal_id = Column(Integer, ForeignKey("deals.id"), nullable=True)
    channel = Column(String, default="WhatsApp") # website, email, whatsapp, instagram, facebook
    status = Column(String, default="New") # New, Open, Replied, Closed
    assigned_agent_id = Column(Integer, ForeignKey("team_members.id"), nullable=True)
    unread = Column(Boolean, default=False)
    last_message_time = Column(String, nullable=True)
    last_message_text = Column(String, nullable=True)
    is_ai_managed = Column(Boolean, default=True)
    simulation_stage = Column(Integer, default=0)

    customer = relationship("Customer", back_populates="conversations")
    deal = relationship("Deal", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    assigned_agent = relationship("TeamMember")

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"))
    sender = Column(String)  # customer, ai, human, ai_draft
    text = Column(Text)
    timestamp = Column(String)
    email_message_id = Column(String, nullable=True)  # For email dedup

    conversation = relationship("Conversation", back_populates="messages")

class Settings(Base):
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), unique=True)
    
    # General
    business_name = Column(String, default="Garment Manufacturer")
    business_logo = Column(String, nullable=True)
    business_description = Column(Text, default="We manufacture high quality garments.")
    business_address = Column(String, nullable=True)
    business_phone = Column(String, nullable=True)
    business_email = Column(String, nullable=True)
    website_url = Column(String, nullable=True)
    social_media_links = Column(String, nullable=True) # JSON string
    working_hours = Column(String, nullable=True)
    timezone = Column(String, default="UTC")
    language = Column(String, default="English")
    currency = Column(String, default="USD")
    
    # AI Settings & Provider Config
    ai_enabled = Column(Boolean, default=True)
    ai_auto_send = Column(Boolean, default=False)
    greeting_message = Column(String, default="Hello! Thank you for contacting us. How can I help you today?")
    ai_reply_delay = Column(Integer, default=1)  # seconds
    max_followups = Column(Integer, default=3)
    ai_provider = Column(String, default="gemini") # gemini, openai, anthropic, groq, openrouter
    ai_model = Column(String, default="gemini-2.0-flash")
    prompt_version = Column(String, default="V2") # V1, V2, V3
    
    # Notifications
    desktop_notifications = Column(Boolean, default=True)
    email_notifications = Column(Boolean, default=False)
    sound_notifications = Column(Boolean, default=True)
    unread_alerts = Column(Boolean, default=True)
    
    # Appearance
    theme = Column(String, default="light")  # light, dark, system
    primary_color = Column(String, default="#6366f1")
    font_size = Column(String, default="medium")  # small, medium, large

    # AI Knowledge Base & Company Brain (Module 1)
    ai_knowledge_base = Column(Text, nullable=True)
    moq_info = Column(String, nullable=True) # E.g. "50 pcs per color/style"
    pricing_tiers = Column(Text, nullable=True) # E.g. JSON/Text of bulk volume discounts
    shipping_policy = Column(Text, nullable=True)
    payment_terms = Column(Text, nullable=True) # E.g. "50% advance, 50% on dispatch"
    return_policy = Column(Text, nullable=True)
    gst_number = Column(String, nullable=True)
    location = Column(String, nullable=True)
    owner_sales_strategy = Column(Text, nullable=True)
    catalog_summary = Column(Text, nullable=True)

    # Integrations
    gmail_address = Column(String, nullable=True)
    gmail_app_password = Column(String, nullable=True)
    whatsapp_api_key = Column(String, nullable=True)
    whatsapp_phone_number_id = Column(String, nullable=True)
    whatsapp_verify_token = Column(String, nullable=True)

    company = relationship("Company", back_populates="settings")

class TeamMember(Base):
    __tablename__ = "team_members"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"))
    name = Column(String)
    email = Column(String)
    phone = Column(String, nullable=True)
    role = Column(String, default="Sales Executive")  # Admin, Manager, Sales Executive
    status = Column(String, default="Active")  # Active, Inactive
    created_at = Column(String, nullable=True)

    company = relationship("Company", back_populates="team_members")

# Module 2 & 5: Company Knowledge Chunks for RAG & File Ingestion
class CompanyKnowledgeChunk(Base):
    __tablename__ = "company_knowledge_chunks"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"))
    title = Column(String)
    category = Column(String, default="General") # FAQ, Pricing, Product, Policy, File
    content = Column(Text)
    source_filename = Column(String, nullable=True)
    created_at = Column(String)

# Module 4: Long-Term Customer Memory
class CustomerLongTermMemory(Base):
    __tablename__ = "customer_memories"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    key = Column(String) # E.g. "preferred_fabric", "past_inquiry_date", "budget_tier"
    value = Column(Text)
    created_at = Column(String)
    updated_at = Column(String)

# Module 9: Workflow Automated Tasks
class WorkflowTask(Base):
    __tablename__ = "workflow_tasks"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"))
    deal_id = Column(Integer, ForeignKey("deals.id"), nullable=True)
    title = Column(String)
    action_type = Column(String) # Reminder, Email_Followup, WhatsApp_Followup, Task
    due_date = Column(String)
    status = Column(String, default="Pending") # Pending, Completed, Cancelled
    notes = Column(Text, nullable=True)
    created_at = Column(String)

# Module 12: AI Telemetry & Token Analytics Logs
class AITelemetryLog(Base):
    __tablename__ = "ai_telemetry_logs"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"))
    request_type = Column(String) # Chat_Reply, Copilot_Suggest, Intent_Analysis, Followup_Gen, Summarize
    provider = Column(String)
    model = Column(String)
    latency_ms = Column(Integer)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    estimated_cost = Column(Float, default=0.0)
    success = Column(Boolean, default=True)
    fallback_used = Column(Boolean, default=False)
    created_at = Column(String)

