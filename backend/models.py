from sqlalchemy import Column, Integer, String, Float, Text, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    company = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    city = Column(String, nullable=True)
    interested_product = Column(String, nullable=True)
    quantity = Column(Integer, nullable=True)
    budget = Column(Float, nullable=True)
    lead_status = Column(String, default="Cold")  # Hot, Warm, Cold
    lead_score = Column(Integer, default=10)
    ai_summary = Column(Text, nullable=True)
    internal_notes = Column(Text, nullable=True)

    # A customer has conversations
    conversations = relationship("Conversation", back_populates="customer", cascade="all, delete-orphan")

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    channel = Column(String, default="Website") # website, email, whatsapp, instagram, facebook
    status = Column(String, default="New") # New, Open, Replied, Closed
    assigned_agent_id = Column(Integer, ForeignKey("team_members.id"), nullable=True)
    unread = Column(Boolean, default=False)
    last_message_time = Column(String, nullable=True)
    last_message_text = Column(String, nullable=True)
    is_ai_managed = Column(Boolean, default=True)
    simulation_stage = Column(Integer, default=0)

    customer = relationship("Customer", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    assigned_agent = relationship("TeamMember")

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"))
    sender = Column(String)  # customer, ai, human
    text = Column(Text)
    timestamp = Column(String)

    conversation = relationship("Conversation", back_populates="messages")

class Admin(Base):
    __tablename__ = "admins"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    name = Column(String, default="Admin")
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    company_name = Column(String, default="AI Sales OS")
    business_address = Column(String, nullable=True)
    profile_photo = Column(String, nullable=True)  # URL or base64
    role = Column(String, default="Admin")
    session_token = Column(String, nullable=True)

class Settings(Base):
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("admins.id"))
    # General
    company_name = Column(String, default="AI Sales OS")
    business_name = Column(String, default="AI Sales OS")
    business_logo = Column(String, nullable=True)
    business_description = Column(Text, default="We provide enterprise SaaS solutions for sales teams.")
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

class TeamMember(Base):
    __tablename__ = "team_members"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String)
    phone = Column(String, nullable=True)
    role = Column(String, default="Sales Executive")  # Admin, Manager, Sales Executive
    status = Column(String, default="Active")  # Active, Inactive
    created_at = Column(String, nullable=True)
