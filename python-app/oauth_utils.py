import json
import os

from httpx import AsyncClient
import logging
from fastapi import HTTPException, Cookie

logger = logging.getLogger(__name__)

SECRET_FILENAME = os.getenv("SECRET_FILE", "client_secret.json")

# Load Google OAuth configuration
with open(SECRET_FILENAME) as f:
    oauth_config = json.load(f)

GOOGLE_CLIENT_ID = oauth_config["web"]["client_id"]
GOOGLE_CLIENT_SECRET = oauth_config["web"]["client_secret"]
GOOGLE_REDIRECT_URI = oauth_config["web"]["redirect_uris"][0]
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

GOOGLE_REVOKE_TOKEN_URL = "https://oauth2.googleapis.com/revoke"

async def get_google_user_info(code: str):
    logger.info(f"Exchanging authorization code {code} for tokens.")
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

        logger.info("Successfully exchanged code for tokens.")

        # Retrieve user information
        user_info_response = await client.get(GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {tokens['access_token']}"})
        user_info_response.raise_for_status()
        return user_info_response.json(), tokens['access_token']


async def get_current_user(access_token: str = Cookie(None)):
    if access_token is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    async with AsyncClient() as client:
        # Retrieve user information with the access token
        user_info_response = await client.get(GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
        user_info_response.raise_for_status()
        user_data = user_info_response.json()
        logger.info(f"get_current_user returned : {user_data}")

        return user_data


async def revoke_google_token(access_token: str):
    async with AsyncClient() as client:
        try:
            # Revoke the token by making a POST request to Google's revoke token endpoint
            response = await client.post(GOOGLE_REVOKE_TOKEN_URL, params={"token": access_token})
            response.raise_for_status()
            logger.info("Successfully revoked Google access token.")
        except Exception as e:
            logger.error(f"Failed to revoke Google access token: {e}")