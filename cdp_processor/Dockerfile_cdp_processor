FROM golang:1.22-bookworm AS builder

WORKDIR /go/src/deceptiscan/cdp_processor

COPY go.mod ./
COPY go.sum ./

RUN go mod download

COPY . ./

ARG GOFLAGS
RUN go install deceptiscan/cdp_processor

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
# ca-certificates are required to make tls connections
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl wget gnupg apt-utils

COPY --from=builder /go/bin/cdp_processor /usr/bin/cdp_processor
RUN mkdir -p /lmdb
RUN mkdir -p /toml
RUN mkdir -p /.config
ADD config.toml /toml
# default env values, override with docker run --env
ENV LMDB_PATH=/lmdb
ENV KAFKA_TOPIC=ledger.events.fraud
ENV KAFKA_BOOTSTRAP_SERVER=kafka-service:9092
ENV CDP_TOML=/toml/config.toml

ENTRYPOINT ["/usr/bin/cdp_processor"]
