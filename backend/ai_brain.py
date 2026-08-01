import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from . import models

logger = logging.getLogger("ai_brain")

class CompanyBrainEngine:
    """
    Module 1: Compiles structured business information (MOQ, Pricing, Shipping, Payment Terms, FAQs, Policies)
    to eliminate AI hallucinations.
    """
    @staticmethod
    def get_company_brain_prompt(settings: Optional[models.Settings]) -> str:
        if not settings:
            return "Company Name: Garment Manufacturer\nProducts: High quality garments."

        biz_name = settings.business_name or "Garment Manufacturer"
        biz_desc = settings.business_description or "We manufacture premium apparel."
        moq = settings.moq_info or "Standard MOQ: 50 pieces per style/color."
        pricing = settings.pricing_tiers or "Wholesale volume pricing available upon inquiry."
        shipping = settings.shipping_policy or "Pan-India and international shipping available. Dispatch within 3-7 business days."
        payment = settings.payment_terms or "50% advance upon order confirmation, 50% prior to dispatch."
        returns = settings.return_policy or "Replacements available for manufacturing defects reported within 7 days of delivery."
        gst = settings.gst_number or "Provided upon invoice."
        location = settings.location or settings.business_address or "India"
        owner_notes = settings.owner_sales_strategy or "Focus on bulk buyers, recommend high-margin catalogs, collect contact details naturally."
        catalog = settings.catalog_summary or "Kurti Sets, Cotton Shirts, Denim, Tops, Custom Apparel."

        knowledge_base = settings.ai_knowledge_base or ""

        brain_text = f"""== COMPANY BRAIN & BUSINESS RULES (MODULE 1) ==
Company Name: {biz_name}
Business Description: {biz_desc}
Location: {location} | GST: {gst}

-- STRICT COMMERCIAL RULES (NEVER OVERRIDE THESE) --
1. Minimum Order Quantity (MOQ): {moq}
2. Pricing Tiers & Discounts: {pricing}
3. Payment Terms: {payment}
4. Shipping & Delivery: {shipping}
5. Return & Replacement Policy: {returns}
6. Product Catalog Overview: {catalog}
7. Owner Sales Strategy & Directives: {owner_notes}

-- GENERAL KNOWLEDGE BASE --
{knowledge_base}
"""
        return brain_text.strip()

class RAGEngine:
    """
    Module 2: Local RAG (Retrieval-Augmented Generation).
    Searches company knowledge chunks for exact evidence before generating responses.
    """
    @staticmethod
    def retrieve_relevant_chunks(db: Session, company_id: int, query_text: str, top_k: int = 3) -> str:
        if not query_text or not db:
            return ""

        chunks = db.query(models.CompanyKnowledgeChunk).filter(
            models.CompanyKnowledgeChunk.company_id == company_id
        ).all()

        if not chunks:
            return ""

        query_words = set(query_text.lower().split())

        scored_chunks = []
        for chunk in chunks:
            content_lower = (chunk.title + " " + chunk.content).lower()
            score = sum(1 for word in query_words if len(word) > 3 and word in content_lower)
            if score > 0:
                scored_chunks.append((score, chunk))

        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        top_chunks = scored_chunks[:top_k]

        if not top_chunks:
            return ""

        result = "== RELEVANT KNOWLEDGE BASE EVIDENCE (LOCAL RAG) ==\n"
        for _, chunk in top_chunks:
            result += f"[{chunk.category.upper()}] {chunk.title}:\n{chunk.content}\n\n"

        logger.info(f"[RAGEngine] Retrieved {len(top_chunks)} relevant knowledge chunks for query: '{query_text[:40]}...'")
        return result.strip()
