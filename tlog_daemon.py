import time
import logging
import signal
import sys
from datetime import datetime

from trusted_container_log.api import TrustedLogAPI
from trusted_container_log.database import init_db
from trusted_container_log.tlog_impl import SigstoreLogAdapter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("tlog_daemon")

# Global flag to control daemon lifecycle
stop_daemon = False

def signal_handler(sig, frame):
    global stop_daemon
    logger.info("Shutdown signal received. Exiting daemon loop gracefully...")
    stop_daemon = True

def main():
    global stop_daemon
    
    # Register termination signals
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("Initializing Trusted Container Log Submission Daemon...")
    init_db()

    # The daemon exclusively hits the remote network - skip local mr injections
    trusted_log = TrustedLogAPI(
        local_mr=None,
        immutable_log=SigstoreLogAdapter()
    )
    logger.info("Out-of-process daemon successfully linked to SQLite queue and Sigstore adapter.")

    interval = 5.0 # Set polling interval explicitly as constant

    while not stop_daemon:
        try:
            queue_status = trusted_log.get_commit_queue_status()
            if queue_status.has_queued_records and queue_status.next_record_id:
                logger.info(f"Picked up queued record ID: {queue_status.next_record_id}. Submitting...")
                result = trusted_log.submit_record(queue_status.next_record_id)
                if getattr(result, "status", None) == "confirmed":
                    logger.info(f"Submit Success: Record {queue_status.next_record_id} accepted.")
                else:
                    logger.warning(f"Submit Warning: Record {queue_status.next_record_id} returned status {getattr(result, 'status', 'UNKNOWN')}.")
        except Exception as e:
            logger.error(f"Daemon encountered generalized error during submission cycle: {e}")
        
        # Incremental sleep to be responsive to graceful shutdown signals
        sleep_budget = interval
        while sleep_budget > 0 and not stop_daemon:
            time.sleep(min(1.0, sleep_budget))
            sleep_budget -= 1.0

    logger.info("Daemon has completely shut down.")

if __name__ == "__main__":
    main()