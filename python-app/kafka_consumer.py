import asyncio
import json
import logging
import os

from aiokafka import AIOKafkaConsumer
from pydantic import  ValidationError

from email_utils import send_email
from models import User, FraudEventOut, Email

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from kafka_config import KAFKA_FRAUD_TOPIC, KAFKA_BOOTSTRAP_SERVERS, HORIZON_TX_URL


# Kafka consumer class using aiokafka
class AccountActivityConsumer:
    def __init__(self, kafka_topic: str, kafka_bootstrap_servers: str, user_db: dict[str, User], accounts_to_users: dict[str, set[User]], starred_users: set[User]):
        self.user_db = user_db
        self.accounts_to_users = accounts_to_users
        self.starred_users = starred_users
        self.kafka_topic = kafka_topic
        self.consumer = AIOKafkaConsumer(
            self.kafka_topic,
            bootstrap_servers=kafka_bootstrap_servers,
            auto_offset_reset='earliest',
            enable_auto_commit=True,
            group_id='account_activity_group',
        )

    async def process_message(self, message):
        try:
            json_data = json.loads(message.value.decode('utf-8'))

            logger.info(f"******* received raw dict on kafka - {json_data}")

            # Normalize keys to snake_case if needed
            account_id=json_data.get("account_id") or json_data.get("AccountId")
            tx_hash=json_data.get("tx_hash") or json_data.get("TxHash")
            timestamp=json_data.get("timestamp") or json_data.get("Timestamp")
            types=json_data.get("event_types") or json_data.get("Types")
            tx_url = f"{HORIZON_TX_URL}/{tx_hash}"
            message = FraudEventOut(
                account_id=account_id,
                tx_hash=tx_hash,
                timestamp=timestamp,
                types=types,
                transaction_url=tx_url
            )

            logger.info(f"Received activity for account: {message.account_id}")

            account_id = message.account_id
            for user in self.accounts_to_users[account_id]:
                email = Email(user.name, user.email, account_id, tx_url)
                user.timeline.add_event(message)
                # send_email(email)


            for user in self.starred_users:
                email = Email(user.name, user.email, account_id, tx_url)
                user.timeline.add_event(message)
                # send_email(email)

        except json.JSONDecodeError as je:
            logger.error(f"Error decoding message: {je}")
        except ValidationError as ve:
            logger.error(f"Failed to validate json data to pydantic model: {ve}")

        except Exception as e:
            logger.error(f"Error processing message: {e}")


    async def consume(self):
        logger.info("Starting Kafka consumer...")
        await self.consumer.start()
        logger.info("Kafka consumer started, waiting for messages...")
        try:
            async for message in self.consumer:
                await self.process_message(message)
        except asyncio.CancelledError:
            logger.info("Kafka consumer task was cancelled.")
        finally:
            logger.info("Stopping Kafka consumer...")
            await self.consumer.stop()


# Function to start the Kafka consumer
async def start_kafka_consumer(user_db, accounts_to_users, starred_users):
    logger.info(f"Connecting to Kafka at {KAFKA_BOOTSTRAP_SERVERS} on topic '{KAFKA_FRAUD_TOPIC}'...")
    consumer = AccountActivityConsumer(KAFKA_FRAUD_TOPIC, KAFKA_BOOTSTRAP_SERVERS, user_db, accounts_to_users, starred_users)
    await consumer.consume()


