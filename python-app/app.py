import asyncio
import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Optional

from aiokafka import AIOKafkaProducer
from fastapi import FastAPI, Depends, Form, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from kafka_consumer import start_kafka_consumer
from models import User
from oauth import router as oauth_router
from oauth_utils import get_current_user

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    logger.info("Starting Kafka producer during application startup...")
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS  # Adjust if your Kafka server is different
    )
    await producer.start()
    app.state.producer = producer
    """

    logger.info("Starting Kafka consumer during application startup...")
    consumer_task = asyncio.create_task(start_kafka_consumer(user_db, accounts_to_users, starred_users))

    try:
        yield
    finally:
        # logger.info("Shutting down Kafka producer...")
        # await producer.stop()  # Ensure the producer is stopped properly
        # logger.info("Kafka producer has been shut down.")

        logger.info("Shutting down Kafka consumer...")
        consumer_task.cancel()  # Cancel the consumer task
        await consumer_task  # Await the cancellation
        logger.info("Kafka consumer has been shut down.")

# App startup
templates = Jinja2Templates(directory="templates")

app = FastAPI(
   lifespan=lifespan
)

# Mount static files for serving images and other static content
app.mount("/static", StaticFiles(directory="templates/images"), name="static")

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
starred_users: set[User] = set()

@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/dashboard", response_class=templates.TemplateResponse)
async def dashboard(request: Request, current_user: dict = Depends(get_current_user)):
    name, email = current_user.get("name", ""), current_user.get("email", "")

    if email not in user_db:
        user_db[email] = User(name, email)

    user: Optional[User] = user_db.get(email)

    logger.info(f"--------  User = {user}")
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": current_user,
        "account_addresses": user.accounts if user else [],
        "register_for_all": user.register_for_all if user else False  # Pass the flag
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

@app.post("/delete_account", response_class=RedirectResponse)
async def delete_account(account_address: str = Form(...), current_user: dict = Depends(get_current_user)):
    name, email = current_user.get("name", ""), current_user.get("email", "")
    if email not in user_db:
        user_db[email] = User(name, email)

    user = user_db.get(email)
    if account_address in user.accounts:
        user.accounts.remove(account_address)  # Remove the account from the user's list
    accounts_to_users[account_address].discard(user)  # Remove user from the account's interested users
    if not accounts_to_users[account_address]:  # If no users are interested anymore, remove the account
        del accounts_to_users[account_address]
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/set_register_for_all")
async def set_register_for_all(request: Request, current_user: dict = Depends(get_current_user)):
    if request.method == "POST":
        # Check if the request is an AJAX request
        data = await request.json()  # Read JSON data
        register_for_all: bool = data.get("register_for_all", False)  # Extract value
        logger.info(f"------------ data is {data}")

        logger.info(f"-------- register_for_all === {register_for_all}")
        user: Optional[User] = user_db.get(current_user["email"])
        user.register_for_all = register_for_all
        if user.register_for_all:
            # remove accounts_to_users mapping
            for account in user.accounts:
                accounts_to_users[account].discard(user)

            user.accounts = []  # Clear accounts if "Register for all" is enabled
            starred_users.add(user)
        else:
            starred_users.discard(user)

        # Return JSON response
        return JSONResponse(content={"status": "success", "register_for_all": user.register_for_all})

    return JSONResponse(content={"status": "error", "message": "Invalid request."}, status_code=400)

@app.get("/activity", response_class=templates.TemplateResponse)
async def activity(request: Request, current_user: dict = Depends(get_current_user)):
    """
    # Simulating some JSON data for the activity
    user = User(name="AAA", email="xx@gmail.com")
    for _ in range(10):
        event = FraudEventOut(
            account_id=f"user{randint(100, 999)}",
            tx_hash=f"hash_{randint(1000, 9999)}_{choice(['A', 'B', 'C', 'D'])}",
            timestamp=randint(1634567800, 1634567900),  # Random timestamps
            event_type=choice(["fraud_event", "suspicious_activity"]),
            tx_url="https://google.com"
        )
        user.timeline.add_event(event)
    """
    name, email = current_user.get("name", ""), current_user.get("email", "")
    user = user_db.get(email)

    activities = [event.model_dump() for event in user.timeline.get_timeline()]
    # Sort activities by timestamp if necessary
    activities.sort(key=lambda x: x['timestamp'])  # Ensure events are in chronological order
    return templates.TemplateResponse("activity.html", {"request": request, "activities": activities})

async def get_producer() -> AIOKafkaProducer:
    return app.state.producer

"""
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
"""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000)
