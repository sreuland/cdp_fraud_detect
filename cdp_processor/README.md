# CDP Processor

## config
Requires 3 env variables:
LMDB_PATH=full path to the folder containing the lmdb files
KAFKA_BOOTSTRAP_SERVER
KAFKA_TOPIC
Optional env variable:
CDP_TOML, if absent, looks for 'config.toml' in process working directory.

Make sure to have a valid GCS authentication context to access the GCS bucket in config.toml - https://cloud.google.com/docs/authentication/application-default-credentials#personal 

The processor is set for Testnet network, it has hardcode to testnet history argchives and passphrase and the config.toml in this project is pre-configured for testnet.

## running the docker image, with kafka broker bound to your localhost:9092, and you have [installed GCP credentials](https://github.com/stellar/go/blob/master/services/galexie/README.md#set-up-gcp-credentials)
```
docker run -it --rm \
   --env GOOGLE_APPLICATION_CREDENTIALS=/.config/gcp/credentials.json \
   --env KAFKA_BOOTSTRAP_SERVER=host.docker.internal:9092 \
   -v "$HOME/.config/gcloud/application_default_credentials.json":/.config/gcp/credentials.json:ro \
   -v "/Users/sreuland/dev/cdp_fraud_detect/cdp_processor/lmdb/fraud_accts_data:/lmdb" \
   deceptiscan/cdp_processor
```
