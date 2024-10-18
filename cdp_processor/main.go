package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"io/fs"
	"log"
	"os"
	"os/signal"

	"github.com/pelletier/go-toml"
	"github.com/pkg/errors"
	"github.com/stellar/go/clients/horizonclient"
	"github.com/stellar/go/historyarchive"
	"github.com/stellar/go/ingest"
	"github.com/stellar/go/ingest/cdp"
	"github.com/stellar/go/ingest/ledgerbackend"
	"github.com/stellar/go/keypair"
	"github.com/stellar/go/network"
	"github.com/stellar/go/strkey"
	"github.com/stellar/go/support/datastore"
	"github.com/stellar/go/support/storage"
	"github.com/stellar/go/xdr"

	"github.com/bmatsuo/lmdb-go/lmdb"
	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
)

// Services
type FraudDetector struct {
	lmdbDBI lmdb.DBI
	lmdbEnv *lmdb.Env
}
type FraudDetection struct {
	FraudTypes []string
}
type FraudDetectionService interface {
	GetFraudulentAccount(accountId string) (*FraudDetection, error)
	Close()
}

type fraudulentLmdbValueModel struct {
	Tags    []string
	Address string
	Domain  string
	Name    string
}

func (service *FraudDetector) Close() {
	service.lmdbEnv.Close()
}

func (service *FraudDetector) GetFraudulentAccount(accountId string) (*FraudDetection, error) {
	var result *FraudDetection

	err := service.lmdbEnv.View(func(txn *lmdb.Txn) (err error) {
		var valueModel fraudulentLmdbValueModel
		value, err := txn.Get(service.lmdbDBI, []byte(accountId))
		if lmdb.IsNotFound(err) {
			return nil
		}
		if err != nil {
			return err
		}
		if err := json.Unmarshal(value, &valueModel); err != nil {
			return errors.Wrap(err, "unmarshaling json")
		}
		result = &FraudDetection{FraudTypes: valueModel.Tags}
		return nil
	})

	return result, err
}

func NewFraudDetectionService(lmdbPath string) (FraudDetectionService, error) {
	// create an environment and make sure it is eventually closed.
	env, err := lmdb.NewEnv()
	if err != nil {
		return nil, err
	}

	err = env.SetMapSize(1 << 30)
	if err != nil {
		env.Close()
		return nil, err
	}
	err = env.Open(lmdbPath, lmdb.NoLock|lmdb.Readonly, fs.FileMode(uint(0777)))
	if err != nil {
		env.Close()
		return nil, err
	}

	var dbi lmdb.DBI
	err = env.View(func(txn *lmdb.Txn) (err error) {
		dbi, err = txn.OpenRoot(0)
		return err
	})
	if err != nil {
		env.Close()
		return nil, err
	}

	return &FraudDetector{lmdbDBI: dbi, lmdbEnv: env}, nil
}

// Application models
type FraudEvent struct {
	AccountId string
	TxHash    string
	Timestamp uint
	Types     []string
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
	producer   *kafka.Producer
	fraudTopic string
}

func NewKafkaOutboundAdpater(kafkaBootstrapServer, kafkaTopic string) (*KafkaOutboundAdapter, error) {
	kafkaPub, err := kafka.NewProducer(&kafka.ConfigMap{"bootstrap.servers": kafkaBootstrapServer})
	if err != nil {
		return nil, err
	}

	// Delivery report handler for produced messages
	go func() {
		for e := range kafkaPub.Events() {
			switch ev := e.(type) {
			case *kafka.Message:
				if ev.TopicPartition.Error != nil {
					fmt.Printf("Delivery failed: %v\n", ev.TopicPartition)
				} else {
					fmt.Printf("Delivered message to %v\n", ev.TopicPartition)
				}
			}
		}
	}()

	return &KafkaOutboundAdapter{producer: kafkaPub, fraudTopic: kafkaTopic}, nil
}

func (adapter *KafkaOutboundAdapter) Process(ctx context.Context, msg Message) error {
	return adapter.producer.Produce(&kafka.Message{
		TopicPartition: kafka.TopicPartition{Topic: &adapter.fraudTopic, Partition: kafka.PartitionAny},
		Value:          msg.Payload.([]byte),
	}, nil)
}

