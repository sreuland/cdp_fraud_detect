import os

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

HORIZON_TX_URL = os.getenv("HORIZON_TX_URL", "https://horizon-testnet.stellar.org/transactions")
KAFKA_FRAUD_TOPIC = os.getenv("KAFKA_FRAUD_TOPIC", "ledger.events.fraud")
KAFKA_CONSUMER_GROUP = os.getenv("KAFKA_CONSUMER_GROUP", "webapp-fraud-service")
