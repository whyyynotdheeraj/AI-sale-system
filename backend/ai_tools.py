import datetime
import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from . import models

logger = logging.getLogger("ai_tools")

class AIToolExecutor:
    """
    Module 3: Autonomous CRM Tool Calling.
    Executes real database actions (Create Lead Task, Update Stage, Assign Rep, Update Lead Score)
    in response to AI decisions.
    """
    @staticmethod
    def create_followup_task(db: Session, company_id: int, customer_id: int, deal_id: Optional[int], task_title: str, due_days: int = 2) -> Dict[str, Any]:
        due_date = (datetime.datetime.utcnow() + datetime.timedelta(days=due_days)).strftime("%Y-%m-%d")
        now_iso = datetime.datetime.utcnow().isoformat() + "Z"

        task = models.WorkflowTask(
            company_id=company_id,
            customer_id=customer_id,
            deal_id=deal_id,
            title=task_title,
            action_type="Task",
            due_date=due_date,
            status="Pending",
            notes="Autonomous AI Tool Action",
            created_at=now_iso
        )
        db.add(task)
        db.commit()
        logger.info(f"[AITools] Action Executed: Created Task '{task_title}' due {due_date}")
        return {"status": "success", "action": "create_task", "task_id": task.id, "due_date": due_date}

    @staticmethod
    def update_deal_stage(db: Session, deal_id: int, new_stage: str) -> Dict[str, Any]:
        deal = db.query(models.Deal).filter(models.Deal.id == deal_id).first()
        if not deal:
            return {"status": "error", "message": "Deal not found"}

        old_stage = deal.stage
        deal.stage = new_stage
        db.commit()
        logger.info(f"[AITools] Action Executed: Updated Deal #{deal_id} Stage '{old_stage}' -> '{new_stage}'")
        return {"status": "success", "action": "update_stage", "old_stage": old_stage, "new_stage": new_stage}

    @staticmethod
    def assign_sales_rep(db: Session, conv_id: int, team_member_id: int) -> Dict[str, Any]:
        conv = db.query(models.Conversation).filter(models.Conversation.id == conv_id).first()
        if not conv:
            return {"status": "error", "message": "Conversation not found"}

        conv.assigned_agent_id = team_member_id
        db.commit()
        logger.info(f"[AITools] Action Executed: Assigned Conversation #{conv_id} to Rep ID {team_member_id}")
        return {"status": "success", "action": "assign_rep", "assigned_agent_id": team_member_id}
