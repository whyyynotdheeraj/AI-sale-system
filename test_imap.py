import sys
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.abspath('.'))

from backend.database import engine, SessionLocal
from backend import models
from backend.auto_migrate import run_auto_migrations
import imaplib

def test():
    run_auto_migrations(engine)
    db = SessionLocal()
    try:
        settings_list = db.query(models.Settings).all()
        print(f"Total settings records: {len(settings_list)}")
        for s in settings_list:
            print(f"Company ID: {s.company_id}")
            print(f"Gmail Address: {s.gmail_address}")
            print(f"Gmail App Password Set: {'Yes' if s.gmail_app_password else 'No'}")
            if s.gmail_address and s.gmail_app_password:
                print("Attempting test IMAP connection...")
                try:
                    mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
                    mail.login(s.gmail_address.strip(), s.gmail_app_password.strip())
                    print("IMAP Login SUCCESSFUL!")
                    mail.select("INBOX")
                    status, messages = mail.search(None, "UNSEEN")
                    print(f"UNSEEN Search Status: {status}, Messages count: {len(messages[0].split()) if messages[0] else 0}")
                    status_all, messages_all = mail.search(None, "ALL")
                    print(f"ALL Search Status: {status_all}, Messages count: {len(messages_all[0].split()) if messages_all[0] else 0}")
                    mail.logout()
                except Exception as ex:
                    print(f"IMAP Connection/Login FAILED: {ex}")
    finally:
        db.close()

if __name__ == "__main__":
    test()
