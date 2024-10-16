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
1. Setup python environment. *Note* - The code has been tested against python version 3.9.0
```commandline
cd cdp_fraud_detect
python3 -m venv venv
source ./venv/bin/activate
pip3 install -r requirements.txt
```
2. This python web-app leverages Google Oauth, so you will need to create and register your Web-app as a oauth client. Please follow instructions [here](https://www.youtube.com/shorts/WABhO9KsOpU)

3. Within the `python-app` directory, setup a `client_secret.json` file. This file will have Oauth credentials - specifically, client_id, client_secret, the URI for redirection, once you are OAuthed by Google. You can find these credeentials from the Credential tab on your `https://console.cloud.google.com/apis/credentials` and can download a JSON file 
Sample `client_secret.json` file
```commandline
{
  "web": {
    "client_id": "xxx",
    "project_id": "xxx",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_secret": "xxx",
    "redirect_uris": [
      "http://localhost:8000/callback"   ---> This should match what you have configured on step 2, when creating your OAuth Client on Google
    ],
    "javascript_origins": [
      "http://localhost:8000"
    ]
  }
}
```

4. Start the service locally from within the `python-app` directory.
```commandline
cd cdp_fraud_detect/python-app
python3 app.py
```

5. Navigate to `localhost:8000` and follow login instructions



### Run Golang CDP processor


### Run API Exporter