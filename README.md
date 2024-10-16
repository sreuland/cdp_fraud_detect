# cdp_fraud_detect
cdp hackathon



## How to setup

### Run kafka docker

1. run the `kafka-docker-compose.yml` file to start kafka (from confluent). Do not forget the `-d` option.
 This `yml` file starts a container named `kafka-service`
```commandline
cd cdp_fraud_detect
docker-compose -f kafka-docker-compose.yml up -d

### To bring the kafka container down
docker-compose -f kafka-docker-compose.yml down
```

2. Create the relevant topics - `ledger.events.fraud`
```commandline
### Create a topic
docker exec -it kafka-service  kafka-topics --create --topic ledger.events.fraud --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1 

### Verify the topic has been created
docker exec -it kafka-service  kafka-topics --list --bootstrap-server localhost:9092
```


### Run python-app



### Run Golang CDP processor
refer to [cdp_processor/README.md](cdp_processor/README.md)


### Run API Exporter