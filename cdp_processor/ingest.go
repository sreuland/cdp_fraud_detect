package main

import (
	"fmt"
	"sort"

	"github.com/pkg/errors"
	"github.com/stellar/go/ingest"
	"github.com/stellar/go/support/contractevents"
	"github.com/stellar/go/toid"
	"github.com/stellar/go/xdr"
)

// All this is direct copy/paste from services/horizon/internal/ingest/processors/operations_processor.go and
// partipant_processor.go

func participantsForMeta(meta xdr.TransactionMeta) ([]xdr.AccountId, error) {
	var participants []xdr.AccountId
	if meta.Operations == nil {
		return participants, nil
	}

	for _, op := range *meta.Operations {
		var accounts []xdr.AccountId
		accounts, err := participantsForChanges(op.Changes)
		if err != nil {
			return nil, err
		}

		participants = append(participants, accounts...)
	}

	return participants, nil
}

func participantsForChanges(
	changes xdr.LedgerEntryChanges,
) ([]xdr.AccountId, error) {
	var participants []xdr.AccountId

	for _, c := range changes {
		var participant *xdr.AccountId

		switch c.Type {
		case xdr.LedgerEntryChangeTypeLedgerEntryCreated:
			participant = participantsForLedgerEntry(c.MustCreated())
		case xdr.LedgerEntryChangeTypeLedgerEntryRemoved:
			participant = participantsForLedgerKey(c.MustRemoved())
		case xdr.LedgerEntryChangeTypeLedgerEntryUpdated:
			participant = participantsForLedgerEntry(c.MustUpdated())
		case xdr.LedgerEntryChangeTypeLedgerEntryState:
			participant = participantsForLedgerEntry(c.MustState())
		default:
			return nil, errors.Errorf("Unknown change type: %s", c.Type)
		}

		if participant != nil {
			participants = append(participants, *participant)
		}
	}

	return participants, nil
}

func participantsForLedgerEntry(le xdr.LedgerEntry) *xdr.AccountId {
	if le.Data.Type != xdr.LedgerEntryTypeAccount {
		return nil
	}
	aid := le.Data.MustAccount().AccountId
	return &aid
}

func participantsForLedgerKey(lk xdr.LedgerKey) *xdr.AccountId {
	if lk.Type != xdr.LedgerEntryTypeAccount {
		return nil
	}
	aid := lk.MustAccount().AccountId
	return &aid
}

func dedupeParticipants(in []xdr.AccountId) []xdr.AccountId {
	if len(in) <= 1 {
		return in
	}
	sort.Slice(in, func(i, j int) bool {
		return in[i].Address() < in[j].Address()
	})
	insert := 1
	for cur := 1; cur < len(in); cur++ {
		if in[cur].Equals(in[cur-1]) {
			continue
		}
		if insert != cur {
			in[insert] = in[cur]
		}
		insert++
	}
	return in[:insert]
}

func getParticipants(transaction ingest.LedgerTransaction, sequence uint32) ([]string, error) {
	// this is cloned from internal horizon ingestion, participants_processor.go
	participants := []xdr.AccountId{
		transaction.Envelope.SourceAccount().ToAccountId(),
	}
	if transaction.Envelope.IsFeeBump() {
		participants = append(participants, transaction.Envelope.FeeBumpAccount().ToAccountId())
	}

	p, err := participantsForMeta(transaction.UnsafeMeta)
	if err != nil {
		return nil, err
	}
	participants = append(participants, p...)

	p, err = participantsForChanges(transaction.FeeChanges)
	if err != nil {
		return nil, err
	}
	participants = append(participants, p...)

	for opi, op := range transaction.Envelope.Operations() {
		operation := transactionOperationWrapper{
			index:          uint32(opi),
			transaction:    transaction,
			operation:      op,
			ledgerSequence: sequence,
		}

		p, err := operation.Participants()
		if err != nil {
			return nil, errors.Wrapf(
				err, "could not determine operation %v participants", operation.ID(),
			)
		}
		participants = append(participants, p...)
	}

	participants = dedupeParticipants(participants)
	particpantStrs := []string{}
	for _, participant := range participants {
		particpantStrs = append(particpantStrs, participant.Address()) // note the = instead of :=
	}

	return particpantStrs, nil
}

type transactionOperationWrapper struct {
	index          uint32
	transaction    ingest.LedgerTransaction
	operation      xdr.Operation
	ledgerSequence uint32
	network        string
}

