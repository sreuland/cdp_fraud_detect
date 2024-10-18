# cdp_fraud_detect
cdp hackathon

## How to Build/Run/Demo

Create and fund four test accounts on Testnet using [Stellar Laboratory](https://lab.stellar.org/account/create?$=network$id=testnet&label=Testnet&horizonUrl=https:////horizon-testnet.stellar.org&rpcUrl=https:////soroban-testnet.stellar.org&passphrase=Test%20SDF%20Network%20/;%20September%202015;&endpoints$params$order=desc&limit=200;;&transaction$build$operations@$operation_type=&params@;;):

afterwards, you will have:

Acc-1 = GBBVMABET5UTIJM7IPW3TUI2UXALQXXINBKYTB6PIF5QE7RB4DMYJPOF

Acc-2 = GBQ3QCMC4LRW3JUCHORIKOTWNPQBZNWOTTIZIULMWS4VMFHRUDNHJA3R

Acc-3 = GAUJW4CUUTBKIVUTXPQARDUSSPVDLXKMFAPAK64QWJXQ4I75C4ORQ4OR

Acc-4 = GBITZDRWKX3OOTV3QMQFKVWM7QNW6RZ6DSY6367DS2RRY644WIZF3L2L
 
Demonstrate the fraud detection can be done against these testnet accounts:

Acc-1, Acc-2 and Acc-3 can be artificially inserted into the local fraudulent accounts data, which are also fed externally from stellarxpert feed, this is to facilitate repeateable demo, as these new accounts won't be marked as fraudulent in stellarxpert feed.

Edit ./fetch_store_unsafe_accts/test_data_config.json, and set the account addresses you just created into that file, when demo is started, they will be seeded automatically into local fraudulent accounts data. 

1. run `docker compose up --build` from top folder of repo.
2. browse to localhost:8000, login
3. register Acc-2 for watch
4. Use lab or freighter, make Acc-1 create a tx to send payment to Acc-2
5. Go to activity list, see this payment show up as a fraud related to Acc-2, click on the tx hash link to see detail on horizon
6. unregister Acc-2, register for `*`
7. Use lab or freighter, make Acc-4 create a tx to send payment Acc-3
8. Go to activity list, see this payment show up as a fraud related to Acc-3 due to `*`, click on the tx hash link to see detail on horizon