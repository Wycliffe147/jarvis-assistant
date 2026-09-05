#!/data/data/com.termux/files/usr/bin/bash

# Configuration
PIPER_BIN="/data/data/com.termux/files/home/piper/piper"
MODEL_PATH="/data/data/com.termux/files/home/piper/en_GB-southern_english_female-low.onnx"
OUTPUT_WAV="/data/data/com.termux/files/home/piper/shortcut_output.wav"

# Open multi-line text input dialog
RESULT=$(termux-dialog text -m -t "Piper Reader" -i "Enter or paste text to read...")

# Extract text and run piper
python3 -c "
import sys, json, subprocess

try:
    data = json.loads(sys.argv[1])
    if data.get('code') == -1:
        text = data.get('text', '').strip()
        if text:
            # Construct the command to run inside Ubuntu
            # We use stdin to pass the text to avoid shell quoting nightmares
            inner_cmd = [sys.argv[2], '--model', sys.argv[3], '--output_file', sys.argv[4]]
            
            # Use proot-distro run ubuntu to execute it
            # We wrap it in bash -c to use pipes or just run the binary directly if possible
            # Actually, running the binary directly with stdin is easiest
            outer_cmd = ['proot-distro', 'run', 'ubuntu', '--'] + inner_cmd
            
            subprocess.run(outer_cmd, input=text, text=True, check=True)
            
            # Play audio
            subprocess.run(['termux-media-player', 'play', sys.argv[4]])
except Exception as e:
    # print(e) 
    pass
" "$RESULT" "$PIPER_BIN" "$MODEL_PATH" "$OUTPUT_WAV"
