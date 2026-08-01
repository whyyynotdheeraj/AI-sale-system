import datetime
import logging
from sqlalchemy.orm import Session
from . import models

logger = logging.getLogger("ai_telemetry")

# Token cost estimates per 1,000 tokens (approximate USD rates)
PROVIDER_COSTS = {
    "gemini": {"input": 0.0001, "output": 0.0004},
    "openai": {"input": 0.0015, "output": 0.0020},
    "anthropic": {"input": 0.0030, "output": 0.0150},
    "groq": {"input": 0.0001, "output": 0.0002},
    "openrouter": {"input": 0.0010, "output": 0.0020},
}

def record_telemetry(
    db: Session,
    company_id: int,
    request_type: str,
    provider: str,
    model: str,
    latency_ms: int,
    input_tokens: int = 0,
    output_tokens: int = 0,
    success: bool = True,
    fallback_used: bool = False
) -> models.AITelemetryLog:
    """
    Logs every AI operation's execution details for Module 12 (AI Telemetry & Analytics).
    """
    p_lower = provider.lower()
    rates = PROVIDER_COSTS.get(p_lower, {"input": 0.0005, "output": 0.0015})
    estimated_cost = (input_tokens / 1000.0 * rates["input"]) + (output_tokens / 1000.0 * rates["output"])

    log_entry = models.AITelemetryLog(
        company_id=company_id,
        request_type=request_type,
        provider=provider,
        model=model,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost=round(estimated_cost, 6),
        success=success,
        fallback_used=fallback_used,
        created_at=datetime.datetime.utcnow().isoformat() + "Z"
    )

    try:
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        logger.info(f"[Telemetry] Logged {request_type} via {provider}/{model} ({latency_ms}ms, est. ${estimated_cost:.6f})")
    except Exception as e:
        logger.error(f"[Telemetry] Failed to record telemetry: {e}")
        db.rollback()

    return log_entry
