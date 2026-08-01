import datetime
import logging
from typing import List, Optional
from sqlalchemy.orm import Session
from . import models

logger = logging.getLogger("ai_memory")

class LongTermMemoryManager:
    """
    Module 4: Manages multi-month persistent customer memory.
    Ensures AI remembers past inquiries, preferences, and details across long gaps.
    """
    @staticmethod
    def get_customer_memory_context(db: Session, customer_id: int) -> str:
        if not db or not customer_id:
            return ""

        memories = db.query(models.CustomerLongTermMemory).filter(
            models.CustomerLongTermMemory.customer_id == customer_id
        ).all()

        if not memories:
            return ""

        context_str = "== LONG-TERM CUSTOMER MEMORY (MODULE 4) ==\n"
        for mem in memories:
            context_str += f"- {mem.key.replace('_', ' ').title()}: {mem.value}\n"

        logger.info(f"[MemoryManager] Loaded {len(memories)} long-term memory items for customer ID {customer_id}")
        return context_str.strip()

    @staticmethod
    def record_memory_fact(db: Session, customer_id: int, key: str, value: str):
        if not db or not customer_id or not key or not value:
            return

        existing = db.query(models.CustomerLongTermMemory).filter(
            models.CustomerLongTermMemory.customer_id == customer_id,
            models.CustomerLongTermMemory.key == key
        ).first()

        now_iso = datetime.datetime.utcnow().isoformat() + "Z"

        if existing:
            existing.value = value
            existing.updated_at = now_iso
        else:
            new_mem = models.CustomerLongTermMemory(
                customer_id=customer_id,
                key=key,
                value=value,
                created_at=now_iso,
                updated_at=now_iso
            )
            db.add(new_mem)

        try:
            db.commit()
            logger.info(f"[MemoryManager] Saved memory fact '{key}'='{value}' for customer {customer_id}")
        except Exception as e:
            logger.error(f"[MemoryManager] Error saving memory: {e}")
            db.rollback()
