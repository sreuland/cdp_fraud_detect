import json
import os

SECRET_FILENAME = os.getenv("SECRET_FILE", "client_secret.json")
with open(SECRET_FILENAME) as f:
    config = json.load(f)

GOOGLE_CLIENT_ID = config["web"]["client_id"]
GOOGLE_CLIENT_SECRET = config["web"]["client_secret"]
GOOGLE_REDIRECT_URI = config["web"]["redirect_uris"][0]
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

GOOGLE_REVOKE_TOKEN_URL = "https://oauth2.googleapis.com/revoke"

# SMTP_USER = config["smtp"]["SMTP_USER"]
# SMTP_PASSWORD = config["smtp"]["SMTP_PASSWORD"]
# SMTP_SERVER = config["smtp"]["SMTP_SERVER"]
# SMTP_PORT = config["smtp"]["SMTP_PORT"]
#
# SENDER_NAME = "CDP Fraud Activity"
# SENDER_EMAIL = "cdp_fraud_activity@cdpfraud.org"


