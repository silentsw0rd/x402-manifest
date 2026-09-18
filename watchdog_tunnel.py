import re
import sys
import time
import subprocess
import threading

SERVER_CMD = [sys.executable, "server.py"]
CLOUDFLARED_CMD = ["cloudflared", "tunnel", "--url", "http://localhost:8000"]

URL_REGEX = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")

class TunnelWatchdog:
    def __init__(self):
        self.server_proc = None
        self.tunnel_proc = None
        self.public_url = None
        self.running = True

    def start_server(self):
        print("[+] Starting FastAPI server (server.py)...")
        self.server_proc = subprocess.Popen(
            SERVER_CMD,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        threading.Thread(target=self._read_stream, args=(self.server_proc, "[SERVER]"), daemon=True).start()

    def start_tunnel(self):
        print("[+] Launching Cloudflare Tunnel...")
        self.tunnel_proc = subprocess.Popen(
            CLOUDFLARED_CMD,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        threading.Thread(target=self._monitor_tunnel_output, args=(self.tunnel_proc,), daemon=True).start()

    def _read_stream(self, proc, prefix):
        for line in iter(proc.stdout.readline, ''):
            if line:
                print(f"{prefix} {line.strip()}")

    def _monitor_tunnel_output(self, proc):
        for line in iter(proc.stdout.readline, ''):
            if not line:
                break
            clean_line = line.strip()
            match = URL_REGEX.search(clean_line)
            if match and not self.public_url:
                self.public_url = match.group(0)
                print("\n" + "=" * 60)
                print(f"🚀 LIVE CLOUDFLARE PUBLIC TUNNEL URL:")
                print(f"   {self.public_url}")
                print(f"   x402 Spec: {self.public_url}/.well-known/x402.json")
                print(f"   Extract API: {self.public_url}/api/v1/extract")
                print("=" * 60 + "\n")
            # Print cloudflared diagnostic lines selectively
            if "INF" in clean_line or "ERR" in clean_line:
                print(f"[TUNNEL] {clean_line}")

    def monitor(self):
        self.start_server()
        time.sleep(2)  # Give server time to bind port
        self.start_tunnel()

        try:
            while self.running:
                time.sleep(3)

                # Check server health
                if self.server_proc and self.server_proc.poll() is not None:
                    print("[!] Server crashed. Restarting...")
                    self.start_server()

                # Check tunnel health
                if self.tunnel_proc and self.tunnel_proc.poll() is not None:
                    print("[!] Cloudflare Tunnel disconnected. Restarting...")
                    self.public_url = None
                    self.start_tunnel()

        except KeyboardInterrupt:
            print("\n[-] Shutting down watchdog processes...")
            self.stop()

    def stop(self):
        self.running = False
        if self.tunnel_proc:
            self.tunnel_proc.terminate()
        if self.server_proc:
            self.server_proc.terminate()
        print("[+] Watchdog stopped cleanly.")

if __name__ == "__main__":
    watchdog = TunnelWatchdog()
    watchdog.monitor()