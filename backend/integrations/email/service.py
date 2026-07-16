import os
import time
import threading
import imaplib
import smtplib
import email
from email.header import decode_header
from email.message import EmailMessage
import datetime

from ...database import SessionLocal
from ... import models

class EmailIntegrationService:
    def __init__(self):
        self.imap_server = "imap.gmail.com"
        self.smtp_server = "smtp.gmail.com"
        self.is_running = False
        self.last_error = None
        self.last_poll_time = None
        self.emails_processed = 0

    def start(self):
        print(f"[Email] Starting multi-tenant IMAP polling service.")
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

    def _poll_inbox(self):
        backoff = 30
        while self.is_running:
            db = SessionLocal()
            try:
                # Find all companies that have gmail configured
                companies_with_email = db.query(models.Settings).filter(
                    models.Settings.gmail_address != None,
                    models.Settings.gmail_app_password != None,
                    models.Settings.gmail_address != "",
                    models.Settings.gmail_app_password != ""
                ).all()

                for settings in companies_with_email:
                    self._check_company_emails(db, settings)

                self.last_poll_time = datetime.datetime.utcnow().isoformat() + "Z"
                self.last_error = None
                backoff = 30
            except Exception as e:
                self.last_error = str(e)
                print(f"[Email] Global Polling Error: {e}")
                time.sleep(backoff)
                backoff = min(backoff * 2, 300)
            finally:
                db.close()
            
            time.sleep(30) # Poll every 30 seconds

    def _check_company_emails(self, db, settings):
        email_address = settings.gmail_address.strip()
        app_password = settings.gmail_app_password.strip()
        company_id = settings.company_id

        mail = None
        try:
            mail = imaplib.IMAP4_SSL(self.imap_server, 993)
            mail.login(email_address, app_password)
            
            mail.select("INBOX")
            status, messages = mail.search(None, "UNSEEN")
            if status != "OK" or not messages[0]:
                return

            email_ids = messages[0].split()
            print(f"[Email] Found {len(email_ids)} new email(s) for {email_address} (Company {company_id})")

            for email_id in email_ids:
                try:
                    status, msg_data = mail.fetch(email_id, "(RFC822)")
                    if status != "OK":
                        continue

                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            self._parse_and_save(db, company_id, email_address, msg)
                except Exception as e:
                    print(f"[Email] Error processing email id {email_id} for {email_address}: {e}")
        except Exception as e:
            print(f"[Email] Connection Error for {email_address}: {e}")
        finally:
            if mail:
                try:
                    mail.logout()
                except:
                    pass

    def _parse_and_save(self, db, company_id, company_email, msg):
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
            return

        # Skip emails from yourself to avoid loops
        if sender_email.lower() == company_email.lower():
            return

        # Skip automated, spam, and marketing emails
        ignore_keywords = ["no-reply", "noreply", "newsletter", "marketing", "updates", "notifications", "do-not-reply", "mailer-daemon", "bounce"]
        ignore_domains = ["youtube.com", "google.com", "facebookmail.com", "twitter.com", "linkedin.com", "instagram.com", "github.com", "render.com"]
        
        email_lower = sender_email.lower()
        if any(kw in email_lower for kw in ignore_keywords) or any(email_lower.endswith(domain) for domain in ignore_domains):
            return

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

        self._process_incoming_email(db, company_id, company_email, sender_email, sender_name or sender_email, subject, body)

    def _process_incoming_email(self, db, company_id, company_email, sender_email, sender_name, subject, body):
        try:
            # 1. Find or create Customer scoped to this company
            customer = db.query(models.Customer).filter(
                models.Customer.email == sender_email,
                models.Customer.company_id == company_id
            ).first()

            if not customer:
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

            # 3. Add the message
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
            )
            db.add(new_msg)

            conversation.unread = True
            conversation.last_message_text = full_text[:120] + ("..." if len(full_text) > 120 else "")
            conversation.last_message_time = iso_time
            conversation.status = "Open"
            db.commit()

            self.emails_processed += 1
            print(f"[Email] Saved message from {sender_email} to DB (Company {company_id}).")

            # 4. AI Auto-reply
            if conversation.is_ai_managed:
                self._send_auto_reply(db, company_id, company_email, customer, conversation, subject)

        except Exception as e:
            print(f"[Email] DB Error processing {sender_email}: {e}")
            db.rollback()

    def _send_auto_reply(self, db, company_id, company_email, customer, conversation, original_subject):
        first_name = customer.name.split(" ")[0] if customer.name else "there"
        reply_text = (
            f"Hi {first_name},\n\n"
            f"Thank you for reaching out! We have received your email and our team will review it and get back to you as soon as possible.\n\n"
            f"Best regards,\nAI Sales OS Team"
        )
        reply_subject = f"Re: {original_subject}" if not str(original_subject).startswith("Re:") else original_subject

        success = self.send_email(db, company_id, customer.email, reply_subject, reply_text)
        if success:
            iso_time = datetime.datetime.utcnow().isoformat() + "Z"
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
            print(f"[Email] AI auto-reply sent to {customer.email}")

    def send_email(self, db, company_id, to_email, subject, body):
        # Fetch the company's SMTP credentials
        settings = db.query(models.Settings).filter(models.Settings.company_id == company_id).first()
        if not settings or not settings.gmail_address or not settings.gmail_app_password:
            print(f"[Email] Cannot send - credentials not configured for company {company_id}.")
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

            print(f"[Email] Email sent to {to_email} via {email_address}")
            return True
        except Exception as e:
            print(f"[Email] SMTP Error for {email_address}: {e}")
            self.last_error = str(e)
            return False

email_service = EmailIntegrationService()
