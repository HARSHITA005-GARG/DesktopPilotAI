import base64
import os
import re
from email.message import EmailMessage

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import (
    GMAIL_CREDENTIALS_FILE,
    SMTP_SENDER,
    GMAIL_TOKEN_FILE,
)
from utils.logger import get_logger

logger = get_logger(__name__)
GMAIL_SEND_SCOPE = ["https://www.googleapis.com/auth/gmail.send"]
EMAIL_ADDRESS_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _require_email_config():
    if not SMTP_SENDER:
        raise RuntimeError(
            "Email sending is not configured yet. Set AURA_SMTP_SENDER in the environment."
        )
    if not os.path.exists(GMAIL_CREDENTIALS_FILE):
        raise RuntimeError(
            f"Gmail OAuth is not configured yet. Put your Google OAuth desktop client file at {GMAIL_CREDENTIALS_FILE}."
        )


def _get_gmail_credentials():
    creds = None

    if os.path.exists(GMAIL_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(GMAIL_TOKEN_FILE, GMAIL_SEND_SCOPE)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                GMAIL_CREDENTIALS_FILE,
                GMAIL_SEND_SCOPE,
            )
            creds = flow.run_local_server(port=0)

        os.makedirs(os.path.dirname(GMAIL_TOKEN_FILE), exist_ok=True)
        with open(GMAIL_TOKEN_FILE, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())

    return creds


def _build_raw_message(recipient, email_subject, email_body):
    message = EmailMessage()
    message["From"] = SMTP_SENDER
    message["To"] = recipient
    message["Subject"] = email_subject
    message.set_content(email_body)
    return {"raw": base64.urlsafe_b64encode(message.as_bytes()).decode()}


def send_email(receiver, subject, body):
    """Send an email using Gmail OAuth."""
    _require_email_config()

    recipient = (receiver or "").strip()
    email_subject = (subject or "").strip()
    email_body = (body or "").strip()

    if not recipient:
        raise ValueError("Missing email recipient.")
    if not EMAIL_ADDRESS_PATTERN.match(recipient):
        raise ValueError("Email recipient must be a valid email address.")
    if not email_subject:
        raise ValueError("Missing email subject.")
    if not email_body:
        raise ValueError("Missing email body.")

    logger.info("Sending email to %s with subject %s", recipient, email_subject)
    creds = _get_gmail_credentials()
    service = build("gmail", "v1", credentials=creds)
    service.users().messages().send(
        userId="me",
        body=_build_raw_message(recipient, email_subject, email_body),
    ).execute()

    return {
        "status": "success",
        "message": f"I sent the email to {recipient}.",
        "receiver": recipient,
        "subject": email_subject,
    }
