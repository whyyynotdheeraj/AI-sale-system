import os
import random
from google import genai
from google.genai import types

FALLBACKS = [
    "Thank you for contacting {company_name}! A sales executive will review your request and get back to you shortly.",
    "Hi there! Thanks for reaching out to {company_name}. We've received your query and a representative will connect with you soon.",
    "Hello! Thank you for your interest in {company_name}. Our team is looking into your inquiry and we will get back to you shortly.",
    "Thanks for messaging {company_name}! Someone from our sales department will get back to you within a few hours.",
    "Greetings from {company_name}! We appreciate you reaching out. A sales specialist will follow up with you very soon.",
    "Hello. We have received your inquiry. A representative from {company_name} will be in touch with you shortly to assist."
]

def generate_sales_reply(settings, customer, conversation, new_message_text: str, force_variation: bool = False) -> str:
    """
    Generates an AI sales reply using Gemini based on company context and customer history.
    """
    biz_name = settings.business_name if settings and settings.business_name else "our company"
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[AI Service] GEMINI_API_KEY not found in environment variables. Using randomized fallback.")
        return random.choice(FALLBACKS).format(company_name=biz_name)

    try:
        client = genai.Client(api_key=api_key)
        
        # Build the System Prompt (Context)
        system_instruction = f"""
        You are a highly professional sales representative for a company named '{biz_name}'.
        Company Description: {settings.business_description if settings else 'We provide enterprise services.'}
        Default Greeting: {settings.greeting_message if settings else 'Hello! How can we help you today?'}
        
        Your goal is to answer customer inquiries politely, professionally, and concisely.
        If they ask for pricing or products, provide relevant information based on the company description, or politely state that a sales manager will provide a detailed quote.
        Do NOT invent fake products, prices, or links that are not in the company description.
        Sign off professionally on behalf of {biz_name}.
        """

        if force_variation:
            system_instruction += "\nIMPORTANT: Please rephrase your previous response to use different wording, structure, and vocabulary, while keeping the same meaning and intent. Do NOT repeat yourself."

        # Build the Chat History
        contents = []
        if conversation and conversation.messages:
            for msg in conversation.messages[-5:]:  # Include last 5 messages for context
                # Skip the new message we're about to add
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

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7,
                max_output_tokens=300
            )
        )
        
        return response.text.strip()
    
    except Exception as e:
        print(f"[AI Service] Error generating reply: {e}. Using randomized fallback.")
        return random.choice(FALLBACKS).format(company_name=biz_name)
