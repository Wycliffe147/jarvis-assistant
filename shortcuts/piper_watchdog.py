import subprocess
import time
import sys
import logging
import os

# --- Configuration ---
# This path is relative to the Ubuntu root or absolute inside proot
SERVER_SCRIPT = "/data/data/com.termux/files/home/piper_server_v2.py"
LOG_FILE = "/data/data/com.termux/files/home/piper_watchdog.log"

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE)
    ]
)
logger = logging.getLogger("piper-watchdog")

def run_watchdog():
    logger.info("Starting Piper Watchdog...")
    
    while True:
        logger.info(f"Launching Piper Server: {SERVER_SCRIPT}")
        
        try:
            # Start the server as a subprocess inside Ubuntu
            process = subprocess.Popen(
                ["proot-distro", "login", "ubuntu", "--", "python3", "-u", SERVER_SCRIPT],
                stdout=sys.stdout,
                stderr=sys.stderr
            )
            
            # Wait for the process to exit
            exit_code = process.wait()
            
            logger.warning(f"Piper Server exited with code {exit_code}.")
            
        except Exception as e:
            logger.error(f"Watchdog encountered an error: {e}")
        
        # Prevent rapid-fire restart loops if something is fundamentally broken
        logger.info("Restarting in 5 seconds...")
        time.sleep(5)

if __name__ == "__main__":
    if not os.path.exists(SERVER_SCRIPT):
        logger.error(f"Server script not found at {SERVER_SCRIPT}")
        sys.exit(1)
        
    try:
        run_watchdog()
    except KeyboardInterrupt:
        logger.info("Watchdog stopped by user.")
