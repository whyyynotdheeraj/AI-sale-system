import json
import logging
import datetime
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from . import models, ai_provider

logger = logging.getLogger("sales_intelligence")

class SalesIntelligenceEngine:
    """
    Implements Module 6 (AI Lead Scoring 0-100), Module 7 (Opportunity Detection),
    and Module 9 (Workflow Intent Detection).
    """
    @staticmethod
    def analyze_sales_intelligence(
        db: Session,
        company_id: int,
        customer: models.Customer,
        deal: Optional[models.Deal],
        latest_message: str,
        conversation_history: str = ""
    ) -> Dict[str, Any]:
        """
        Uses AI to extract structured Lead Score (0-100), Score Reasons, Opportunity Tags,
        Detected Intent, Sentiment, Next Recommended Action, and Workflow Commitments.
        """
        system_prompt = """You are an expert AI Sales Intelligence Evaluator.
Analyze the customer's latest message and past context carefully.
Output your analysis in STRICT, VALID JSON with NO markdown formatting around it.

JSON Format:
{
  "lead_score": 85,
  "score_reasons": ["Urgent delivery required", "Specific quantity mentioned (200 pcs)", "Price accepted"],
  "opportunity_tags": ["Bulk Order", "High Value Prospect"],
  "detected_intent": "Bulk Purchase Order Inquiry",
  "sentiment": "Enthusiastic / Ready to Buy",
  "next_best_action": "Send quotation with 5% bulk volume discount immediately",
  "workflow_commitment": {
     "has_commitment": true,
     "task_title": "Follow up on promised bulk order payment",
     "due_days": 3,
     "action_type": "WhatsApp_Followup"
  }
}
"""

        user_content = f"""Customer Name: {customer.name if customer else 'Customer'}
Customer Email: {customer.email if customer else 'Unknown'}
Deal Stage: {deal.stage if deal else 'New Inquiry'}
Deal Budget: {deal.budget if deal and deal.budget else 'Not set'}
Latest Customer Message: "{latest_message}"
Recent Context: {conversation_history}
"""

        try:
            res = ai_provider.execute_with_retry_and_fallback(
                provider_name="gemini",
                system_instruction=system_prompt,
                contents=[{"role": "user", "text": user_content}],
                temperature=0.2,
                max_tokens=500
            )

            raw_text = res["text"].strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text.replace("```json", "").replace("```", "").strip()

            analysis = json.loads(raw_text)

            # Persist results to DB deal record if present
            if deal:
                deal.lead_score = int(analysis.get("lead_score", deal.lead_score or 10))
                deal.lead_score_reasons = json.dumps(analysis.get("score_reasons", []))
                deal.opportunity_tags = ", ".join(analysis.get("opportunity_tags", []))
                deal.detected_intent = analysis.get("detected_intent")
                deal.sentiment = analysis.get("sentiment")
                deal.next_best_action = analysis.get("next_best_action")

            # Check and create Module 9 Workflow Task if commitment detected
            wf = analysis.get("workflow_commitment")
            if wf and wf.get("has_commitment") and deal:
                due_days = int(wf.get("due_days", 2))
                due_date_iso = (datetime.datetime.utcnow() + datetime.timedelta(days=due_days)).strftime("%Y-%m-%d")

                task = models.WorkflowTask(
                    company_id=company_id,
                    customer_id=customer.id if customer else 0,
                    deal_id=deal.id,
                    title=wf.get("task_title", "Customer Commitment Followup"),
                    action_type=wf.get("action_type", "Task"),
                    due_date=due_date_iso,
                    status="Pending",
                    notes=f"Auto-generated commitment from message: '{latest_message[:80]}'",
                    created_at=datetime.datetime.utcnow().isoformat() + "Z"
                )
                db.add(task)

            db.commit()
            logger.info(f"[SalesIntelligence] Analyzed customer {customer.id if customer else 'Unknown'}: Score {analysis.get('lead_score')}/100")
            return analysis

        except Exception as e:
            logger.error(f"[SalesIntelligence] Fallback analysis used due to error: {e}")
            fallback_analysis = {
                "lead_score": deal.lead_score if deal else 50,
                "score_reasons": ["Standard inquiry engaged"],
                "opportunity_tags": ["Inquiry"],
                "detected_intent": "General Inquiry",
                "sentiment": "Neutral",
                "next_best_action": "Qualify lead product requirements and target quantity",
                "workflow_commitment": {"has_commitment": False}
            }
            return fallback_analysis
