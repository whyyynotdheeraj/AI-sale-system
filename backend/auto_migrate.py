import logging
from sqlalchemy import text

logger = logging.getLogger("auto_migrate")

def run_auto_migrations(engine):
    """
    Runs ALTER TABLE statements to add missing columns in PostgreSQL/SQLite.
    This is a lightweight alternative to Alembic for simple column additions.
    """
    logger.info("Running auto-migrations for new schema columns...")
    
    # SQLite doesn't support IF NOT EXISTS in ADD COLUMN until newer versions,
    # and PostgreSQL does. But we can just try/except each ALTER statement.
    
    statements = [
        # deals table
        "ALTER TABLE deals ADD COLUMN lead_score INTEGER DEFAULT 10;",
        "ALTER TABLE deals ADD COLUMN lead_score_reasons TEXT;",
        "ALTER TABLE deals ADD COLUMN opportunity_tags VARCHAR;",
        "ALTER TABLE deals ADD COLUMN detected_intent VARCHAR;",
        "ALTER TABLE deals ADD COLUMN sentiment VARCHAR;",
        "ALTER TABLE deals ADD COLUMN next_best_action TEXT;",
        "ALTER TABLE deals ADD COLUMN ai_summary TEXT;",
        
        # settings table - Provider configs
        "ALTER TABLE settings ADD COLUMN ai_provider VARCHAR DEFAULT 'gemini';",
        "ALTER TABLE settings ADD COLUMN ai_model VARCHAR DEFAULT 'gemini-2.0-flash';",
        "ALTER TABLE settings ADD COLUMN prompt_version VARCHAR DEFAULT 'V2';",
        
        # settings table - Company Brain configs
        "ALTER TABLE settings ADD COLUMN ai_knowledge_base TEXT;",
        "ALTER TABLE settings ADD COLUMN moq_info VARCHAR;",
        "ALTER TABLE settings ADD COLUMN pricing_tiers TEXT;",
        "ALTER TABLE settings ADD COLUMN shipping_policy TEXT;",
        "ALTER TABLE settings ADD COLUMN payment_terms TEXT;",
        "ALTER TABLE settings ADD COLUMN return_policy TEXT;",
        "ALTER TABLE settings ADD COLUMN gst_number VARCHAR;",
        "ALTER TABLE settings ADD COLUMN location VARCHAR;",
        "ALTER TABLE settings ADD COLUMN owner_sales_strategy TEXT;",
        "ALTER TABLE settings ADD COLUMN catalog_summary TEXT;"
    ]
    
    with engine.begin() as conn:
        for stmt in statements:
            try:
                conn.execute(text(stmt))
                logger.info(f"Successfully executed: {stmt}")
            except Exception as e:
                # Expected if column already exists
                logger.debug(f"Skipped execution (likely already exists): {stmt}")
                pass
    
    logger.info("Auto-migrations complete.")
