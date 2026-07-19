import os
import random
import logging
from google import genai
from google.genai import types

logger = logging.getLogger("ai_service")

FALLBACKS = [
    "Thank you for reaching out to {company_name}! I would love to help you with our garment collections. May I know what products you are looking for today?",
    "Hi there! Warm welcome to {company_name}. We specialize in high-quality apparel manufacturing. What type of garments or styles are you interested in?",
    "Hello! Thanks for contacting {company_name}. We're excited to partner with you. Are you looking for custom designs, or wholesale purchases?",
]

def generate_sales_reply(settings, customer, conversation, new_message_text: str, force_variation: bool = False) -> str:
    """
    Generates a highly-engaging, context-aware AI sales reply using Gemini.
    Behaves like an experienced sales executive, qualifing leads, suggesting products, and keeping the conversation flowing.
    """
    biz_name = getattr(settings, 'business_name', None) or "our manufacturing company"
    biz_desc = getattr(settings, 'business_description', None) or "We manufacture premium garments."
    greeting = getattr(settings, 'greeting_message', None) or "Hello! Welcome to our store. How can I help you today?"
    knowledge = getattr(settings, 'ai_knowledge_base', None) or ""
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.warning("[AI Service] GEMINI_API_KEY not found. Using fallback.")
        return random.choice(FALLBACKS).format(company_name=biz_name)

    try:
        client = genai.Client(api_key=api_key)
        
        # Build customer background and context
        cust_name = getattr(customer, 'name', None) or "Customer"
        cust_email = getattr(customer, 'email', None) or "Not provided"
        cust_phone = getattr(customer, 'phone', None) or "Not provided"
        cust_company = getattr(customer, 'company', None) or "Not provided"
        lead_status = getattr(customer, 'lead_status', None) or "New"
        lead_score = getattr(customer, 'lead_score', 0)
        interested_product = getattr(customer, 'interested_product', None) or "Not specified"
        budget = getattr(customer, 'budget', None) or "Not specified"
        city = getattr(customer, 'city', None) or "Not specified"

        # Build system instruction enforcing active, high-converting Sales Agent persona
        system_instruction = f"""You are 'Sarah', a highly experienced, charming, and smart Senior Sales Executive working for '{biz_name}'.
Your primary goal is to engage the customer, build trust, recommend products, collect qualification details naturally, and convert every conversation into a high-value bulk order.

== THE COMPANY ==
Company Name: {biz_name}
What We Do: {biz_desc}

== BUSINESS KNOWLEDGE BASE (Products, Pricing, MOQ, Delivery, & FAQs) ==
Use this knowledge base to answer questions. NEVER make up products, prices, customization options, or delivery times that are not in this text:
{knowledge}

== CUSTOMER CARD (YOUR MEMORY) ==
Customer Name: {cust_name}
Email Address: {cust_email}
Phone Number: {cust_phone}
Company/Business Name: {cust_company}
Current Interested Product: {interested_product}
Budget: {budget}
City/Location: {city}
Lead Status: {lead_status}
Lead Score: {lead_score}

== YOUR CONVERSATIONAL & SALES PROTOCOLS ==
1. **Never be a passive FAQ bot.** Do not just give a single-line answer or dump dry facts. Start with a warm, helpful sales tone, answer their question using the knowledge base, and immediately pivot to guide the conversation.
2. **Follow-Up Questions**: Always end your response with 1 or 2 relevant follow-up questions to keep the conversation going and qualify the lead. Do NOT ask for everything at once (that feels robotic). Ask step-by-step.
   - If they ask for *price*: Give the pricing range from the knowledge base, then ask about their required quantity and preferred fabric/style.
   - If they ask for *MOQ*: Answer, then ask what specific styles or products they are targeting.
   - If they ask about *customization*: Outline what we offer, then ask for their logo requirements, quantity, and target delivery date.
   - If they ask about *delivery*: Answer, then ask for their delivery city or country.
3. **Lead Qualification Flow**: Gather their business details naturally. If they haven't provided these yet, try to discover:
   - Are they buying retail or wholesale/bulk?
   - What is their target quantity/pieces?
   - What is their city or location?
   - Can we get their contact number or email to send our latest catalog/quote?
4. **Memory Usage**: Reference details they already shared. Do not ask for quantity or product type again if it is listed in the Customer Card above or has been mentioned in the recent chat history.
5. **Product Recommendations**: Actively suggest products matching their interests. Explain *why* you suggest them (e.g. "Since you mentioned needing soft, breathable fabrics for summer, I highly recommend our Rayon Printed Kurtis because...").
6. **Cross-Selling & Upselling**: If they show interest in one garment, suggest a matching product (e.g. "We also manufacture high-quality matching leggings/bottoms that go perfectly with these kurtis. Would you like to see options for those?"). Encourage larger quantities for better discounts.
7. **Human Tone**: Be conversational, warm, and highly professional. Never start messages with "According to our information..." or "Based on our knowledge base...". Speak as "I" or "We". Use formatted bullet points for readability when presenting lists.
"""
        if force_variation:
            system_instruction += "\n\nIMPORTANT: You must rewrite this response completely. Use different opening greetings, structure, and vocabulary. Make it sound fresh while keeping the sales objective."

        # Build chat history from conversation
        contents = []
        if conversation and hasattr(conversation, 'messages') and conversation.messages:
            # Take last 8 messages for a wider context memory
            for msg in conversation.messages[-8:]:
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

        logger.info(f"[AI Service] Generating sales response for {cust_name}")

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.85 if force_variation else 0.75,
                max_output_tokens=500
            )
        )
        
        result = response.text.strip()
        logger.info(f"[AI Service] Sales response generated successfully ({len(result)} chars)")
        return result
    
    except Exception as e:
        logger.error(f"[AI Service] Error in generate_sales_reply: {e}")
        return random.choice(FALLBACKS).format(company_name=biz_name)
