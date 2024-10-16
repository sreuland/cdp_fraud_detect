# CDP Processor

## config
Requires 3 env variables:
LMDB_PATH=full path to the folder containing the lmdb files
KAFKA_BOOTSTRAP_SERVER
KAFKA_TOPIC

Make sure to have a valid GCS authentication context to access the GCS bucket in config.toml - https://cloud.google.com/docs/authentication/application-default-credentials#personal 


The processor is set for Testnet network, it has hardcode to testnet history argchives and passphrase
and the config.toml is pre-configured for testnet.
