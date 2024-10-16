import asyncio
import json
from collections import defaultdict
from contextlib import asynccontextmanager

from aiokafka import AIOKafkaProducer
from fastapi import FastAPI, Depends, Form, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates

from kafka_config import KAFKA_BOOTSTRAP_SERVERS, KAFKA_FRAUD_TOPIC
from kafka_consumer import start_kafka_consumer
from models import User, FraudEvent
from oauth import router as oauth_router
from fastapi.responses import RedirectResponse
import logging

from oauth_utils import get_current_user


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Kafka consumer during application startup...")
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS  # Adjust if your Kafka server is different
    )
    await producer.start()
    app.state.producer = producer

    logger.info("Starting Kafka producer during application startup...")
    consumer_task = asyncio.create_task(start_kafka_consumer(user_db))

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

# App startup
templates = Jinja2Templates(directory="templates")


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


# User database simulation
user_db: dict[str, User] = {}
accounts_to_users: dict[str, set[User]] = defaultdict(set)


@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/dashboard", response_class=templates.TemplateResponse)
async def dashboard(request: Request, current_user: dict = Depends(get_current_user)):
    user = user_db.get(current_user["email"], None)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": current_user,
        "account_addresses": user.accounts if user else []
    })


@app.get("/accounts", response_class=templates.TemplateResponse)
async def accounts(request: Request, current_user: dict = Depends(get_current_user)):
    user = user_db.get(current_user["email"], None)
    return templates.TemplateResponse("accounts.html", {
        "request": request,
        "user": current_user,
        "account_addresses": user.accounts if user else []
    })


@app.post("/add_account", response_class=RedirectResponse)
async def add_account(account_address: str = Form(...), current_user: dict = Depends(get_current_user)):
    name, email = current_user.get("name", ""), current_user.get("email", "")

    if email not in user_db:
        user_db[email] = User(name, email)

    user = user_db[email]
    # Reverse mapping from account_address to list of interested users
    user.accounts.append(account_address)
    accounts_to_users[account_address].add(user)

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





async def get_producer() -> AIOKafkaProducer:
    return app.state.producer

@app.post("/push_message")
async def push_message(message: dict, producer: AIOKafkaProducer = Depends(get_producer)):
    try:
        ss = json.dumps(message)
        await producer.send_and_wait(KAFKA_FRAUD_TOPIC, value=ss.encode("utf-8"))
        logger.info(f"Message sent to Kafka topic 'ledger.updates': {message}")
        return {"status": "success", "message": "Message sent to Kafka."}
    except Exception as e:
        logger.error(f"Failed to send message to Kafka: {e}")
        return {"status": "error", "message": "Failed to send message."}



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000)



