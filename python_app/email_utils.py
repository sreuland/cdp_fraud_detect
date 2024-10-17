import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os


# Function to send email
def send_email(to_email, account_address, activity_details):
    smtp_server = os.getenv("SMTP_SERVER", "sandbox.smtp.mailtrap.io")
    smtp_port = int(os.getenv("SMTP_PORT"), 25)
    email_user = os.getenv("EMAIL_USER", "b51e7d9d82c3fe")
    email_pass = os.getenv("EMAIL_PASS", "78f8cb0a7cfc22")

    # Create the email content
    subject = f"Activity Detected on Account: {account_address}"
    body = f"Details of the activity:\n{activity_details}"

    msg = MIMEMultipart()
    msg['From'] = email_user
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(email_user, email_pass)
            server.sendmail(email_user, to_email, msg.as_string())
        print(f"Email sent to {to_email} successfully.")
    except Exception as e:
        print(f"Failed to send email to {to_email}. Error: {e}")
