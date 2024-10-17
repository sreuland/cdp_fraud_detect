import os
import lmdb
import json

# PUT ops data
addresses_to_insert = [
    #"GINSERTNEWADDRESS1234567890",
    #"GINSERTNEWADDRESS0987654321"
]
data_to_insert = [
    {
        'address': "GINSERTNEWADDRESS1234567890",
        'domain': 'example.com',
        'name': 'Example Name 1',
        'tags': ['unsafe']
    },
    {
        'address': "GINSERTNEWADDRESS0987654321",
        'domain': 'another-example.com',
        'name': 'Example Name 2',
        'tags': ['malicious']
    }
]

# POST ops data
addresses_to_update = [
    #"GAEDLNMCQZOSLY7Y4NW3DTEWQEVVCXYYMBDNGPPGBMQH4GFYECBI7YVK",
    #"GA3WKI3NHYHN7VQQZE2XA2PNUDLLET7VQO5JIMSMEVWUHJEJBLHWGJDI"
]
data_to_update = [
    {
        'address': "GAEDLNMCQZOSLY7Y4NW3DTEWQEVVCXYYMBDNGPPGBMQH4GFYECBI7YVK",
        'domain': 'updated-domain.com',
        'name': 'Updated Name 1',
        'tags': ['malicious', 'unsafe']
    },
    {
        'address': "GA3WKI3NHYHN7VQQZE2XA2PNUDLLET7VQO5JIMSMEVWUHJEJBLHWGJDI",
        'domain': 'yet-another-domain.com',
        'name': 'Updated Name 2',
        'tags': ['safe']
    }
]

# DEL ops data
addresses_to_delete = [
    #"GA5U3QQQRZABN5ENSNZ3ELCCRPJBPJRKZL5RA5URQMCKQN5OLB7SJVI4",
    #"GA3WKI3NHYHN7VQQZE2XA2PNUDLLET7VQO5JIMSMEVWUHJEJBLHWGJDI"
]

# GET ops data
addresses_to_get = [
    "GAEDLNMCQZOSLY7Y4NW3DTEWQEVVCXYYMBDNGPPGBMQH4GFYECBI7YVK",
    "GINSERTNEWADDRESS1234567890"
]

def insert_data(env, addresses, data_list):
    with env.begin(write=True) as txn:
        for address, data in zip(addresses, data_list):
            txn.put(address.encode(), json.dumps(data).encode())
            print(f"Inserted data for address: {address}")

def update_data(env, addresses, data_list):
    with env.begin(write=True) as txn:
        for address, data in zip(addresses, data_list):
            if txn.get(address.encode()) is not None:
                txn.put(address.encode(), json.dumps(data).encode())
                print(f"Updated data for address: {address}")
            else:
                print(f"Address {address} not found for update")

def delete_data(env, addresses):
    with env.begin(write=True) as txn:
        for address in addresses:
            if txn.delete(address.encode()):
                print(f"Deleted data for address: {address}")
            else:
                print(f"Address {address} not found for deletion")

def retrieve_data(env, addresses):
    with env.begin() as txn:
        for address in addresses:
            value = txn.get(address.encode())
            if value is not None:
                account_data = json.loads(value.decode())
                print(f"Retrieved data for address {address}: {json.dumps(account_data, indent=2)}")
            else:
                print(f"No data found for address {address}")

if __name__ == "__main__":
    db_path = '/app/fraud_accts_data' if os.getenv('DOCKER_ENV') == 'true' else './fraud_accts_data'
    env = lmdb.open(db_path, map_size=1024 * 1024 * 1024)  # 1GB map size

    try:
        # Check and perform PUT operation (insert)
        if addresses_to_insert and data_to_insert:
            print("PUT: Insert operation")
            insert_data(env, addresses_to_insert, data_to_insert)
        else:
            print("Skipping PUT operation: No data to insert")

        # Check and perform POST operation (update)
        if addresses_to_update and data_to_update:
            print("\nPOST: Update operation")
            update_data(env, addresses_to_update, data_to_update)
        else:
            print("Skipping POST operation: No data to update")

        # Check and perform GET operation (retrieve)
        if addresses_to_get:
            print("\nGET: Retrieve operation")
            retrieve_data(env, addresses_to_get)
        else:
            print("Skipping GET operation: No addresses to retrieve")

        # Check and perform DELETE operation
        if addresses_to_delete:
            print("\nDELETE: Delete operation")
            delete_data(env, addresses_to_delete)
        else:
            print("Skipping DELETE operation: No addresses to delete")

    finally:
        env.close()
