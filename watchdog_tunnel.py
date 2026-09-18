import json
import os
import time
import urllib.request
import subprocess
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("x402-watchdog")

NGROK_API_URL = "http://127.0.0.1:4040/api/tunnels"
MANIFEST_PATH = ".well-known/x402.json"
README_PATH = "README.md"
CHECK_INTERVAL_SECONDS = 30


def get_active_ngrok_url() -> str:
    """Queries Ngrok's local inspection API for the active HTTPS tunnel URL."""
    try:
        req = urllib.request.Request(NGROK_API_URL)
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for tunnel in data.get("tunnels", []):
                public_url = tunnel.get("public_url", "")
                if public_url.startswith("https://"):
                    return public_url
    except Exception:
        pass
    return None


def update_manifest_and_sync(new_url: str):
    """Updates manifest files and pushes changes to GitHub if URL changed."""
    if not os.path.exists(MANIFEST_PATH):
        logger.error(f"Manifest file not found at {MANIFEST_PATH}")
        return

    with open(MANIFEST_PATH, "r") as f:
        manifest = json.load(f)

    # Check current active base URL stored in service endpoints
    current_service_url = manifest.get("services", [{}])[0].get("baseUrl", "")
    if current_service_url == new_url:
        logger.info(f"Ingress URL unchanged ({new_url}). No sync needed.")
        return

    logger.warning(f"Tunnel URL change detected! New ingress: {new_url}")

    # Update manifest
    for service in manifest.get("services", []):
        service["baseUrl"] = new_url
        service["endpoint"] = f"{new_url}/api/v1/extract"

    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)

    logger.info("Updated .well-known/x402.json with new ingress URL.")

    # Commit and push changes to GitHub
    try:
        subprocess.run(["git", "add", MANIFEST_PATH], check=True)
        subprocess.run(["git", "commit", "-m", f"auto: sync ngrok ingress URL to {new_url}"], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
        logger.info("[SUCCESS] Pushed updated manifest to GitHub x402-manifest repo.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to execute Git push: {e}")


def main():
    logger.info("Starting x402 Tunnel Watchdog service...")
    while True:
        ngrok_url = get_active_ngrok_url()
        if ngrok_url:
            update_manifest_and_sync(ngrok_url)
        else:
            logger.warning("Ngrok API not responding. Ensure Ngrok is running locally.")
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()