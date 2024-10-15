package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"os"
	"os/signal"

	"github.com/pelletier/go-toml"
	"github.com/pkg/errors"
	"github.com/stellar/go/historyarchive"
	"github.com/stellar/go/ingest"
	"github.com/stellar/go/ingest/cdp"
	"github.com/stellar/go/ingest/ledgerbackend"
	"github.com/stellar/go/network"
	"github.com/stellar/go/support/datastore"
	"github.com/stellar/go/support/storage"
	"github.com/stellar/go/xdr"
)

// Services
type FraudDetector struct {
	dbUrl string
}
type FraudDetection struct {
	AccountId string
	FraudType string
}
type FraudDetectionService interface {
	GetFraudulentAccounts() (map[string]FraudDetection, error)
}

func (service FraudDetector) GetFraudulentAccounts() (map[string]FraudDetection, error) {
	//TODO
	return make(map[string]FraudDetection), nil
}

func NewFraudDetectionService() FraudDetectionService {
	//TODO
	return &FraudDetector{}
}

type RegistrationActor struct {
	dbUrl string
}

type RegistrationService interface {
	GetRegistrationsForAccount(accountId string) ([]string, error)
}

func (service RegistrationActor) GetRegistrationsForAccount(accountId string) ([]string, error) {
	//TODO
	return []string{}, nil
}

func NewRegistrationService() RegistrationService {
	//TODO
	return &RegistrationActor{}
}

// Application models
type FraudEvent struct {
  AppUserId string
	AccountId string
	TxHash        string
	Timestamp     uint
	Type          string
}

// application data pipeline
type Message struct {
	Payload interface{}
}

type Processor interface {
	Process(context.Context, Message) error
}

type Publisher interface {
	Subscribe(receiver Processor)
}

// Ingestion Pipeline Processors
type KafkaOutboundAdapter struct {
	Publisher interface{}
}

func (adapter *KafkaOutboundAdapter) Process(ctx context.Context, msg Message) error {
	// TODO - publish FraudEvent json to kafka here
	return nil
}

type FraudDetectionTransformer struct {
	processors            []Processor
	fraudDetectionService FraudDetectionService
  registrationService   RegistrationService
	networkPassPhrase     string
}

func (transformer *FraudDetectionTransformer) Subscribe(receiver Processor) {
	transformer.processors = append(transformer.processors, receiver)
}

func (transformer *FraudDetectionTransformer) Process(ctx context.Context, msg Message) error {
	ledgerCloseMeta := msg.Payload.(xdr.LedgerCloseMeta)
	ledgerTxReader, err := ingest.NewLedgerTransactionReaderFromLedgerCloseMeta(transformer.networkPassPhrase, ledgerCloseMeta)
	if err != nil {
		return errors.Wrapf(err, "failed to create reader for ledger %v", ledgerCloseMeta.LedgerSequence())
	}

	closeTime := uint(ledgerCloseMeta.LedgerHeaderHistoryEntry().Header.ScpValue.CloseTime)

	// scan all transactions in a ledger for fraud accounts
	fraudulentAccounts, err := transformer.fraudDetectionService.GetFraudulentAccounts()
	if err != nil {
		return errors.Wrapf(err, "failed to get fraud list for ledger %v", ledgerCloseMeta.LedgerSequence())
	}
	transaction, err := ledgerTxReader.Read()
	for ; err == nil; transaction, err = ledgerTxReader.Read() {
		accountId := transaction.Envelope.SourceAccount().ToAccountId().Address()
		if fraudDetected, ok := fraudulentAccounts[accountId]; ok {
      registeredAppWatchers, err := transformer.registrationService.GetRegistrationsForAccount(accountId)
      if err != nil {
        return err
      }
      for _, registeredAppUserId := range registeredAppWatchers { 
        fraudEvent := FraudEvent{
          AppUserId: registeredAppUserId,
          AccountId: accountId,
          TxHash:        transaction.Result.TransactionHash.HexString(),
          Timestamp:     closeTime,
          Type:          fraudDetected.FraudType,
        }
        jsonBytes, err := json.Marshal(fraudEvent)
        if err != nil {
          return err
        }

        for _, processor := range transformer.processors {
          processor.Process(ctx, Message{Payload: jsonBytes})
        }
      }
		}
	}

	if err != io.EOF {
		return errors.Wrapf(err, "failed to read transaction from ledger %v", ledgerCloseMeta.LedgerSequence())
	}
	return nil
}

