import os
import time
import random
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from . import models
from .ai_provider import execute_with_retry_and_fallback
from .ai_brain import CompanyBrainEngine, RAGEngine
from .ai_memory import LongTermMemoryManager
from .sales_intelligence import SalesIntelligenceEngine
from .ai_telemetry import record_telemetry
from .ai_tools import AIToolExecutor

logger = logging.getLogger("ai_service")

FALLBACKS = [
    "Thank you for reaching out to {company_name}! I would love to help you with our garment collections. May I know what products or catalog you are looking for today?",
    "Hi there! Warm welcome to {company_name}. We specialize in high-quality apparel manufacturing. What type of garments or bulk styles are you interested in?",
    "Hello! Thanks for contacting {company_name}. We're excited to partner with you on your apparel inventory. Are you looking for custom designs or wholesale orders?",
]

# Module 11: Prompt Versioning Library
PROMPT_VERSIONS = {
    "V1": """You are a Senior Sales Executive for '{company_name}'. Answer customer questions clearly and qualify leads.""",

    "V2": """You are 'Sarah', an elite, top-performing Senior Sales Executive representing '{company_name}'.
Your primary objective is to build trust, answer questions using exact company facts, qualify buyer requirements (quantity, budget, delivery location), suggest matching products, and convert inquiries into bulk purchase orders.

== YOUR CONVERSATIONAL PROTOCOLS ==
1. **Be Human & Natural**: Speak warmly as an experienced sales professional. Never use robotic formulas like "Based on our knowledge base...".
2. **Channel Adaptability**:
   - If Channel is **Email**: Write a well-structured, professional business email with formal greeting, clear value points, follow-up qualification questions, and sign-off.
   - If Channel is **WhatsApp/Chat**: Keep response crisp, conversational, warm, using bullet points for options and 1-2 step-by-step follow-up questions.
3. **Strict Facts & Zero Hallucinations**: Rely strictly on the Company Brain & RAG evidence provided below for MOQ, pricing, shipping, and return rules.
4. **Active Sales Qualification**: Always end with 1 or 2 natural follow-up questions to uncover target quantity, fabric preference, or delivery city.
""",

    "V3": """You are 'Sarah', a Master Sales Strategist & Senior Account Manager for '{company_name}'.
Your mandate is to deliver high-converting, personalized B2B sales conversations.

== STRATEGIC DIRECTIVES ==
- Analyze sentiment and intent. If customer is price-sensitive, highlight bulk volume discounts. If urgent, emphasize express dispatch.
- Cross-sell matching garment lines naturally.
- Maintain seamless context memory of all past buyer conversations.
"""
}

