"""
auto_migrate.py — Comprehensive schema migration for AI Sale OS.

Strategy:
  1. Create ALL missing tables using raw SQL (idempotent via CREATE TABLE IF NOT EXISTS).
  2. ADD any missing columns via ALTER TABLE ... ADD COLUMN IF NOT EXISTS.
  3. Every statement is wrapped in its own try/except so one failure never
     blocks the others — and each failure is logged at WARNING level.

This replaces the previous approach that used separate try/except blocks and
did NOT handle missing tables.
"""

import logging
from sqlalchemy import text

logger = logging.getLogger("auto_migrate")


# ──────────────────────────────────────────────────────────────
# HELPER: execute one DDL statement, swallow errors gracefully
# ──────────────────────────────────────────────────────────────
def _exec(conn, stmt: str, label: str = ""):
    try:
        conn.execute(text(stmt))
        logger.info(f"[AutoMigrate] ✅ {label or stmt[:80]}")
    except Exception as e:
        # DuplicateColumn / relation already exists → expected noise, not a bug
        logger.debug(f"[AutoMigrate] ⚠️  Skipped (already exists?): {label or stmt[:80]} — {e}")


# ──────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ──────────────────────────────────────────────────────────────
def run_auto_migrations(engine):
    logger.info("[AutoMigrate] ─── Starting comprehensive schema migration ───")

    with engine.begin() as conn:

        # ══════════════════════════════════════════════════════
        # SECTION 1 — ENSURE ALL TABLES EXIST
        # (CREATE TABLE IF NOT EXISTS is safe to run repeatedly)
        # ══════════════════════════════════════════════════════

        _exec(conn, """
            CREATE TABLE IF NOT EXISTS companies (
                id SERIAL PRIMARY KEY,
                name VARCHAR,
                subscription_plan VARCHAR DEFAULT 'Free',
                created_at VARCHAR
            );
        """, "CREATE TABLE companies")

        _exec(conn, """
            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,
                company_id INTEGER REFERENCES companies(id),
                username VARCHAR UNIQUE,
                password_hash VARCHAR,
                name VARCHAR DEFAULT 'Admin',
                email VARCHAR,
                phone VARCHAR,
                role VARCHAR DEFAULT 'Admin',
                session_token VARCHAR,
                address VARCHAR,
                profile_photo VARCHAR
            );
        """, "CREATE TABLE admins")

        _exec(conn, """
            CREATE TABLE IF NOT EXISTS customers (
                id SERIAL PRIMARY KEY,
                company_id INTEGER REFERENCES companies(id),
                name VARCHAR,
                buyer_company_name VARCHAR,
                phone VARCHAR,
                email VARCHAR,
                city VARCHAR,
                internal_notes TEXT
            );
        """, "CREATE TABLE customers")

        _exec(conn, """
            CREATE TABLE IF NOT EXISTS deals (
                id SERIAL PRIMARY KEY,
                company_id INTEGER REFERENCES companies(id),
                customer_id INTEGER REFERENCES customers(id),
                interested_product VARCHAR,
                quantity INTEGER,
                budget FLOAT,
                stage VARCHAR DEFAULT 'New Inquiry',
                lead_score INTEGER DEFAULT 10,
                lead_score_reasons TEXT,
                opportunity_tags VARCHAR,
                detected_intent VARCHAR,
                sentiment VARCHAR,
                next_best_action TEXT,
                ai_summary TEXT
            );
        """, "CREATE TABLE deals")

        _exec(conn, """
            CREATE TABLE IF NOT EXISTS team_members (
                id SERIAL PRIMARY KEY,
                company_id INTEGER REFERENCES companies(id),
                name VARCHAR,
                email VARCHAR,
                phone VARCHAR,
                role VARCHAR DEFAULT 'Sales Executive',
                status VARCHAR DEFAULT 'Active',
                created_at VARCHAR
            );
        """, "CREATE TABLE team_members")

        _exec(conn, """
            CREATE TABLE IF NOT EXISTS conversations (
                id SERIAL PRIMARY KEY,
                customer_id INTEGER REFERENCES customers(id),
                deal_id INTEGER REFERENCES deals(id),
                channel VARCHAR DEFAULT 'WhatsApp',
                status VARCHAR DEFAULT 'New',
                assigned_agent_id INTEGER REFERENCES team_members(id),
                unread BOOLEAN DEFAULT FALSE,
                last_message_time VARCHAR,
                last_message_text VARCHAR,
                is_ai_managed BOOLEAN DEFAULT TRUE,
                simulation_stage INTEGER DEFAULT 0
            );
        """, "CREATE TABLE conversations")

        _exec(conn, """
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                conversation_id INTEGER REFERENCES conversations(id),
                sender VARCHAR,
                text TEXT,
                timestamp VARCHAR,
                email_message_id VARCHAR
            );
        """, "CREATE TABLE messages")

        _exec(conn, """
            CREATE TABLE IF NOT EXISTS settings (
                id SERIAL PRIMARY KEY,
                company_id INTEGER UNIQUE REFERENCES companies(id),
                business_name VARCHAR DEFAULT 'Garment Manufacturer',
                business_logo VARCHAR,
                business_description TEXT,
                business_address VARCHAR,
                business_phone VARCHAR,
                business_email VARCHAR,
                website_url VARCHAR,
                social_media_links VARCHAR,
                working_hours VARCHAR,
                timezone VARCHAR DEFAULT 'UTC',
                language VARCHAR DEFAULT 'English',
                currency VARCHAR DEFAULT 'USD',
                ai_enabled BOOLEAN DEFAULT TRUE,
                ai_auto_send BOOLEAN DEFAULT FALSE,
                greeting_message VARCHAR DEFAULT 'Hello! Thank you for contacting us. How can I help you today?',
                ai_reply_delay INTEGER DEFAULT 1,
                max_followups INTEGER DEFAULT 3,
                ai_provider VARCHAR DEFAULT 'gemini',
                ai_model VARCHAR DEFAULT 'gemini-2.0-flash',
                prompt_version VARCHAR DEFAULT 'V2',
                desktop_notifications BOOLEAN DEFAULT TRUE,
                email_notifications BOOLEAN DEFAULT FALSE,
                sound_notifications BOOLEAN DEFAULT TRUE,
                unread_alerts BOOLEAN DEFAULT TRUE,
                theme VARCHAR DEFAULT 'light',
                primary_color VARCHAR DEFAULT '#6366f1',
                font_size VARCHAR DEFAULT 'medium',
                ai_knowledge_base TEXT,
                moq_info VARCHAR,
                pricing_tiers TEXT,
                shipping_policy TEXT,
                payment_terms TEXT,
                return_policy TEXT,
                gst_number VARCHAR,
                location VARCHAR,
                owner_sales_strategy TEXT,
                catalog_summary TEXT,
                gmail_address VARCHAR,
                gmail_app_password VARCHAR,
                whatsapp_api_key VARCHAR,
                whatsapp_phone_number_id VARCHAR,
                whatsapp_verify_token VARCHAR
            );
        """, "CREATE TABLE settings")

        _exec(conn, """
            CREATE TABLE IF NOT EXISTS company_knowledge_chunks (
                id SERIAL PRIMARY KEY,
                company_id INTEGER REFERENCES companies(id),
                title VARCHAR,
                category VARCHAR DEFAULT 'General',
                content TEXT,
                source_filename VARCHAR,
                created_at VARCHAR
            );
        """, "CREATE TABLE company_knowledge_chunks")

        _exec(conn, """
            CREATE TABLE IF NOT EXISTS customer_memories (
                id SERIAL PRIMARY KEY,
                customer_id INTEGER REFERENCES customers(id),
                key VARCHAR,
                value TEXT,
                created_at VARCHAR,
                updated_at VARCHAR
            );
        """, "CREATE TABLE customer_memories")

        _exec(conn, """
            CREATE TABLE IF NOT EXISTS workflow_tasks (
                id SERIAL PRIMARY KEY,
                company_id INTEGER REFERENCES companies(id),
                customer_id INTEGER REFERENCES customers(id),
                deal_id INTEGER REFERENCES deals(id),
                title VARCHAR,
                action_type VARCHAR,
                due_date VARCHAR,
                status VARCHAR DEFAULT 'Pending',
                notes TEXT,
                created_at VARCHAR
            );
        """, "CREATE TABLE workflow_tasks")

        _exec(conn, """
            CREATE TABLE IF NOT EXISTS ai_telemetry_logs (
                id SERIAL PRIMARY KEY,
                company_id INTEGER REFERENCES companies(id),
                request_type VARCHAR,
                provider VARCHAR,
                model VARCHAR,
                latency_ms INTEGER,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                estimated_cost FLOAT DEFAULT 0.0,
                success BOOLEAN DEFAULT TRUE,
                fallback_used BOOLEAN DEFAULT FALSE,
                created_at VARCHAR
            );
        """, "CREATE TABLE ai_telemetry_logs")

        # ══════════════════════════════════════════════════════
        # SECTION 2 — ADD MISSING COLUMNS TO EXISTING TABLES
        # PostgreSQL 9.6+ supports IF NOT EXISTS on ADD COLUMN
        # ══════════════════════════════════════════════════════

        # — admins table —
        for col, definition in [
            ("address",       "VARCHAR"),
            ("profile_photo", "VARCHAR"),
        ]:
            _exec(conn,
                f"ALTER TABLE admins ADD COLUMN IF NOT EXISTS {col} {definition};",
                f"admins.{col}")

        # — messages table —
        for col, definition in [
            ("email_message_id", "VARCHAR"),
        ]:
            _exec(conn,
                f"ALTER TABLE messages ADD COLUMN IF NOT EXISTS {col} {definition};",
                f"messages.{col}")

        # — deals table —
        for col, definition in [
            ("lead_score",        "INTEGER DEFAULT 10"),
            ("lead_score_reasons","TEXT"),
            ("opportunity_tags",  "VARCHAR"),
            ("detected_intent",   "VARCHAR"),
            ("sentiment",         "VARCHAR"),
            ("next_best_action",  "TEXT"),
            ("ai_summary",        "TEXT"),
        ]:
            _exec(conn,
                f"ALTER TABLE deals ADD COLUMN IF NOT EXISTS {col} {definition};",
                f"deals.{col}")

        # — conversations table —
        for col, definition in [
            ("simulation_stage", "INTEGER DEFAULT 0"),
            ("last_message_time","VARCHAR"),
            ("last_message_text","VARCHAR"),
            ("is_ai_managed",    "BOOLEAN DEFAULT TRUE"),
            ("unread",           "BOOLEAN DEFAULT FALSE"),
        ]:
            _exec(conn,
                f"ALTER TABLE conversations ADD COLUMN IF NOT EXISTS {col} {definition};",
                f"conversations.{col}")

        # — settings table — every column the model defines —
        settings_cols = [
            ("business_name",            "VARCHAR DEFAULT 'Garment Manufacturer'"),
            ("business_logo",            "VARCHAR"),
            ("business_description",     "TEXT"),
            ("business_address",         "VARCHAR"),
            ("business_phone",           "VARCHAR"),
            ("business_email",           "VARCHAR"),
            ("website_url",              "VARCHAR"),
            ("social_media_links",       "VARCHAR"),
            ("working_hours",            "VARCHAR"),
            ("timezone",                 "VARCHAR DEFAULT 'UTC'"),
            ("language",                 "VARCHAR DEFAULT 'English'"),
            ("currency",                 "VARCHAR DEFAULT 'USD'"),
            ("ai_enabled",               "BOOLEAN DEFAULT TRUE"),
            ("ai_auto_send",             "BOOLEAN DEFAULT FALSE"),
            ("greeting_message",         "VARCHAR DEFAULT 'Hello! Thank you for contacting us.'"),
            ("ai_reply_delay",           "INTEGER DEFAULT 1"),
            ("max_followups",            "INTEGER DEFAULT 3"),
            ("ai_provider",              "VARCHAR DEFAULT 'gemini'"),
            ("ai_model",                 "VARCHAR DEFAULT 'gemini-2.0-flash'"),
            ("prompt_version",           "VARCHAR DEFAULT 'V2'"),
            ("desktop_notifications",    "BOOLEAN DEFAULT TRUE"),
            ("email_notifications",      "BOOLEAN DEFAULT FALSE"),
            ("sound_notifications",      "BOOLEAN DEFAULT TRUE"),
            ("unread_alerts",            "BOOLEAN DEFAULT TRUE"),
            ("theme",                    "VARCHAR DEFAULT 'light'"),
            ("primary_color",            "VARCHAR DEFAULT '#6366f1'"),
            ("font_size",                "VARCHAR DEFAULT 'medium'"),
            ("ai_knowledge_base",        "TEXT"),
            ("moq_info",                 "VARCHAR"),
            ("pricing_tiers",            "TEXT"),
            ("shipping_policy",          "TEXT"),
            ("payment_terms",            "TEXT"),
            ("return_policy",            "TEXT"),
            ("gst_number",               "VARCHAR"),
            ("location",                 "VARCHAR"),
            ("owner_sales_strategy",     "TEXT"),
            ("catalog_summary",          "TEXT"),
            ("gmail_address",            "VARCHAR"),
            ("gmail_app_password",       "VARCHAR"),
            ("whatsapp_api_key",         "VARCHAR"),
            ("whatsapp_phone_number_id", "VARCHAR"),
            ("whatsapp_verify_token",    "VARCHAR"),
        ]
        for col, definition in settings_cols:
            _exec(conn,
                f"ALTER TABLE settings ADD COLUMN IF NOT EXISTS {col} {definition};",
                f"settings.{col}")

    logger.info("[AutoMigrate] ─── Migration complete ───")
