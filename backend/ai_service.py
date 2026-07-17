import os
from google import genai
from google.genai import types

def generate_sales_reply(settings, customer, conversation, new_message_text: str) -> str:
    """
    Generates an AI sales reply using Gemini based on company context and customer history.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[AI Service] GEMINI_API_KEY not found in environment variables.")
        return "Thank you for reaching out! A representative will be with you shortly."

    try:
        client = genai.Client(api_key=api_key)
        
        # Build the System Prompt (Context)
        system_instruction = f"""
        You are a highly professional sales representative for a company named '{settings.business_name}'.
        Company Description: {settings.business_description}
        Default Greeting: {settings.greeting_message}
        
        Your goal is to answer customer inquiries politely, professionally, and concisely.
        If they ask for pricing or products, provide relevant information based on the company description, or politely state that a sales manager will provide a detailed quote.
        Do NOT invent fake products, prices, or links that are not in the company description.
        Sign off professionally on behalf of {settings.business_name}.
        """

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
        print(f"[AI Service] Error generating reply: {e}")
        return "Thank you for your message. We will get back to you shortly."
