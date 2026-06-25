# Shared state for the Jarvis assistant
is_speaking = False

# Vision upload compression (see tools/camera.py)
# None = not checked yet this session, True/False = cached result of `which ffmpeg`
ffmpeg_available = None
# Once the user explicitly says "go ahead without compression," this stays
# True for the rest of the session so they're not asked on every single
# photo/screenshot analysis -- only re-asked if Jarvis is restarted.
user_approved_uncompressed_upload = False
