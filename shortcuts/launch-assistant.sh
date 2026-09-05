#!/data/data/com.termux/files/usr/bin/bash
# Acquire wake lock
termux-wake-lock

# Set log file to match boot script
LOGFILE="$HOME/boot_debug.log"

echo "--- Manual Start at $(date) ---" >> "$LOGFILE"

cd ~
# Start Piper Server in background
proot-distro run ubuntu -- python3 -u /data/data/com.termux/files/home/piper_server_v2.py >> "$HOME/piper_server.log" 2>&1 &

# Launch in background with unbuffered output
/data/data/com.termux/files/usr/bin/python -u -m jarvis.main >> "$LOGFILE" 2>&1 &

termux-toast "Assistant started manually"
