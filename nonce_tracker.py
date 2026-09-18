import hashlib
import time
import aiosqlite
from typing import Optional, Tuple

DB_PATH = "storage/nonce_tracker.db"

class NonceTracker:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    async def init_db(self):
        """Creates tables for replay tracking and pending settlement queues."""
        async with aiosqlite.connect(self.db_path) as db:
            # Replay protection table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS used_signatures (
                    signature_hash TEXT PRIMARY KEY,
                    payer_address TEXT,
                    nonce TEXT,
                    timestamp REAL
                )
            """)
            # On-chain settlement queue table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS pending_settlements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payment_header TEXT UNIQUE,
                    payer TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()

    @staticmethod
    def compute_hash(signature_b64: str) -> str:
        """Generates SHA-256 hash of the raw Base64 payment payload."""
        return hashlib.sha256(signature_b64.encode("utf-8")).hexdigest()

    async def check_and_record(
        self, signature_b64: str, payer: str, nonce: str, valid_before: Optional[int] = None
    ) -> Tuple[bool, str]:
        """Validates payload timestamps and checks SQLite for signature reuse."""
        now = time.time()
        if valid_before and valid_before > 0 and now > valid_before:
            return False, "Payment signature has expired (validBefore limit reached)"

        sig_hash = self.compute_hash(signature_b64)

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT timestamp FROM used_signatures WHERE signature_hash = ?", (sig_hash,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return False, f"Replay attack detected: Signature consumed at timestamp {row[0]}"

            await db.execute(
                "INSERT INTO used_signatures (signature_hash, payer_address, nonce, timestamp) VALUES (?, ?, ?, ?)",
                (sig_hash, payer, str(nonce), now)
            )
            await db.commit()

        return True, "Signature accepted"

    async def queue_settlement(self, payment_header: str, payer: str):
        """Helper method to queue verified payment signatures for background worker processing."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO pending_settlements (payment_header, payer) VALUES (?, ?)",
                (payment_header, payer)
            )
            await db.commit()

    async def purge_old_nonces(self, max_age_seconds: int = 86400):
        """Housekeeping background job to clean up signatures older than 24h."""
        cutoff = time.time() - max_age_seconds
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM used_signatures WHERE timestamp < ?", (cutoff,))
            await db.commit()

nonce_db = NonceTracker()