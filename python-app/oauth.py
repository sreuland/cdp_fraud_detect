import json
import logging
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2AuthorizationCodeBearer
from httpx import AsyncClient

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
router = APIRouter()

# Load Google OAuth configuration
with open("client_secret.json") as f:
    oauth_config = json.load(f)

GOOGLE_CLIENT_ID = oauth_config["web"]["client_id"]
GOOGLE_CLIENT_SECRET = oauth_config["web"]["client_secret"]
GOOGLE_REDIRECT_URI = oauth_config["web"]["redirect_uris"][0]
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
# GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

# Define the authorization URL
authorization_url = (
    f"https://accounts.google.com/o/oauth2/auth?"
    f"client_id={GOOGLE_CLIENT_ID}&"
    f"redirect_uri={GOOGLE_REDIRECT_URI}&"
    f"response_type=code&"
    f"scope=openid email profile"
)

oauth2_scheme = OAuth2AuthorizationCodeBearer(
    authorizationUrl=authorization_url,
    tokenUrl=GOOGLE_TOKEN_URL
)

@router.get("/login")
async def login():
    return RedirectResponse(url=authorization_url)

@router.get("/callback")
async def callback(request: Request, code: str):
    async with AsyncClient() as client:
        # Exchange the authorization code for access tokens
        token_response = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        })
        token_response.raise_for_status()
        tokens = token_response.json()

        # Get user information
        user_info_response = await client.get(GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {tokens['access_token']}"})
        user_info_response.raise_for_status()
        user_info = user_info_response.json()

        # Log user info
        logger.warning("User info retrieved: %s", user_info)

        # Store the access token as a cookie
        response = RedirectResponse(url="/dashboard")
        response.set_cookie(key="access_token", value=tokens["access_token"], httponly=True)

        return response
