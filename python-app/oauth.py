import logging
from fastapi import APIRouter, Cookie, status
from fastapi.responses import RedirectResponse
from oauth_utils import get_google_user_info, GOOGLE_CLIENT_ID, GOOGLE_REDIRECT_URI, revoke_google_token

logger = logging.getLogger(__name__)
router = APIRouter()

authorization_url = (
    f"https://accounts.google.com/o/oauth2/auth?"
    f"client_id={GOOGLE_CLIENT_ID}&"
    f"redirect_uri={GOOGLE_REDIRECT_URI}&"
    f"response_type=code&"
    f"scope=openid email profile"
)


@router.get("/login")
async def login(access_token: str = Cookie(None)):
    if access_token:
        return RedirectResponse(url="/dashboard")
    return RedirectResponse(url=authorization_url)

@router.get("/callback")
async def callback(code: str):
    user_info, access_token = await get_google_user_info(code)
    logger.info(f"User info retrieved: {user_info}")

    # Redirect to dashboard with cookie set
    response = RedirectResponse(url="/dashboard")
    response.set_cookie(key="access_token", value=access_token, httponly=True)
    return response


@router.post("/logout")
async def logout(response: RedirectResponse, access_token: str = Cookie(None)):
    if access_token:
        # (Optional) Add revoke_google_token function to invalidate token
        await revoke_google_token(access_token)
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="access_token")
    return response
