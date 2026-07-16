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
        self.email_address = os.environ.get("GMAIL_ADDRESS")
        self.app_password = os.environ.get("GMAIL_APP_PASSWORD")
        self.imap_server = "imap.gmail.com"
        self.smtp_server = "smtp.gmail.com"
        self.is_running = False

    def start(self):
        if not self.email_address or not self.app_password or self.email_address == "your_email@gmail.com":
            print("Email Integration: GMAIL_ADDRESS or GMAIL_APP_PASSWORD not set. Email polling disabled.")
            return

        self.is_running = True
        thread = threading.Thread(target=self._poll_inbox, daemon=True)
        thread.start()
        print(f"Email Integration: Started IMAP polling for {self.email_address}")

    def _poll_inbox(self):
        while self.is_running:
            try:
                self._check_for_new_emails()
            except Exception as e:
                print(f"Email Integration Error (IMAP): {e}")
            
            # Wait 30 seconds before checking again
            time.sleep(30)

    def _check_for_new_emails(self):
        # Connect to IMAP
        mail = imaplib.IMAP4_SSL(self.imap_server)
        mail.login(self.email_address, self.app_password)
        mail.select("inbox")

        # Search for UNSEEN emails
        status, messages = mail.search(None, "UNSEEN")
        if status != "OK":
            mail.logout()
            return

        email_ids = messages[0].split()
        for email_id in email_ids:
            status, msg_data = mail.fetch(email_id, "(RFC822)")
            if status != "OK":
                continue

            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    # Extract Subject
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding if encoding else "utf-8")
                    
                    # Extract Sender
                    sender_raw = msg.get("From")
                    # Usually formatted as "Name <email@domain.com>"
                    sender_email = sender_raw
                    sender_name = sender_raw
                    if "<" in sender_raw and ">" in sender_raw:
                        sender_name = sender_raw.split("<")[0].strip()
                        sender_email = sender_raw.split("<")[1].split(">")[0].strip()
                    
                    # Extract Body
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            content_disposition = str(part.get("Content-Disposition"))
                            
                            if content_type == "text/plain" and "attachment" not in content_disposition:
                                try:
                                    body = part.get_payload(decode=True).decode()
                                    break # Get the first text part
                                except:
                                    pass
                    else:
                        try:
                            body = msg.get_payload(decode=True).decode()
                        except:
                            pass

                    self._process_incoming_email(sender_email, sender_name, subject, body)

        mail.logout()

    def _process_incoming_email(self, sender_email, sender_name, subject, body):
        if not body:
            return

        db = SessionLocal()
        try:
            # 1. Find or create customer
            customer = db.query(models.Customer).filter(models.Customer.email == sender_email).first()
            if not customer:
                customer = models.Customer(
                    name=sender_name.replace('"', ''),
                    email=sender_email,
                    channel="Email"
                )
                db.add(customer)
                db.commit()
                db.refresh(customer)

            # 2. Find or create conversation
            conversation = db.query(models.Conversation).filter(
                models.Conversation.customer_id == customer.id,
                models.Conversation.channel == "Email"
            ).first()

            if not conversation:
                conversation = models.Conversation(
                    customer_id=customer.id,
                    channel="Email",
                    status="Open",
                    is_ai_managed=True
                )
                db.add(conversation)
                db.commit()
                db.refresh(conversation)

            # 3. Add Message
            iso_time = datetime.datetime.utcnow().isoformat() + "Z"
            
            # Prefix subject if it's the first message
            if db.query(models.Message).filter(models.Message.conversation_id == conversation.id).count() == 0:
                full_text = f"Subject: {subject}\n\n{body.strip()}"
            else:
                full_text = body.strip()

            new_msg = models.Message(
                conversation_id=conversation.id,
                sender="customer",
                text=full_text,
                timestamp=iso_time
            )
            db.add(new_msg)
            
            # Update conversation
            conversation.unread = True
            conversation.last_message_text = full_text[:100] + ("..." if len(full_text) > 100 else "")
            conversation.last_message_time = iso_time
            db.commit()

            # 4. Handle AI Reply if managed
            if conversation.is_ai_managed:
                self._generate_and_send_ai_reply(db, customer, conversation, subject)
                
        finally:
            db.close()

    def _generate_and_send_ai_reply(self, db, customer, conversation, original_subject):
        # Very simple AI simulated response for now
        reply_text = f"Hi {customer.name.split(' ')[0]},\n\nThank you for your email. Our AI Sales Agent has received your message and our team will get back to you shortly.\n\nBest regards,\nAI Sales OS Team"
        
        reply_subject = original_subject if str(original_subject).startswith("Re:") else f"Re: {original_subject}"
        
        # Send the email via SMTP
        success = self.send_email(customer.email, reply_subject, reply_text)
        
        if success:
            iso_time = datetime.datetime.utcnow().isoformat() + "Z"
            ai_msg = models.Message(
                conversation_id=conversation.id,
                sender="ai",
                text=reply_text,
                timestamp=iso_time
            )
            db.add(ai_msg)
            
            conversation.status = "Replied"
            conversation.last_message_text = reply_text[:100] + ("..." if len(reply_text) > 100 else "")
            conversation.last_message_time = iso_time
            db.commit()

    def send_email(self, to_email, subject, body):
        if not self.email_address or not self.app_password or self.email_address == "your_email@gmail.com":
            print(f"Email Integration: Cannot send email to {to_email}. Credentials not configured.")
            return False

        try:
            msg = EmailMessage()
            msg.set_content(body)
            msg["Subject"] = subject
            msg["From"] = self.email_address
            msg["To"] = to_email

            server = smtplib.SMTP_SSL(self.smtp_server, 465)
            server.login(self.email_address, self.app_password)
            server.send_message(msg)
            server.quit()
            print(f"Email Integration: Sent email to {to_email}")
            return True
        except Exception as e:
            print(f"Email Integration Error (SMTP): {e}")
            return False

email_service = EmailIntegrationService()