// ID returns the ID for the operation.
func (operation *transactionOperationWrapper) ID() int64 {
	return toid.New(
		int32(operation.ledgerSequence),
		int32(operation.transaction.Index),
		int32(operation.index+1),
	).ToInt64()
}

// Order returns the operation order.
func (operation *transactionOperationWrapper) Order() uint32 {
	return operation.index + 1
}

// TransactionID returns the id for the transaction related with this operation.
func (operation *transactionOperationWrapper) TransactionID() int64 {
	return toid.New(int32(operation.ledgerSequence), int32(operation.transaction.Index), 0).ToInt64()
}

// SourceAccount returns the operation's source account.
func (operation *transactionOperationWrapper) SourceAccount() *xdr.MuxedAccount {
	sourceAccount := operation.operation.SourceAccount
	if sourceAccount != nil {
		return sourceAccount
	} else {
		ret := operation.transaction.Envelope.SourceAccount()
		return &ret
	}
}

// OperationType returns the operation type.
func (operation *transactionOperationWrapper) OperationType() xdr.OperationType {
	return operation.operation.Body.Type
}

func (operation *transactionOperationWrapper) getSignerSponsorInChange(signerKey string, change ingest.Change) xdr.SponsorshipDescriptor {
	if change.Type != xdr.LedgerEntryTypeAccount || change.Post == nil {
		return nil
	}

	preSigners := map[string]xdr.AccountId{}
	if change.Pre != nil {
		account := change.Pre.Data.MustAccount()
		preSigners = account.SponsorPerSigner()
	}

	account := change.Post.Data.MustAccount()
	postSigners := account.SponsorPerSigner()

	pre, preFound := preSigners[signerKey]
	post, postFound := postSigners[signerKey]

	if !postFound {
		return nil
	}

	if preFound {
		formerSponsor := pre.Address()
		newSponsor := post.Address()
		if formerSponsor == newSponsor {
			return nil
		}
	}

	return &post
}

func (operation *transactionOperationWrapper) getSponsor() (*xdr.AccountId, error) {
	changes, err := operation.transaction.GetOperationChanges(operation.index)
	if err != nil {
		return nil, err
	}
	var signerKey string
	if setOps, ok := operation.operation.Body.GetSetOptionsOp(); ok && setOps.Signer != nil {
		signerKey = setOps.Signer.Key.Address()
	}

	for _, c := range changes {
		// Check Signer changes
		if signerKey != "" {
			if sponsorAccount := operation.getSignerSponsorInChange(signerKey, c); sponsorAccount != nil {
				return sponsorAccount, nil
			}
		}

		// Check Ledger key changes
		if c.Pre != nil || c.Post == nil {
			// We are only looking for entry creations denoting that a sponsor
			// is associated to the ledger entry of the operation.
			continue
		}
		if sponsorAccount := c.Post.SponsoringID(); sponsorAccount != nil {
			return sponsorAccount, nil
		}
	}

	return nil, nil
}

type liquidityPoolDelta struct {
	ReserveA        xdr.Int64
	ReserveB        xdr.Int64
	TotalPoolShares xdr.Int64
}

var errLiquidityPoolChangeNotFound = errors.New("liquidity pool change not found")

func (operation *transactionOperationWrapper) getLiquidityPoolAndProductDelta(lpID *xdr.PoolId) (*xdr.LiquidityPoolEntry, *liquidityPoolDelta, error) {
	changes, err := operation.transaction.GetOperationChanges(operation.index)
	if err != nil {
		return nil, nil, err
	}

	for _, c := range changes {
		if c.Type != xdr.LedgerEntryTypeLiquidityPool {
			continue
		}
		// The delta can be caused by a full removal or full creation of the liquidity pool
		var lp *xdr.LiquidityPoolEntry
		var preA, preB, preShares xdr.Int64
		if c.Pre != nil {
			if lpID != nil && c.Pre.Data.LiquidityPool.LiquidityPoolId != *lpID {
				// if we were looking for specific pool id, then check on it
				continue
			}
			lp = c.Pre.Data.LiquidityPool
			if c.Pre.Data.LiquidityPool.Body.Type != xdr.LiquidityPoolTypeLiquidityPoolConstantProduct {
				return nil, nil, fmt.Errorf("unexpected liquity pool body type %d", c.Pre.Data.LiquidityPool.Body.Type)
			}
			cpPre := c.Pre.Data.LiquidityPool.Body.ConstantProduct
			preA, preB, preShares = cpPre.ReserveA, cpPre.ReserveB, cpPre.TotalPoolShares
		}
		var postA, postB, postShares xdr.Int64
		if c.Post != nil {
			if lpID != nil && c.Post.Data.LiquidityPool.LiquidityPoolId != *lpID {
				// if we were looking for specific pool id, then check on it
				continue
			}
			lp = c.Post.Data.LiquidityPool
			if c.Post.Data.LiquidityPool.Body.Type != xdr.LiquidityPoolTypeLiquidityPoolConstantProduct {
				return nil, nil, fmt.Errorf("unexpected liquity pool body type %d", c.Post.Data.LiquidityPool.Body.Type)
			}
			cpPost := c.Post.Data.LiquidityPool.Body.ConstantProduct
			postA, postB, postShares = cpPost.ReserveA, cpPost.ReserveB, cpPost.TotalPoolShares
		}
		delta := &liquidityPoolDelta{
			ReserveA:        postA - preA,
			ReserveB:        postB - preB,
			TotalPoolShares: postShares - preShares,
		}
		return lp, delta, nil
	}

	return nil, nil, errLiquidityPoolChangeNotFound
}

