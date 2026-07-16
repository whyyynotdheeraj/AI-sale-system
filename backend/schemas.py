from pydantic import BaseModel
from typing import List, Optional

class CompanyBase(BaseModel):
    name: str
    subscription_plan: str = "Free"

class CompanyResponse(CompanyBase):
    id: int
    created_at: Optional[str] = None
    class Config:
        from_attributes = True

class MessageBase(BaseModel):
    sender: str
    text: str
    timestamp: str

class MessageCreate(BaseModel):
    customer_id: int
    sender: str
    text: str
    timestamp: str
    simulation_mode: Optional[bool] = False

class MessageResponse(MessageBase):
    id: int
    conversation_id: int
    class Config:
        from_attributes = True

class ConversationBase(BaseModel):
    id: int
    customer_id: int
    deal_id: Optional[int] = None
    channel: str = "Website"
    status: str = "New"
    assigned_agent_id: Optional[int] = None
    unread: bool
    last_message_time: Optional[str] = None
    last_message_text: Optional[str] = None
    is_ai_managed: bool
    simulation_stage: int
    class Config:
        from_attributes = True

class DealBase(BaseModel):
    interested_product: Optional[str] = None
    quantity: Optional[int] = None
    budget: Optional[float] = None
    stage: str = "New Inquiry"
    lead_score: int = 10
    ai_summary: Optional[str] = None

class DealCreate(DealBase):
    customer_id: int

class DealResponse(DealBase):
    id: int
    company_id: int
    customer_id: int
    class Config:
        from_attributes = True

class CustomerBase(BaseModel):
    name: str
    buyer_company_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    city: Optional[str] = None
    internal_notes: Optional[str] = None

class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    buyer_company_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    city: Optional[str] = None
    internal_notes: Optional[str] = None
    # Deal related fields that the frontend might send in a single update
    interested_product: Optional[str] = None
    quantity: Optional[int] = None
    budget: Optional[float] = None
    lead_status: Optional[str] = None
    lead_score: Optional[int] = None
    ai_summary: Optional[str] = None

class CustomerResponse(CustomerBase):
    id: int
    company_id: int
    # Deal data (flattened for frontend compatibility)
    interested_product: Optional[str] = None
    quantity: Optional[int] = None
    budget: Optional[float] = None
    lead_status: str = "Cold"
    lead_score: int = 10
    ai_summary: Optional[str] = None
    # Conversation data (flattened)
    unread: bool = False
    last_message_time: Optional[str] = None
    last_message_text: Optional[str] = None
    is_ai_managed: bool = True
    simulation_stage: int = 0
    channel: str = "Website"
    status: str = "New"

    class Config:
        from_attributes = True

# ── Auth Schemas ──────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

# ── Admin Schemas ─────────────────────────────────────────────

class AdminBase(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    role: str

class AdminResponse(AdminBase):
    id: int
    company_id: int
    username: str
    class Config:
        from_attributes = True

class AdminUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    password: Optional[str] = None  # New password if user wants to change
    username: Optional[str] = None

# ── Settings Schemas ──────────────────────────────────────────

class SettingsResponse(BaseModel):
    id: int
    company_id: int
    business_name: Optional[str] = None
    business_logo: Optional[str] = None
    business_description: Optional[str] = None
    business_address: Optional[str] = None
    business_phone: Optional[str] = None
    business_email: Optional[str] = None
    website_url: Optional[str] = None
    social_media_links: Optional[str] = None
    working_hours: Optional[str] = None
    timezone: Optional[str] = None
    language: Optional[str] = None
    currency: Optional[str] = None
    ai_enabled: Optional[bool] = None
    greeting_message: Optional[str] = None
    ai_reply_delay: Optional[int] = None
    max_followups: Optional[int] = None
    desktop_notifications: Optional[bool] = None
    email_notifications: Optional[bool] = None
    sound_notifications: Optional[bool] = None
    unread_alerts: Optional[bool] = None
    theme: Optional[str] = None
    primary_color: Optional[str] = None
    font_size: Optional[str] = None
    class Config:
        from_attributes = True

class SettingsUpdate(BaseModel):
    business_name: Optional[str] = None
    business_logo: Optional[str] = None
    business_description: Optional[str] = None
    business_address: Optional[str] = None
    business_phone: Optional[str] = None
    business_email: Optional[str] = None
    website_url: Optional[str] = None
    social_media_links: Optional[str] = None
    working_hours: Optional[str] = None
    timezone: Optional[str] = None
    language: Optional[str] = None
    currency: Optional[str] = None
    ai_enabled: Optional[bool] = None
    greeting_message: Optional[str] = None
    ai_reply_delay: Optional[int] = None
    max_followups: Optional[int] = None
    desktop_notifications: Optional[bool] = None
    email_notifications: Optional[bool] = None
    sound_notifications: Optional[bool] = None
    unread_alerts: Optional[bool] = None
    theme: Optional[str] = None
    primary_color: Optional[str] = None
    font_size: Optional[str] = None

# ── Team Member Schemas ───────────────────────────────────────

class TeamMemberBase(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    role: str = "Sales Executive"
    status: str = "Active"

class TeamMemberCreate(TeamMemberBase):
    pass

class TeamMemberUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None

class TeamMemberResponse(TeamMemberBase):
    id: int
    company_id: int
    created_at: Optional[str] = None
    class Config:
        from_attributes = True

class SignupRequest(BaseModel):
    username: str
    password: str
    name: str
    company_name: str

class ForgotPasswordRequest(BaseModel):
    email: str
