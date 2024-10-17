import logging
import json
from aiokafka import AIOKafkaProducer

from python_app.kafka_config import KAFKA_FRAUD_TOPIC, KAFKA_BOOTSTRAP_SERVERS

logger = logging.getLogger(__name__)

class KafkaProducerWrapper:
    def __init__(self, kafka_bootstrap_servers: str):
        self.producer = AIOKafkaProducer(
            bootstrap_servers=kafka_bootstrap_servers,
        )

    async def start(self):
        logger.info("Starting Kafka producer...")
        await self.producer.start()

    async def stop(self):
        logger.info("Stopping Kafka producer...")
        await self.producer.stop()

    async def send_message(self, topic: str, message: dict):
        logger.info(f"Sending message to Kafka topic '{topic}': {message}")
        await self.producer.send_and_wait(
            topic,
            json.dumps(message).encode("utf-8")
        )

# Helper to create a producer instance and expose methods
kafka_producer: KafkaProducerWrapper = None

async def init_kafka_producer():
    global kafka_producer
    logger.info("Starting Kafka producer during application startup...")
    kafka_producer = KafkaProducerWrapper(KAFKA_BOOTSTRAP_SERVERS)
    await kafka_producer.start()

async def shutdown_kafka_producer():
    logger.info("Shutting down Kafka producer...")
    if kafka_producer:
        await kafka_producer.stop()

async def send_kafka_message(message: dict):
    if kafka_producer:
        await kafka_producer.send_message(KAFKA_FRAUD_TOPIC, message)
