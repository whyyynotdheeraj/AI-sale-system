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
    sender = Column(String)  # customer, ai, human
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
    
    # AI Settings
    ai_enabled = Column(Boolean, default=True)
    ai_auto_send = Column(Boolean, default=False)
    greeting_message = Column(String, default="Hello! Thank you for contacting us. How can I help you today?")
    ai_reply_delay = Column(Integer, default=1)  # seconds
    max_followups = Column(Integer, default=3)
    
    # Notifications
    desktop_notifications = Column(Boolean, default=True)
    email_notifications = Column(Boolean, default=False)
    sound_notifications = Column(Boolean, default=True)
    unread_alerts = Column(Boolean, default=True)
    
    # Appearance
    theme = Column(String, default="light")  # light, dark, system
    primary_color = Column(String, default="#6366f1")
    font_size = Column(String, default="medium")  # small, medium, large

    # AI Knowledge Base
    ai_knowledge_base = Column(Text, nullable=True)  # Detailed business info for AI context

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
