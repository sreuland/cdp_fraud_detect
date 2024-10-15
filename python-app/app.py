import asyncio
from contextlib import asynccontextmanager

from aiokafka import AIOKafkaProducer
from fastapi import FastAPI, Depends, Form, Request, status, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2AuthorizationCodeBearer
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from kafka_consumer import start_kafka_consumer
from oauth import router as oauth_router
from fastapi.responses import RedirectResponse
from httpx import AsyncClient
import json
import logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Kafka consumer during application startup...")
    producer = AIOKafkaProducer(
        bootstrap_servers='localhost:9092'  # Adjust if your Kafka server is different
    )
    await producer.start()
    app.state.producer = producer

    logger.info("Starting Kafka producer during application startup...")
    consumer_task = asyncio.create_task(start_kafka_consumer(user_db))

    # Consumer stuff
    try:
        yield
    finally:
        logger.info("Shutting down Kafka producer...")
        await producer.stop()  # Ensure the producer is stopped properly
        logger.info("Kafka producer has been shut down.")

        logger.info("Shutting down Kafka consumer...")
        consumer_task.cancel()  # Cancel the consumer task
        await consumer_task  # Await the cancellation
        logger.info("Kafka consumer has been shut down.")

templates = Jinja2Templates(directory="templates")


# Load Google OAuth configuration
with open("client_secret.json") as f:
    oauth_config = json.load(f)

GOOGLE_CLIENT_ID = oauth_config["web"]["client_id"]
GOOGLE_CLIENT_SECRET = oauth_config["web"]["client_secret"]
GOOGLE_REDIRECT_URI = oauth_config["web"]["redirect_uris"][0]
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
#GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

# Create OAuth2AuthorizationCodeBearer object
oauth2_scheme = OAuth2AuthorizationCodeBearer(
    authorizationUrl=f"https://accounts.google.com/o/oauth2/auth?client_id={GOOGLE_CLIENT_ID}&redirect_uri={GOOGLE_REDIRECT_URI}&response_type=code&scope=openid email profile",
    tokenUrl=GOOGLE_TOKEN_URL
)

# User database simulation
user_db = {}




from fastapi import Cookie
# Dependency to get the curren
async def get_current_user(access_token: str = Cookie(None)):
    if access_token is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    async with AsyncClient() as client:
        logger.warning(f"*********** Getting info from {GOOGLE_USERINFO_URL}")
        response = await client.get(GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
        response.raise_for_status()
        return response.json()


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

app = FastAPI(
   lifespan=lifespan
)
# Include OAuth routes
app.include_router(oauth_router)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this for your production settings
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/dashboard", response_class=templates.TemplateResponse)
async def dashboard(request: Request, current_user: dict = Depends(get_current_user)):
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": current_user, "account_addresses": user_db.get(current_user["email"], [])})

@app.get("/accounts", response_class=templates.TemplateResponse)
async def accounts(request: Request, current_user: dict = Depends(get_current_user)):
    return templates.TemplateResponse("accounts.html", {"request": request, "user": current_user, "account_addresses": user_db.get(current_user["email"], [])})

@app.post("/add_account", response_class=RedirectResponse)
async def add_account(account_address: str = Form(...), current_user: dict = Depends(get_current_user)):
    if current_user["email"] not in user_db:
        user_db[current_user["email"]] = []
    user_db[current_user["email"]].append({"address": account_address})
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/activity", response_class=templates.TemplateResponse)
async def activity(request: Request):
    # Simulating some JSON data for the activity
    activities = [
        {
            "hash1": {
                "id": 1,
                "name": "Activity 1",
                "details": {
                    "description": "Detail 1",
                    "timestamp": "2024-10-14",
                    "additional_info": {
                        "valid": True,
                        "related_activities": [
                            {"id": 3, "name": "Sub Activity 1", "sin": ["aa", "bb" ]},
                            {"id": 4, "name": "Sub Activity 2", "ss": {"aa": [1, 2,3]}},

                        ]
                    }
                }
            }
        },
        {
            "hash2": {
                "id": 2,
                "name": "Activity 2",
                "details": {
                    "description": "Detail 2",
                    "timestamp": "2024-10-15",
                    "starttime": "10:00 AM",
                    "endtime": "11:00 AM",
                    "additional_info": {
                        "valid": False,
                        "location": "Conference Room A"
                    }
                }
            }
        }
    ]

    return templates.TemplateResponse("activity.html", {"request": request, "activities": activities})



# Pydantic model for the message
class Message(BaseModel):
    account_address: str
    details: str


async def get_producer() -> AIOKafkaProducer:
    return app.state.producer

@app.post("/push_message")
async def push_message(message: Message, producer: AIOKafkaProducer = Depends(get_producer)):
    try:
        await producer.send_and_wait('ledger.updates', value=message.model_dump_json().encode('utf-8'))
        logger.info(f"Message sent to Kafka topic 'ledger.updates': {message}")
        return {"status": "success", "message": "Message sent to Kafka."}
    except Exception as e:
        logger.error(f"Failed to send message to Kafka: {e}")
        return {"status": "error", "message": "Failed to send message."}



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000)



