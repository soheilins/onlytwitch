#!/usr/bin/env python3
import os
import sys
import time
import requests
from pathlib import Path

# ===== CONFIGURATION =====
FOLDER = "spear"
CHECK_INTERVAL = 60        # seconds between scans
MAX_RUNTIME = 6 * 3600     # 6 hours
# =========================

TOKEN = os.environ.get("RUBIKA_TOKEN")
CHAT_ID = os.environ.get("RUBIKA_CHAT_ID")

if not TOKEN or not CHAT_ID:
    print("❌ Missing RUBIKA_TOKEN or RUBIKA_CHAT_ID")
    sys.exit(1)

BASE_API = f"https://botapi.rubika.ir/v3/{TOKEN}"
SEND_MESSAGE_URL = f"{BASE_API}/sendMessage"
REQUEST_SEND_FILE_URL = f"{BASE_API}/requestSendFile"
SEND_FILE_URL = f"{BASE_API}/sendFile"

def send_text_message(text):
    """Send a plain text message to the chat."""
    try:
        resp = requests.post(SEND_MESSAGE_URL, json={"chat_id": CHAT_ID, "text": text}, timeout=10)
        if resp.status_code == 200:
            print(f"  📨 Text sent: {text[:50]}")
        else:
            print(f"  ⚠️ Text send failed: {resp.text[:100]}")
    except Exception as e:
        print(f"  ⚠️ Text send error: {e}")

def upload_and_send_file(file_path):
    """Upload a file to Rubika and send it. Returns True on success."""
    filename = os.path.basename(file_path)
    # First, send the filename as a separate text message
    send_text_message(f"📄 Sending: {filename}")

    # Retry loop for upload
    for attempt in range(10):   # max 10 attempts, then give up
        try:
            # 1. Request upload URL
            resp = requests.post(REQUEST_SEND_FILE_URL, json={"type": "File"}, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") != "OK":
                print(f"  ❌ requestSendFile error: {data}")
                time.sleep(2)
                continue
            upload_url = data["data"]["upload_url"]

            # 2. Upload file
            with open(file_path, 'rb') as f:
                files = {"file": (filename, f, "application/octet-stream")}
                upload_resp = requests.post(upload_url, files=files, timeout=30)
                upload_resp.raise_for_status()
                upload_data = upload_resp.json()
                if upload_data.get("status") != "OK":
                    print(f"  ❌ Upload error: {upload_data}")
                    time.sleep(2)
                    continue
                file_id = upload_data["data"]["file_id"]

            # 3. Send file to chat
            send_payload = {
                "chat_id": CHAT_ID,
                "file_id": file_id,
                "text": filename
            }
            send_resp = requests.post(SEND_FILE_URL, json=send_payload, timeout=15)
            send_resp.raise_for_status()
            print(f"  ✅ Sent {filename}")
            return True

        except Exception as e:
            print(f"  ⚠️ Attempt {attempt+1} failed: {e}")
            time.sleep(2)

    print(f"  ❌ Giving up on {filename} after 10 attempts")
    return False

def main():
    print("=" * 50)
    print("Rubika Spear Folder Watcher (Python)")
    print(f"Folder: {FOLDER}")
    print(f"Check interval: {CHECK_INTERVAL}s")
    print(f"Max runtime: {MAX_RUNTIME}s (6 hours)")
    print("=" * 50)

    start_time = time.time()
    sent_files = set()

    # Wait for folder to exist and contain files
    while True:
        if os.path.isdir(FOLDER):
            files = [f for f in Path(FOLDER).iterdir() if f.is_file()]
            if files:
                print(f"✅ Folder '{FOLDER}' found with {len(files)} file(s).")
                break
            else:
                print(f"📁 Folder '{FOLDER}' exists but is empty. Waiting...")
        else:
            print(f"❌ Folder '{FOLDER}' does not exist. Waiting...")
        time.sleep(CHECK_INTERVAL)

    # Send all files that exist now (fresh start – send everything)
    all_files = sorted(Path(FOLDER).iterdir(), key=lambda p: p.name)
    for file_path in all_files:
        if file_path.is_file():
            if upload_and_send_file(str(file_path)):
                sent_files.add(str(file_path))
            time.sleep(1)   # small delay to avoid rate limits

    print("✅ Initial files sent. Now watching for new files...")

    # Continuous watch (up to 6 hours)
    while (time.time() - start_time) < MAX_RUNTIME:
        current_files = set(str(p) for p in Path(FOLDER).iterdir() if p.is_file())
        new_files = current_files - sent_files
        for file_path in sorted(new_files):
            if upload_and_send_file(file_path):
                sent_files.add(file_path)
            time.sleep(1)
        time.sleep(CHECK_INTERVAL)

    print("⏰ 6 hours reached. Exiting. Next scheduled run will continue.")

if __name__ == "__main__":
    main()
