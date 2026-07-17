import os
import time
import threading
import imaplib
import smtplib
import email
import hashlib
from email.header import decode_header
from email.message import EmailMessage
import datetime
import logging

from ...database import SessionLocal
from ... import models
from ...ai_service import generate_sales_reply

logger = logging.getLogger("email_service")

class EmailIntegrationService:
    def __init__(self):
        self.imap_server = "imap.gmail.com"
        self.smtp_server = "smtp.gmail.com"
        self.is_running = False
        self.last_error = None
        self.last_poll_time = None
        self.emails_processed = 0
        self._poll_interval = 15  # Poll every 15 seconds

    def start(self):
        logger.info("[Email] Starting multi-tenant IMAP polling service (interval: %ds).", self._poll_interval)
        self.is_running = True
        thread = threading.Thread(target=self._poll_inbox, daemon=True)
        thread.start()

    def get_status(self):
        return {
            "running": self.is_running,
            "last_poll": self.last_poll_time,
            "emails_processed": self.emails_processed,
            "last_error": self.last_error,
        }

    # ── On-demand fetch for a specific company ──────────────────
    def fetch_now(self, company_id: int) -> dict:
        """
        Called by the /integrations/email/fetch endpoint.
        Connects to IMAP, pulls UNSEEN emails, syncs to DB, returns count.
        """
        logger.info("[Email][Fetch] On-demand fetch triggered for company %d", company_id)
        db = SessionLocal()
        try:
            settings = db.query(models.Settings).filter(
                models.Settings.company_id == company_id
            ).first()

            if not settings or not settings.gmail_address or not settings.gmail_app_password:
                logger.warning("[Email][Fetch] No email credentials configured for company %d", company_id)
                return {"status": "no_credentials", "new_emails": 0}

            new_count = self._check_company_emails(db, settings)
            logger.info("[Email][Fetch] On-demand fetch complete for company %d: %d new emails", company_id, new_count)
            return {"status": "ok", "new_emails": new_count}
        except Exception as e:
            logger.error("[Email][Fetch] Error during on-demand fetch for company %d: %s", company_id, e)
            return {"status": "error", "error": str(e), "new_emails": 0}
        finally:
            db.close()

    # ── Background polling loop ─────────────────────────────────
    def _poll_inbox(self):
        backoff = self._poll_interval
        while self.is_running:
            db = SessionLocal()
            try:
                companies_with_email = db.query(models.Settings).filter(
                    models.Settings.gmail_address != None,
                    models.Settings.gmail_app_password != None,
                    models.Settings.gmail_address != "",
                    models.Settings.gmail_app_password != ""
                ).all()

                if companies_with_email:
                    logger.info("[Email][Poll] Polling %d company(ies) with configured email.", len(companies_with_email))
                
                for settings in companies_with_email:
                    self._check_company_emails(db, settings)

                self.last_poll_time = datetime.datetime.utcnow().isoformat() + "Z"
                self.last_error = None
                backoff = self._poll_interval
            except Exception as e:
                self.last_error = str(e)
                logger.error("[Email][Poll] Global Polling Error: %s", e)
                time.sleep(backoff)
                backoff = min(backoff * 2, 300)
            finally:
                db.close()
            
            time.sleep(self._poll_interval)

    # ── Check a single company's inbox ──────────────────────────
    def _check_company_emails(self, db, settings) -> int:
        email_address = settings.gmail_address.strip()
        app_password = settings.gmail_app_password.strip()
        company_id = settings.company_id
        new_count = 0

        mail = None
        try:
            logger.info("[Email][IMAP] Connecting to %s for company %d...", self.imap_server, company_id)
            mail = imaplib.IMAP4_SSL(self.imap_server, 993)
            mail.login(email_address, app_password)
            logger.info("[Email][IMAP] Login successful for %s", email_address)
            
            mail.select("INBOX")
            status, messages = mail.search(None, "UNSEEN")
            
            if status != "OK":
                logger.warning("[Email][IMAP] SEARCH returned non-OK status for %s: %s", email_address, status)
                return 0
                
            if not messages[0]:
                logger.info("[Email][IMAP] No new (UNSEEN) emails for %s", email_address)
                return 0

            email_ids = messages[0].split()
            logger.info("[Email][IMAP] Found %d new email(s) for %s (Company %d)", len(email_ids), email_address, company_id)

            for email_id in email_ids:
                try:
                    status, msg_data = mail.fetch(email_id, "(RFC822)")
                    if status != "OK":
                        logger.warning("[Email][IMAP] Failed to FETCH email id %s", email_id)
                        continue

                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            saved = self._parse_and_save(db, company_id, email_address, msg)
                            if saved:
                                new_count += 1
                except Exception as e:
                    logger.error("[Email][IMAP] Error processing email id %s for %s: %s", email_id, email_address, e)
        except imaplib.IMAP4.error as e:
            logger.error("[Email][IMAP] Authentication/Connection Error for %s: %s", email_address, e)
            self.last_error = f"IMAP Auth Error for {email_address}: {e}"
        except Exception as e:
            logger.error("[Email][IMAP] Connection Error for %s: %s", email_address, e)
            self.last_error = str(e)
        finally:
            if mail:
                try:
                    mail.logout()
                except:
                    pass
        
        return new_count

    # ── Parse raw email and save to DB (with dedup) ─────────────
    def _parse_and_save(self, db, company_id, company_email, msg) -> bool:
        # --- Message-ID for deduplication ---
        raw_message_id = msg.get("Message-ID", "")
        if not raw_message_id:
            # Generate a fingerprint from headers if no Message-ID
            raw_message_id = hashlib.sha256(
                f"{msg.get('From','')}{msg.get('Date','')}{msg.get('Subject','')}".encode()
            ).hexdigest()
        
        # --- Subject ---
        raw_subject = msg.get("Subject", "No Subject")
        subject_parts = decode_header(raw_subject)
        subject = ""
        for part, enc in subject_parts:
            if isinstance(part, bytes):
                subject += part.decode(enc or "utf-8", errors="replace")
            else:
                subject += str(part)

        # --- Sender ---
        sender_raw = msg.get("From", "")
        sender_email = sender_raw
        sender_name = sender_raw
        if "<" in sender_raw:
            sender_name = sender_raw.split("<")[0].strip().strip('"')
            sender_email = sender_raw.split("<")[1].split(">")[0].strip()

        if not sender_email or "@" not in sender_email:
            logger.warning("[Email][Parse] Skipping email with invalid sender: %s", sender_raw)
            return False

        # Skip emails from yourself to avoid loops
        if sender_email.lower() == company_email.lower():
            return False

        # Skip automated, spam, and marketing emails
        ignore_keywords = ["no-reply", "noreply", "newsletter", "marketing", "updates", "notifications", "do-not-reply", "mailer-daemon", "bounce"]
        ignore_domains = ["youtube.com", "google.com", "facebookmail.com", "twitter.com", "linkedin.com", "instagram.com", "github.com", "render.com"]
        
        email_lower = sender_email.lower()
        if any(kw in email_lower for kw in ignore_keywords) or any(email_lower.endswith(domain) for domain in ignore_domains):
            return False

        # --- Dedup Check: have we already stored this exact email? ---
        existing = db.query(models.Message).filter(
            models.Message.email_message_id == raw_message_id
        ).first()
        if existing:
            logger.info("[Email][Dedup] Skipping already-saved email (Message-ID: %s)", raw_message_id[:40])
            return False

        # --- Body ---
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                disposition = str(part.get("Content-Disposition", ""))
                if ctype == "text/plain" and "attachment" not in disposition:
                    try:
                        charset = part.get_content_charset() or "utf-8"
                        body = part.get_payload(decode=True).decode(charset, errors="replace")
                        break
                    except Exception:
                        pass
        else:
            try:
                charset = msg.get_content_charset() or "utf-8"
                body = msg.get_payload(decode=True).decode(charset, errors="replace")
            except Exception:
                pass

        body = body.strip() or "(No message body)"

        logger.info("[Email][Save] New email from %s, subject: '%s'", sender_email, subject[:60])
        self._process_incoming_email(db, company_id, company_email, sender_email, sender_name or sender_email, subject, body, raw_message_id)
        return True

    def _process_incoming_email(self, db, company_id, company_email, sender_email, sender_name, subject, body, message_id):
        try:
            # 1. Find or create Customer scoped to this company
            customer = db.query(models.Customer).filter(
                models.Customer.email == sender_email,
                models.Customer.company_id == company_id
            ).first()

            if not customer:
                logger.info("[Email][DB] Creating new customer: %s (Company %d)", sender_email, company_id)
                customer = models.Customer(
                    company_id=company_id,
                    name=sender_name,
                    email=sender_email,
                )
                db.add(customer)
                db.commit()
                db.refresh(customer)
            
            # 2. Find or create Email Conversation
            conversation = db.query(models.Conversation).filter(
                models.Conversation.customer_id == customer.id,
                models.Conversation.channel == "Email"
            ).first()

            if not conversation:
                deal = models.Deal(
                    company_id=company_id,
                    customer_id=customer.id,
                    stage="New Inquiry"
                )
                db.add(deal)
                db.commit()
                db.refresh(deal)

                conversation = models.Conversation(
                    customer_id=customer.id,
                    deal_id=deal.id,
                    channel="Email",
                    status="Open",
                    is_ai_managed=True,
                    unread=True,
                )
                db.add(conversation)
                db.commit()
                db.refresh(conversation)

            # 3. Add the message with email_message_id for dedup
            iso_time = datetime.datetime.utcnow().isoformat() + "Z"
            msg_count = db.query(models.Message).filter(
                models.Message.conversation_id == conversation.id
            ).count()

            full_text = f"Subject: {subject}\n\n{body}" if msg_count == 0 else body

            new_msg = models.Message(
                conversation_id=conversation.id,
                sender="customer",
                text=full_text,
                timestamp=iso_time,
                email_message_id=message_id,
            )
            db.add(new_msg)

            conversation.unread = True
            conversation.last_message_text = full_text[:120] + ("..." if len(full_text) > 120 else "")
            conversation.last_message_time = iso_time
            conversation.status = "Open"
            db.commit()

            self.emails_processed += 1
            logger.info("[Email][DB] Saved message from %s to DB (Company %d, Conv %d).", sender_email, company_id, conversation.id)

            # 4. AI Auto-reply
            settings = db.query(models.Settings).filter(models.Settings.company_id == company_id).first()
            if conversation.is_ai_managed and settings and settings.ai_enabled:
                self._send_auto_reply(db, company_id, company_email, customer, conversation, subject, body, settings)

        except Exception as e:
            logger.error("[Email][DB] Error processing %s: %s", sender_email, e)
            db.rollback()

    def _send_auto_reply(self, db, company_id, company_email, customer, conversation, original_subject, incoming_text, settings):
        logger.info("[Email][AI] Generating AI reply for %s...", customer.email)
        
        reply_text = generate_sales_reply(settings, customer, conversation, incoming_text)
        reply_subject = f"Re: {original_subject}" if not str(original_subject).startswith("Re:") else original_subject

        iso_time = datetime.datetime.utcnow().isoformat() + "Z"
        
        if settings.ai_auto_send:
            # OPTION A: Auto Send
            success = self.send_email(db, company_id, customer.email, reply_subject, reply_text)
            if success:
                ai_msg = models.Message(
                    conversation_id=conversation.id,
                    sender="ai",
                    text=reply_text,
                    timestamp=iso_time,
                )
                db.add(ai_msg)
                conversation.status = "Replied"
                conversation.last_message_text = reply_text[:120]
                conversation.last_message_time = iso_time
                db.commit()
                logger.info("[Email][AI] Auto-reply sent to %s", customer.email)
        else:
            # OPTION B: Draft Mode
            ai_draft = models.Message(
                conversation_id=conversation.id,
                sender="ai_draft",
                text=reply_text,
                timestamp=iso_time,
            )
            db.add(ai_draft)
            conversation.status = "Open"
            db.commit()
            logger.info("[Email][AI] Reply drafted for %s", customer.email)

    def send_email(self, db, company_id, to_email, subject, body):
        # Fetch the company's SMTP credentials
        settings = db.query(models.Settings).filter(models.Settings.company_id == company_id).first()
        if not settings or not settings.gmail_address or not settings.gmail_app_password:
            logger.error("[Email][SMTP] Cannot send - credentials not configured for company %d.", company_id)
            return False

        email_address = settings.gmail_address.strip()
        app_password = settings.gmail_app_password.strip()

        try:
            msg = EmailMessage()
            msg.set_content(body)
            msg["Subject"] = subject
            msg["From"] = email_address
            msg["To"] = to_email

            with smtplib.SMTP_SSL(self.smtp_server, 465) as server:
                server.login(email_address, app_password)
                server.send_message(msg)

            logger.info("[Email][SMTP] Email sent to %s via %s", to_email, email_address)
            return True
        except Exception as e:
            logger.error("[Email][SMTP] Error for %s: %s", email_address, e)
            self.last_error = str(e)
            return False

email_service = EmailIntegrationService()
