import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import SMTP_SERVER, SMTP_PORT
from utils.logger import get_logger
import os

logger = get_logger(__name__)


def send_email(receiver, subject, body):
    """Send email via SMTP."""
    try:
        sender_email = os.getenv("SENDER_EMAIL")
        sender_password = os.getenv("SENDER_PASSWORD")
        
        if not sender_email or not sender_password:
            raise ValueError("Email credentials not found in environment variables")
        
        logger.info(f"Sending email to: {receiver}")
        
        # Create message
        message = MIMEMultipart()
        message["From"] = sender_email
        message["To"] = receiver
        message["Subject"] = subject
        message.attach(MIMEText(body, "plain"))
        
        # Send email
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(message)
        
        logger.info(f"Email sent successfully to: {receiver}")
        return {"status": "success", "receiver": receiver}
    
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        raise
