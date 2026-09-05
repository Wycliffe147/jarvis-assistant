#!/data/data/com.termux/files/usr/bin/bash

# Kill Jarvis main process
pkill -9 -f "jarvis.main"
pkill -9 -f "jarvis_v3.main"

# Kill Piper server and related processes
pkill -9 -f "piper_server"
pkill -9 -f "piper/piper"
pkill -9 -f "piper_watchdog"

# Kill any log tailing scripts
pkill -9 -f "tail-jarvis-log.sh"

# Release wake lock
termux-wake-unlock

termux-toast "Jarvis stopped"
echo "Jarvis and related processes have been terminated."