def generate_sales_reply(
    settings: Optional[models.Settings],
    customer: Optional[models.Customer],
    conversation: Optional[models.Conversation],
    new_message_text: str,
    db: Optional[Session] = None,
    force_variation: bool = False
) -> str:
    """
    Production-grade AI Sales Executive reply generator integrating all 12 modules.
    """
    start_time = time.time()
    company_id = settings.company_id if settings else 1
    biz_name = getattr(settings, 'business_name', None) or "our manufacturing company"

    provider_name = getattr(settings, 'ai_provider', 'gemini') or 'gemini'
    model_name = getattr(settings, 'ai_model', 'gemini-flash-latest') or 'gemini-flash-latest'
    if model_name in ['gemini-2.0-flash', 'gemini-1.5-flash']:
        model_name = 'gemini-flash-latest'
    prompt_ver = getattr(settings, 'prompt_version', 'V2') or 'V2'

    # Module 1: Build Company Brain Prompt
    brain_prompt = CompanyBrainEngine.get_company_brain_prompt(settings)

    # Module 2: Local RAG Evidence
    rag_evidence = ""
    if db:
        rag_evidence = RAGEngine.retrieve_relevant_chunks(db, company_id, new_message_text)

    # Module 4: Long-Term Memory
    long_term_memory = ""
    if db and customer:
        long_term_memory = LongTermMemoryManager.get_customer_memory_context(db, customer.id)

    # Channel Context
    channel_type = conversation.channel if conversation else "WhatsApp"

    # Module 11: System Instruction
    base_template = PROMPT_VERSIONS.get(prompt_ver, PROMPT_VERSIONS["V2"])
    system_instruction = f"""{base_template.format(company_name=biz_name)}

CURRENT COMMUNICATION CHANNEL: {channel_type.upper()}

{brain_prompt}

{rag_evidence}

{long_term_memory}

== CUSTOMER PROFILE & CONTEXT ==
Customer Name: {getattr(customer, 'name', 'Buyer') or 'Buyer'}
Email: {getattr(customer, 'email', 'Not provided')}
Phone: {getattr(customer, 'phone', 'Not provided')}
Buyer Business: {getattr(customer, 'buyer_company_name', 'Not provided')}
Location: {getattr(customer, 'city', 'Not provided')}
Notes: {getattr(customer, 'internal_notes', 'None')}
"""
    if force_variation:
        system_instruction += "\n\nIMPORTANT: Rephrase this response with fresh wording and structure while maintaining professional sales quality."

    # Build Sanitized Alternating History
    contents = []
    if conversation and hasattr(conversation, 'messages') and conversation.messages:
        # Filter valid past messages (excluding drafts)
        valid_messages = [m for m in conversation.messages if m.sender in ['customer', 'ai', 'human']][-10:]
        for msg in valid_messages:
            if msg.text == new_message_text:
                continue
            role = "user" if msg.sender == "customer" else "assistant"
            contents.append({"role": role, "text": msg.text})

    # Append current message
    contents.append({"role": "user", "text": new_message_text})

    # Trigger Execution with Retry & Failover
    fallback_used = False
    try:
        res = execute_with_retry_and_fallback(
            provider_name=provider_name,
            system_instruction=system_instruction,
            contents=contents,
            temperature=0.85 if force_variation else 0.7,
            max_tokens=650
        )
        reply_text = res["text"].strip()
        in_tokens = res.get("input_tokens", 0)
        out_tokens = res.get("output_tokens", 0)
        actual_provider = res.get("provider", provider_name)
        actual_model = res.get("model", model_name)
        fallback_used = res.get("fallback_used", False)
    except Exception as e:
        logger.error(f"[AIService] All providers failed for sales reply: {e}")
        reply_text = random.choice(FALLBACKS).format(company_name=biz_name)
        in_tokens = out_tokens = 0
        actual_provider = "Fallback"
        actual_model = "Static"
        fallback_used = True

    elapsed_ms = int((time.time() - start_time) * 1000)

    # Module 12: Record Telemetry
    if db:
        record_telemetry(
            db=db,
            company_id=company_id,
            request_type="Sales_Reply",
            provider=actual_provider,
            model=actual_model,
            latency_ms=elapsed_ms,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            success=True,
            fallback_used=fallback_used
        )

    # Module 6, 7, 9: Background Sales Intelligence & Tool Execution
    if db and customer:
        try:
            deal = conversation.deal if conversation else None
            intel = SalesIntelligenceEngine.analyze_sales_intelligence(
                db=db,
                company_id=company_id,
                customer=customer,
                deal=deal,
                latest_message=new_message_text,
                conversation_history=reply_text[:200]
            )
            # Module 3 Tool Call: If intent shows high buyer intent, auto-update deal stage
            if deal and intel.get("lead_score", 0) >= 80 and deal.stage == "New Inquiry":
                AIToolExecutor.update_deal_stage(db, deal.id, "Qualifying")
        except Exception as ex:
            logger.warning(f"[AIService] Non-blocking intelligence analysis error: {ex}")

    return reply_text

def generate_ai_insights(db: Session, company_id: int, customer: models.Customer, conversation: Optional[models.Conversation]) -> Dict[str, Any]:
    """
    Module 8: Generates comprehensive sales insights & recommendations for a lead card.
    """
    deal = conversation.deal if conversation else None
    last_msg = conversation.last_message_text if conversation else ""

    intel = SalesIntelligenceEngine.analyze_sales_intelligence(
        db=db,
        company_id=company_id,
        customer=customer,
        deal=deal,
        latest_message=last_msg or "Inquiring about apparel catalog."
    )
    return intel

def generate_auto_followup(db: Session, company_id: int, customer: models.Customer, conversation: models.Conversation) -> str:
    """
    Generates a proactive follow-up message for cold/stalled leads.
    """
    settings = db.query(models.Settings).filter(models.Settings.company_id == company_id).first()
    biz_name = getattr(settings, 'business_name', None) or "our company"

    prompt = f"""You are 'Sarah', Senior Sales Executive for '{biz_name}'.
The customer '{customer.name}' hasn't responded to our last quotation/inquiry.
Write a warm, non-pushy, high-converting follow-up message asking if they need sample swatches, pricing adjustments, or express shipping.
Keep it under 3-4 sentences.
"""
    try:
        res = execute_with_retry_and_fallback(
            provider_name="gemini",
            system_instruction=prompt,
            contents=[{"role": "user", "text": f"Last message: {conversation.last_message_text}"}],
            temperature=0.75,
            max_tokens=250
        )
        return res["text"].strip()
    except Exception as e:
        logger.error(f"[AIService] Followup generation failed: {e}")
        return f"Hi {customer.name}! Following up on your recent inquiry with {biz_name}. Would you like us to share our updated catalog or custom quotation?"