// OperationResult returns the operation's result record
func (operation *transactionOperationWrapper) OperationResult() *xdr.OperationResultTr {
	results, _ := operation.transaction.Result.OperationResults()
	tr := results[operation.index].MustTr()
	return &tr
}

func filterEvents(diagnosticEvents []xdr.DiagnosticEvent) []xdr.ContractEvent {
	var filtered []xdr.ContractEvent
	for _, diagnosticEvent := range diagnosticEvents {
		if !diagnosticEvent.InSuccessfulContractCall || diagnosticEvent.Event.Type != xdr.ContractEventTypeContract {
			continue
		}
		filtered = append(filtered, diagnosticEvent.Event)
	}
	return filtered
}

func getLedgerKeyParticipants(ledgerKey xdr.LedgerKey) []xdr.AccountId {
	var result []xdr.AccountId
	switch ledgerKey.Type {
	case xdr.LedgerEntryTypeAccount:
		result = append(result, ledgerKey.Account.AccountId)
	case xdr.LedgerEntryTypeClaimableBalance:
		// nothing to do
	case xdr.LedgerEntryTypeData:
		result = append(result, ledgerKey.Data.AccountId)
	case xdr.LedgerEntryTypeOffer:
		result = append(result, ledgerKey.Offer.SellerId)
	case xdr.LedgerEntryTypeTrustline:
		result = append(result, ledgerKey.TrustLine.AccountId)
	}
	return result
}

// Determines if an operation is qualified to represent a payment in horizon terms.
func (operation *transactionOperationWrapper) IsPayment() bool {
	switch operation.OperationType() {
	case xdr.OperationTypeCreateAccount:
		return true
	case xdr.OperationTypePayment:
		return true
	case xdr.OperationTypePathPaymentStrictReceive:
		return true
	case xdr.OperationTypePathPaymentStrictSend:
		return true
	case xdr.OperationTypeAccountMerge:
		return true
	case xdr.OperationTypeInvokeHostFunction:
		diagnosticEvents, err := operation.transaction.GetDiagnosticEvents()
		if err != nil {
			return false
		}
		// scan all the contract events for at least one SAC event, qualified to be a payment
		// in horizon
		for _, contractEvent := range filterEvents(diagnosticEvents) {
			if sacEvent, err := contractevents.NewStellarAssetContractEvent(&contractEvent, operation.network); err == nil {
				switch sacEvent.GetType() {
				case contractevents.EventTypeTransfer:
					return true
				case contractevents.EventTypeMint:
					return true
				case contractevents.EventTypeClawback:
					return true
				case contractevents.EventTypeBurn:
					return true
				}
			}
		}
	}

	return false
}

func (operation *transactionOperationWrapper) findInitatingBeginSponsoringOp() *transactionOperationWrapper {
	if !operation.transaction.Result.Successful() {
		// Failed transactions may not have a compliant sandwich structure
		// we can rely on (e.g. invalid nesting or a being operation with the wrong sponsoree ID)
		// and thus we bail out since we could return incorrect information.
		return nil
	}
	sponsoree := operation.SourceAccount().ToAccountId()
	operations := operation.transaction.Envelope.Operations()
	for i := int(operation.index) - 1; i >= 0; i-- {
		if beginOp, ok := operations[i].Body.GetBeginSponsoringFutureReservesOp(); ok &&
			beginOp.SponsoredId.Address() == sponsoree.Address() {
			result := *operation
			result.index = uint32(i)
			result.operation = operations[i]
			return &result
		}
	}
	return nil
}

