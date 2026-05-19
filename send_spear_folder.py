#!/usr/bin/env python3
import os
import sys
import time
import requests
import subprocess
from pathlib import Path

# ===== CONFIGURATION =====
FOLDER = "spear"
CHECK_INTERVAL = 10        # seconds between folder scans
# =========================

TOKEN = os.environ.get("RUBIKA_TOKEN")
CHAT_ID = os.environ.get("RUBIKA_CHAT_ID")

if not TOKEN or not CHAT_ID:
    print("❌ Missing RUBIKA_TOKEN or RUBIKA_CHAT_ID")
    sys.exit(1)

BASE_API = f"https://botapi.rubika.ir/v3/{TOKEN}"
REQUEST_SEND_FILE_URL = f"{BASE_API}/requestSendFile"
SEND_FILE_URL = f"{BASE_API}/sendFile"

def git_pull():
    """Pull latest changes from the repository."""
    try:
        result = subprocess.run(
            ["git", "pull", "--ff-only"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            if "Already up to date" not in result.stdout:
                print("📥 Git pull: updated working copy")
            return True
        else:
            print(f"⚠️ Git pull failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"⚠️ Git pull error: {e}")
        return False

def upload_and_send_file(file_path):
    """
    Upload a file to Rubika and send it with the filename as caption.
    Retries forever until success (infinite retries).
    """
    filename = os.path.basename(file_path)
    attempt = 0

    while True:
        attempt += 1
        try:
            # 1. Request upload URL
            resp = requests.post(REQUEST_SEND_FILE_URL, json={"type": "File"}, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") != "OK":
                print(f"  ⚠️ requestSendFile error: {data} (attempt {attempt})")
                time.sleep(2)
                continue

            upload_url = data["data"]["upload_url"]

            # 2. Upload file
            with open(file_path, 'rb') as f:
                files = {"file": (filename, f, "application/octet-stream")}
                upload_resp = requests.post(upload_url, files=files, timeout=60)
                upload_resp.raise_for_status()
                upload_data = upload_resp.json()
                if upload_data.get("status") != "OK":
                    print(f"  ❌ Upload error: {upload_data} (attempt {attempt})")
                    time.sleep(2)
                    continue

                file_id = upload_data["data"]["file_id"]

            # 3. Send file to chat (filename as caption)
            send_payload = {
                "chat_id": CHAT_ID,
                "file_id": file_id,
                "text": filename
            }
            send_resp = requests.post(SEND_FILE_URL, json=send_payload, timeout=15)
            send_resp.raise_for_status()
            print(f"  ✅ Sent {filename} after {attempt} attempt(s)")
            return True

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 502:
                print(f"  ⚠️ 502 Bad Gateway (attempt {attempt}) – retrying in 5s...")
                time.sleep(5)
            else:
                print(f"  ⚠️ HTTP error {e.response.status_code} (attempt {attempt}) – retrying in 2s...")
                time.sleep(2)
        except Exception as e:
            print(f"  ⚠️ Attempt {attempt} failed: {e} – retrying in 2s...")
            time.sleep(2)

def main():
    print("=" * 50)
    print("Rubika Spear Folder Watcher (continuous)")
    print(f"Folder: {FOLDER}")
    print(f"Check interval: {CHECK_INTERVAL}s")
    print("No max runtime – will run until GitHub Actions stops the job.")
    print("=" * 50)

    sent_files = set()

    # Wait for folder to exist (with git pull each time)
    while True:
        git_pull()
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

    # Send all existing files (fresh start – send everything)
    all_files = sorted(Path(FOLDER).iterdir(), key=lambda p: p.name)
    for file_path in all_files:
        if file_path.is_file():
            upload_and_send_file(str(file_path))
            sent_files.add(str(file_path))
            time.sleep(1)

    print("✅ Initial files sent. Now watching for new files...")

    # Continuous watch – runs forever (until GitHub kills the job)
    while True:
        git_pull()   # get latest files from repo

        if not os.path.isdir(FOLDER):
            print(f"❌ Folder '{FOLDER}' disappeared. Waiting for it to return...")
            time.sleep(CHECK_INTERVAL)
            continue

        current_files = set(str(p) for p in Path(FOLDER).iterdir() if p.is_file())
        new_files = current_files - sent_files
        for file_path in sorted(new_files):
            upload_and_send_file(file_path)
            sent_files.add(file_path)
            time.sleep(1)
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
