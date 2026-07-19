import os
import random
import logging
from google import genai
from google.genai import types

logger = logging.getLogger("ai_service")

FALLBACKS = [
    "Thank you for contacting {company_name}! A sales executive will review your request and get back to you shortly.",
    "Hi there! Thanks for reaching out to {company_name}. We've received your query and a representative will connect with you soon.",
    "Hello! Thank you for your interest in {company_name}. Our team is looking into your inquiry and we will get back to you shortly.",
    "Thanks for messaging {company_name}! Someone from our sales department will get back to you within a few hours.",
    "Greetings from {company_name}! We appreciate you reaching out. A sales specialist will follow up with you very soon.",
]

def generate_sales_reply(settings, customer, conversation, new_message_text: str, force_variation: bool = False) -> str:
    """
    Generates an AI sales reply using Gemini based on company context, knowledge base, and customer history.
    """
    biz_name = getattr(settings, 'business_name', None) or "our company"
    biz_desc = getattr(settings, 'business_description', None) or "We provide enterprise services."
    greeting = getattr(settings, 'greeting_message', None) or "Hello! How can we help you today?"
    knowledge = getattr(settings, 'ai_knowledge_base', None) or ""
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.warning("[AI Service] GEMINI_API_KEY not found. Using fallback.")
        return random.choice(FALLBACKS).format(company_name=biz_name)

    try:
        client = genai.Client(api_key=api_key)
        
        # Build the System Prompt with full business context
        system_instruction = f"""You are a highly professional and friendly sales representative for '{biz_name}'.

== COMPANY INFORMATION ==
Company Name: {biz_name}
Business Description: {biz_desc}
Default Greeting: {greeting}
"""
        
        if knowledge:
            system_instruction += f"""
== BUSINESS KNOWLEDGE BASE ==
The following is detailed information about the company's products, services, pricing, policies, and FAQs. Use this to answer customer questions accurately:

{knowledge}
"""

        # Customer context
        cust_name = getattr(customer, 'name', None) or "Customer"
        cust_email = getattr(customer, 'email', None) or ""
        cust_company = getattr(customer, 'buyer_company_name', None) or ""
        
        system_instruction += f"""
== CUSTOMER CONTEXT ==
Customer Name: {cust_name}
Customer Email: {cust_email}
Customer Company: {cust_company}

== YOUR INSTRUCTIONS ==
1. Answer the customer's question directly, using the Business Knowledge Base above.
2. Be warm, professional, and concise.
3. If the customer asks about specific products, pricing, MOQ, delivery etc., answer using ONLY the knowledge base above. Do NOT invent information.
4. If you don't have the answer in the knowledge base, politely say a sales manager will provide details.
5. Keep responses under 150 words unless a detailed answer is needed.
6. Always address the customer by name ({cust_name}).
7. Sign off professionally on behalf of {biz_name}.
"""

        if force_variation:
            system_instruction += "\n\nIMPORTANT: You MUST rephrase your response completely. Use different sentence structure, vocabulary, and opening. Do NOT repeat any previous wording."

        # Build chat history from conversation
        contents = []
        if conversation and hasattr(conversation, 'messages') and conversation.messages:
            for msg in conversation.messages[-6:]:
                if msg.text == new_message_text:
                    continue
                role = "user" if msg.sender == "customer" else "model"
                contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=msg.text)]
                    )
                )

        # Add the latest incoming message
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=new_message_text)]
            )
        )

        logger.info(f"[AI Service] Generating reply for customer '{cust_name}' (knowledge base: {'YES' if knowledge else 'NO'})")

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.8 if force_variation else 0.7,
                max_output_tokens=400
            )
        )
        
        result = response.text.strip()
        logger.info(f"[AI Service] Generated reply ({len(result)} chars)")
        return result
    
    except Exception as e:
        logger.error(f"[AI Service] Error generating reply: {e}")
        return random.choice(FALLBACKS).format(company_name=biz_name)