func (operation *transactionOperationWrapper) Participants() ([]xdr.AccountId, error) {
	participants := []xdr.AccountId{}
	participants = append(participants, operation.SourceAccount().ToAccountId())
	op := operation.operation

	switch operation.OperationType() {
	case xdr.OperationTypeCreateAccount:
		participants = append(participants, op.Body.MustCreateAccountOp().Destination)
	case xdr.OperationTypePayment:
		participants = append(participants, op.Body.MustPaymentOp().Destination.ToAccountId())
	case xdr.OperationTypePathPaymentStrictReceive:
		participants = append(participants, op.Body.MustPathPaymentStrictReceiveOp().Destination.ToAccountId())
	case xdr.OperationTypePathPaymentStrictSend:
		participants = append(participants, op.Body.MustPathPaymentStrictSendOp().Destination.ToAccountId())
	case xdr.OperationTypeManageBuyOffer:
		// the only direct participant is the source_account
	case xdr.OperationTypeManageSellOffer:
		// the only direct participant is the source_account
	case xdr.OperationTypeCreatePassiveSellOffer:
		// the only direct participant is the source_account
	case xdr.OperationTypeSetOptions:
		// the only direct participant is the source_account
	case xdr.OperationTypeChangeTrust:
		// the only direct participant is the source_account
	case xdr.OperationTypeAllowTrust:
		participants = append(participants, op.Body.MustAllowTrustOp().Trustor)
	case xdr.OperationTypeAccountMerge:
		participants = append(participants, op.Body.MustDestination().ToAccountId())
	case xdr.OperationTypeInflation:
		// the only direct participant is the source_account
	case xdr.OperationTypeManageData:
		// the only direct participant is the source_account
	case xdr.OperationTypeBumpSequence:
		// the only direct participant is the source_account
	case xdr.OperationTypeCreateClaimableBalance:
		for _, c := range op.Body.MustCreateClaimableBalanceOp().Claimants {
			participants = append(participants, c.MustV0().Destination)
		}
	case xdr.OperationTypeClaimClaimableBalance:
		// the only direct participant is the source_account
	case xdr.OperationTypeBeginSponsoringFutureReserves:
		participants = append(participants, op.Body.MustBeginSponsoringFutureReservesOp().SponsoredId)
	case xdr.OperationTypeEndSponsoringFutureReserves:
		beginSponsorshipOp := operation.findInitatingBeginSponsoringOp()
		if beginSponsorshipOp != nil {
			participants = append(participants, beginSponsorshipOp.SourceAccount().ToAccountId())
		}
	case xdr.OperationTypeRevokeSponsorship:
		op := operation.operation.Body.MustRevokeSponsorshipOp()
		switch op.Type {
		case xdr.RevokeSponsorshipTypeRevokeSponsorshipLedgerEntry:
			participants = append(participants, getLedgerKeyParticipants(*op.LedgerKey)...)
		case xdr.RevokeSponsorshipTypeRevokeSponsorshipSigner:
			participants = append(participants, op.Signer.AccountId)
			// We don't add signer as a participant because a signer can be arbitrary account.
			// This can spam successful operations history of any account.
		}
	case xdr.OperationTypeClawback:
		op := operation.operation.Body.MustClawbackOp()
		participants = append(participants, op.From.ToAccountId())
	case xdr.OperationTypeClawbackClaimableBalance:
		// the only direct participant is the source_account
	case xdr.OperationTypeSetTrustLineFlags:
		op := operation.operation.Body.MustSetTrustLineFlagsOp()
		participants = append(participants, op.Trustor)
	case xdr.OperationTypeLiquidityPoolDeposit:
		// the only direct participant is the source_account
	case xdr.OperationTypeLiquidityPoolWithdraw:
		// the only direct participant is the source_account
	case xdr.OperationTypeInvokeHostFunction:
		// the only direct participant is the source_account
	case xdr.OperationTypeExtendFootprintTtl:
		// the only direct participant is the source_account
	case xdr.OperationTypeRestoreFootprint:
		// the only direct participant is the source_account
	default:
		return participants, fmt.Errorf("unknown operation type: %s", op.Body.Type)
	}

	sponsor, err := operation.getSponsor()
	if err != nil {
		return nil, err
	}
	if sponsor != nil {
		participants = append(participants, *sponsor)
	}

	return dedupeParticipants(participants), nil
}