func (adapter *KafkaOutboundAdapter) Close() {
	adapter.producer.Close()
}

type FraudDetectionTransformer struct {
	processors            []Processor
	fraudDetectionService FraudDetectionService
	networkPassPhrase     string
}

func (transformer *FraudDetectionTransformer) Subscribe(receiver Processor) {
	transformer.processors = append(transformer.processors, receiver)
}

func (transformer *FraudDetectionTransformer) Process(ctx context.Context, msg Message) error {
	ledgerCloseMeta := msg.Payload.(xdr.LedgerCloseMeta)
	fmt.Printf("inspecting ledger %v for fraud detection ...\n", ledgerCloseMeta.LedgerSequence())

	ledgerTxReader, err := ingest.NewLedgerTransactionReaderFromLedgerCloseMeta(transformer.networkPassPhrase, ledgerCloseMeta)
	if err != nil {
		return errors.Wrapf(err, "failed to create reader for ledger %v", ledgerCloseMeta.LedgerSequence())
	}

	closeTime := uint(ledgerCloseMeta.LedgerHeaderHistoryEntry().Header.ScpValue.CloseTime)

	transaction, err := ledgerTxReader.Read()
	for ; err == nil; transaction, err = ledgerTxReader.Read() {
		accountParticipants, err := getParticipants(transaction, ledgerCloseMeta.LedgerSequence())
		if err != nil {
			return err
		}

		for _, accountId := range accountParticipants {
			fraudDetection, err := transformer.fraudDetectionService.GetFraudulentAccount(accountId)
			if err != nil {
				return err
			}
			if fraudDetection == nil {
				// account not fraudulent!
				continue
			}

			fmt.Printf("Detected fraudulent account activity on tx hash: %v, for account: %v\n",
				transaction.Result.TransactionHash.HexString(), accountId)

			fraudEvent := FraudEvent{
				AccountId: accountId,
				TxHash:    transaction.Result.TransactionHash.HexString(),
				Timestamp: closeTime,
				Types:     fraudDetection.FraudTypes,
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
	historyArchive, err := historyarchive.NewArchivePool(adapter.historyArchiveURLs, historyarchive.ArchiveOptions{
		ConnectOptions: storage.ConnectOptions{
			UserAgent: "fraud_demo",
			Context:   ctx,
		},
	})
	if err != nil {
		return errors.Wrap(err, "error creating history archive client")
	}
	// Acquire the most recent ledger on network to begin streaming from
	latestNetworkLedger, err := historyArchive.GetLatestLedgerSequence()

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
	lmdbPath := os.Getenv("LMDB_PATH")
	kafkaBootstrapServer := os.Getenv("KAFKA_BOOTSTRAP_SERVER")
	kafkaTopic := os.Getenv("KAFKA_TOPIC")
	cdpToml := os.Getenv("CDP_TOML")
	if cdpToml == "" {
		cdpToml = "config.toml"
	}
	// run a data pipeline that transforms Pubnet ledger metadata into fraud events
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, os.Kill)
	defer stop()

	cfg, err := toml.LoadFile(cdpToml)
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
		historyArchiveURLs: network.TestNetworkhistoryArchiveURLs,
		dataStoreConfig:    datastoreConfig,
	}

	fraudDetectionService, err := NewFraudDetectionService(lmdbPath)
	if err != nil {
		fmt.Printf("error creating fraud detection service: %v\n", err)
		return
	}
	defer fraudDetectionService.Close()

	// create the transformer to convert network data to fraud detections
	fraudDetectionTransformer := &FraudDetectionTransformer{
		networkPassPhrase:     network.TestNetworkPassphrase,
		fraudDetectionService: fraudDetectionService,
	}

	// create the outbound adapter, this is the end point of the pipeline
	// publishes application data model as messages to a broker
	outboundAdapter, err := NewKafkaOutboundAdpater(kafkaBootstrapServer, kafkaTopic)
	if err != nil {
		fmt.Printf("error creating kafka producer: %v\n", err)
		return
	}
	defer outboundAdapter.Close()

	// wire up the ingestion pipeline and let it run
	fraudDetectionTransformer.Subscribe(outboundAdapter)
	ledgerMetadataInboundAdapter.Subscribe(fraudDetectionTransformer)

	// not needed ...
	//seedAccounts(lmdbPath)
	log.Printf("Fraud detection pipeline ended %v\n", ledgerMetadataInboundAdapter.Run(ctx))
}

func seedAccounts(lmdbPath string) {

	fraudAccounts := []fraudulentLmdbValueModel{}

	acc1Kp := keypair.MustRandom()
	horizonclient.DefaultTestNetClient.Fund(acc1Kp.Address())

	acc1 := fraudulentLmdbValueModel{
		Tags:    []string{"unsafe"},
		Address: acc1Kp.Address(),
		Domain:  "domain.com",
		Name:    "acc 1",
	}
	fraudAccounts = append(fraudAccounts, acc1)
	fmt.Printf("Generated Fake Account #1, as fraud unsafe: \npub: %v\npriv: %v\n\n", acc1Kp.Address(), strkey.MustEncode(strkey.VersionByteSeed, []byte(acc1Kp.Seed())))

	acc2Kp := keypair.MustRandom()
	horizonclient.DefaultTestNetClient.Fund(acc1Kp.Address())

	acc2 := fraudulentLmdbValueModel{
		Tags:    []string{"malicious"},
		Address: acc2Kp.Address(),
		Domain:  "domain.com",
		Name:    "acc 2",
	}
	fraudAccounts = append(fraudAccounts, acc2)
	fmt.Printf("Generated Fake Account #2, as fraud malicious: \npub: %v\npriv: %v\n\n", acc2Kp.Address(), strkey.MustEncode(strkey.VersionByteSeed, []byte(acc2Kp.Seed())))

	acc3Kp := keypair.MustRandom()
	horizonclient.DefaultTestNetClient.Fund(acc3Kp.Address())

	acc3 := fraudulentLmdbValueModel{
		Tags:    []string{"malicious", "unsafe"},
		Address: acc2Kp.Address(),
		Domain:  "domain.com",
		Name:    "acc 2",
	}
	fraudAccounts = append(fraudAccounts, acc3)
	fmt.Printf("Generated Fake Account #3, as fraud malicious, unsafe: \npub: %v\npriv: %v\n\n", acc3Kp.Address(), strkey.MustEncode(strkey.VersionByteSeed, []byte(acc3Kp.Seed())))

	acc4Kp := keypair.MustRandom()
	horizonclient.DefaultTestNetClient.Fund(acc4Kp.Address())
	fmt.Printf("Generated Fake Account #4, no fraud: \npub: %v\npriv: %v\n\n", acc4Kp.Address(), strkey.MustEncode(strkey.VersionByteSeed, []byte(acc4Kp.Seed())))

	// create an environment and make sure it is eventually closed.
	env, err := lmdb.NewEnv()
	if err != nil {
		log.Panicf("can't seed accounts, %v", err)
	}
	defer env.Close()

	err = env.SetMaxDBs(1)
	if err != nil {
		log.Panicf("can't seed accounts, %v", err)
	}
	err = env.SetMapSize(1 << 30)
	if err != nil {
		log.Panicf("can't seed accounts, %v", err)
	}
	err = env.Open(lmdbPath, 0, fs.FileMode(uint(0777)))
	if err != nil {
		log.Panicf("can't seed accounts, %v", err)
	}

	staleReaders, err := env.ReaderCheck()
	if err != nil {
		log.Panicf("can't seed accounts, %v", err)
	}
	if staleReaders > 0 {
		log.Printf("cleared %d reader slots from dead processes", staleReaders)
	}

	var dbi lmdb.DBI
	err = env.Update(func(txn *lmdb.Txn) (err error) {
		dbi, err = txn.OpenRoot(0)
		return err
	})
	if err != nil {
		log.Panicf("can't seed accounts, %v", err)
	}

	for _, account := range fraudAccounts {
		err = env.Update(func(txn *lmdb.Txn) (err error) {

			jsonBytes, err := json.Marshal(account)
			if err != nil {
				return err
			}

			err = txn.Put(dbi, []byte(account.Address), jsonBytes, 0)
			if err != nil {
				return err
			}
			return nil
		})

		if err != nil {
			log.Panicf("can't seed fraud accounts, %v", err)
		}
	}
}
