import asyncio
import json
import logging
from aiokafka import AIOKafkaConsumer
from email_utils import send_email

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        data = json.loads(message.value.decode('utf-8'))
        account_address = data.get('account_address', None)
        activity_details = data.get('details', None)

        logger.info(f"Received activity for account: {account_address}")

        # Check if the account address is registered
        for user_email, user in self.user_db.items():
            if account_address in [addr['address'] for addr in user]:
                # Send email notification
                send_email(user_email, account_address, activity_details)
                logger.info(f"Email sent to {user_email} for account {account_address}")


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
    kafka_topic = 'ledger.updates'
    kafka_bootstrap_servers = 'localhost:9092'  # Adjust if your Kafka server is different
    logger.info(f"Connecting to Kafka at {kafka_bootstrap_servers} on topic '{kafka_topic}'...")
    consumer = AccountActivityConsumer(user_db, kafka_topic, kafka_bootstrap_servers)
    await consumer.consume()