type LedgerMetadataInboundAdapter struct {
	processors         []Processor
	historyArchiveURLs []string
	dataStoreConfig    datastore.DataStoreConfig
}

func (adapter *LedgerMetadataInboundAdapter) Subscribe(receiver Processor) {
	adapter.processors = append(adapter.processors, receiver)
}

func (adapter *LedgerMetadataInboundAdapter) Run(ctx context.Context) error {

	/////////////////////////////////////////////////////////////////
	// TODO - make this easier for callers, move latest ledger fetch into cdp.ApplyLedgerMetadata()
	// so caller doesn't have to this to start streaming from latest use case
	// i.e. allow unbounded range with from=0 which can signal the same.
	historyArchive, err := historyarchive.NewArchivePool(adapter.historyArchiveURLs, historyarchive.ArchiveOptions{
		ConnectOptions: storage.ConnectOptions{
			UserAgent: "payment_demo",
			Context:   ctx,
		},
	})
	if err != nil {
		return errors.Wrap(err, "error creating history archive client")
	}
	// Acquire the most recent ledger on network to begin streaming from
	latestNetworkLedger, err := historyArchive.GetLatestLedgerSequence()
	/////////////////////////////////////////////////////////////////////

	if err != nil {
		return errors.Wrap(err, "error getting latest ledger")
	}

	ledgerRange := ledgerbackend.UnboundedRange(latestNetworkLedger)

	pubConfig := cdp.PublisherConfig{
		DataStoreConfig:       adapter.dataStoreConfig,
		BufferedStorageConfig: cdp.DefaultBufferedStorageBackendConfig(adapter.dataStoreConfig.Schema.LedgersPerFile),
	}

	fmt.Printf("beginning fraud detection stream, starting at ledger %v ...\n", latestNetworkLedger)
	return cdp.ApplyLedgerMetadata(ledgerRange, pubConfig, ctx,
		func(lcm xdr.LedgerCloseMeta) error {
			for _, processor := range adapter.processors {
				if err = processor.Process(ctx, Message{Payload: lcm}); err != nil {
					return err
				}
			}
			return nil
		})
}

func main() {
	// run a data pipeline that transforms Pubnet ledger metadata into fraud events
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, os.Kill)
	defer stop()

	cfg, err := toml.LoadFile("config.toml")
	if err != nil {
		fmt.Printf("config.toml shoule be accessible in current directdory: %v\n", err)
		return
	}

	datastoreConfig := datastore.DataStoreConfig{}
	// Unmarshal TOML data into the Config struct
	if err = cfg.Unmarshal(&datastoreConfig); err != nil {
		fmt.Printf("error unmarshalling TOML config: %v\n", err)
		return
	}

	// create the inbound source of pubnet ledger metadata
	ledgerMetadataInboundAdapter := &LedgerMetadataInboundAdapter{
		historyArchiveURLs: network.PublicNetworkhistoryArchiveURLs,
		dataStoreConfig:    datastoreConfig,
	}

	// create the transformer to convert network data to fraud detections
	fraudDetectionTransformer := &FraudDetectionTransformer{
		networkPassPhrase:     network.PublicNetworkPassphrase,
		fraudDetectionService: NewFraudDetectionService(),
    registrationService:   NewRegistrationService(),
	}

	// create the outbound adapter, this is the end point of the pipeline
	// publishes application data model as messages to a broker
	outboundAdapter := &KafkaOutboundAdapter{}

	// wire up the ingestion pipeline and let it run
	fraudDetectionTransformer.Subscribe(outboundAdapter)
	ledgerMetadataInboundAdapter.Subscribe(fraudDetectionTransformer)
	log.Printf("Fraud detection pipeline ended %v\n", ledgerMetadataInboundAdapter.Run(ctx))
}
