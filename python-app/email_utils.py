import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config.config import SENDER_EMAIL, SMTP_USER, SMTP_PASSWORD, SMTP_SERVER, SMTP_PORT, SENDER_NAME
from models import Email

logger = logging.getLogger(__name__)


def email_content(recipient: Email) -> MIMEMultipart:
    sender = f"{SENDER_NAME} <{SENDER_EMAIL}>"
    receiver = f"{recipient.name} <{recipient.email}>"

    # Create the MIMEMultipart message
    message = MIMEMultipart()
    message['From'] = sender
    message['To'] = receiver
    message['Subject'] = "Fraud Activity Alert"

    # Plain text message
    body = f"""\
    Hi {recipient.name},

    We have detected fraudulent activity on account address: {recipient.account_address}.
    Please visit this URL for more details: {recipient.tx_url}.
    """

    # Attach the message body
    message.attach(MIMEText(body, 'plain'))

    return message


def send_email(recipient: Email):
    message = email_content(recipient)

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()  # Secure the connection
            server.login(SMTP_USER, SMTP_PASSWORD)
            # Convert the message to string and send it
            server.sendmail(SENDER_EMAIL, recipient.email, message.as_string())

        logger.info(f"Email sent to {recipient.email} successfully.")
    except Exception as e:
        logger.error(f"Failed to send email to {recipient.email}. Error: {e}")




