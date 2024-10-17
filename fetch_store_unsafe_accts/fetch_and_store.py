import os
import lmdb
import requests
import json
import time
import schedule
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
from threading import Thread
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import logging
import signal
import sys

# Logging setup
log_file_path = os.path.join(os.path.dirname(__file__), 'fraud_data_fetch_store.log')
logging.basicConfig(filename=log_file_path, filemode='w', format='%(asctime)s - %(message)s', level=logging.INFO)

MAX_WORKERS = 25
BATCH_SIZE = 200
FETCH_QUEUE = Queue()

# Graceful shutdown
def signal_handler(sig, frame):
    logging.info('Shutting down gracefully...  :)')
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# Retry logic for API issues
def requests_retry_session(retries=3, backoff_factor=0.3, status_forcelist=(429, 500, 502, 503, 504)):
    session = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=frozenset(['GET', 'POST'])
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def fetch_batch(cursor=None):
    base_url = "https://api.stellar.expert/explorer/directory"
    params = {"tag[]": ["malicious", "unsafe"], "limit": BATCH_SIZE}
    if cursor:
        params['cursor'] = cursor

    try:
        session = requests_retry_session()
        response = session.get(base_url, params=params)
        response.raise_for_status()
        data = response.json()
        records = data['_embedded']['records']
        next_link = data['_links'].get('next', None)
        return records, next_link
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching data: {e}")
        return [], None

def producer_fetch_data(next_cursor=None):
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        while True:
            futures = [executor.submit(fetch_batch, next_cursor) for _ in range(1)]
            for future in as_completed(futures):
                try:
                    records, next_link = future.result()
                    if records:
                        FETCH_QUEUE.put(records)
                    else:
                        FETCH_QUEUE.put(None)
                        return
                except Exception as e:
                    logging.error(f"Producer fetch error: {e}")
                    FETCH_QUEUE.put(None)
                    return

                if next_link and 'href' in next_link:
                    next_cursor = next_link['href'].split('cursor=')[1]
                else:
                    FETCH_QUEUE.put(None)
                    return

def consumer_write_data():
    db_path = '/app/fraud_accts_data' if os.getenv('DOCKER_ENV') == 'true' else './fraud_accts_data'

    env = lmdb.open(db_path, map_size=1024 * 1024 * 1024)

    try:
        while True:
            records = FETCH_QUEUE.get()
            if records is None:
                break
            with env.begin(write=True) as txn:
                for item in records:
                    address = item['address']
                    clean_item = {
                        'address': item['address'],
                        'domain': item.get('domain'),
                        'name': item.get('name'),
                        'tags': item.get('tags', [])
                    }
                    txn.put(address.encode(), json.dumps(clean_item).encode())
    except Exception as e:
        logging.error(f"Error writing data to LMDB: {e}")
    finally:
        env.close()

def job():
    start_time = time.time()
    logging.info("Fetch Job started")

    producer_thread = Thread(target=producer_fetch_data)
    producer_thread.start()

    consumer_write_data()
    producer_thread.join()

    stats = get_stats()
    duration = time.time() - start_time
    logging.info(f"Job ended | Time taken: {duration:.2f} seconds | "
                f"Total: {stats['total']}, Malicious: {stats['malicious']}, Unsafe: {stats['unsafe']}, Malicious & Unsafe: {stats['malicious and unsafe']}")


def get_stats():
    db_path = '/app/fraud_accts_data' if os.getenv('DOCKER_ENV') == 'true' else './fraud_accts_data'

    env = lmdb.open(db_path, readonly=True)
    try:
        with env.begin() as txn:
            cursor = txn.cursor()
            total_count = malicious_count = unsafe_count = both_tags_count = 0
            for _, value in cursor:
                total_count += 1
                item = json.loads(value.decode())
                tags = item.get('tags', [])
                if 'malicious' in tags:
                    malicious_count += 1
                if 'unsafe' in tags:
                    unsafe_count += 1
                if 'malicious' in tags and 'unsafe' in tags:
                    both_tags_count += 1
    finally:
        env.close()

    return {
        'total': total_count,
        'malicious': malicious_count,
        'unsafe': unsafe_count,
        'malicious and unsafe': both_tags_count
    }

if __name__ == "__main__":
    fetch_interval = int(os.getenv('FETCH_INTERVAL_MINUTES', 15))

    job()  # Run the job once

    if os.getenv('DOCKER_ENV') == 'true':
        schedule.every(fetch_interval).minutes.do(job)

        while True:
            schedule.run_pending()
            time.sleep(1)
    else:
        sys.exit(0)
