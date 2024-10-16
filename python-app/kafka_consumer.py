import asyncio
import json
import logging

from aiokafka import AIOKafkaConsumer
from pydantic import  ValidationError
from models import FraudEvent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from kafka_config import KAFKA_FRAUD_TOPIC, KAFKA_BOOTSTRAP_SERVERS

# Kafka consumer class using aiokafka
class AccountActivityConsumer:
    def __init__(self, user_db, kafka_topic, kafka_bootstrap_servers):
        self.user_db = user_db
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
            logger.info(f"******* received raw dict on kafak - {json_data}")

            # Normalize keys to snake_case if needed
            normalized_data = {
                "account_id": json_data.get("account_id") or json_data.get("AccountId"),
                "tx_hash": json_data.get("tx_hash") or json_data.get("TxHash"),
                "timestamp": json_data.get("timestamp") or json_data.get("Timestamp"),
                "event_type": json_data.get("event_type") or json_data.get("Type")
            }
            message = FraudEvent.model_validate(normalized_data)

            logger.info(f"Received activity for account: {message.account_id}")

            # Check if the account address is registered
            for user_email, user in self.user_db.items():
                if message.account_id in [addr['address'] for addr in user]:
                   pass
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
async def start_kafka_consumer(user_db):
    logger.info(f"Connecting to Kafka at {KAFKA_BOOTSTRAP_SERVERS} on topic '{KAFKA_FRAUD_TOPIC}'...")
    consumer = AccountActivityConsumer(user_db, KAFKA_FRAUD_TOPIC, KAFKA_BOOTSTRAP_SERVERS)
    await consumer.consume()
