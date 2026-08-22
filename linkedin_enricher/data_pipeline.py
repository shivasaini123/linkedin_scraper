import csv
import logging
import os
import sqlite3
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("DataPipeline")

class DataPipeline:
    """
    SQLite-Backed Asynchronous Work Queue and Data Checkpoint Manager.
    Guarantees state persistence, crash resilience, and pause/resume capability for 1M records.
    """

    def __init__(self, db_path: str = "checkpoint_queue.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS enrichment_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    orig_company TEXT DEFAULT '',
                    city TEXT DEFAULT 'Seattle',
                    state TEXT DEFAULT 'Washington',
                    current_company TEXT DEFAULT '',
                    profile_url TEXT DEFAULT '',
                    status TEXT DEFAULT 'pending',
                    attempts INTEGER DEFAULT 0,
                    error TEXT DEFAULT '',
                    created_at REAL,
                    updated_at REAL,
                    UNIQUE(username, city, state)
                )
            """)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON enrichment_queue(status)")
            # Automatically recover any jobs left in 'processing' state from previous interrupted runs
            conn.execute("UPDATE enrichment_queue SET status = 'pending' WHERE status = 'processing'")
            conn.commit()


    def import_csv(self, csv_path: str, default_state: str = "Washington") -> int:
        """Imports dataset CSV into SQLite queue, ignoring duplicate records."""
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Input CSV file not found: {csv_path}")

        imported_count = 0
        now = time.time()

        with open(csv_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            # Normalize fieldnames
            headers = [h.strip().lower() for h in reader.fieldnames] if reader.fieldnames else []
            
            # Map column names
            name_key = next((h for h in reader.fieldnames if h.strip().lower() in ["username", "contact", "name", "full_name", "user"]), None)
            city_key = next((h for h in reader.fieldnames if h.strip().lower() in ["city", "location", "town"]), None)
            comp_key = next((h for h in reader.fieldnames if h.strip().lower() in ["company", "past_company", "organization"]), None)

            if not name_key:
                raise ValueError(f"Could not identify Name/Username column in CSV. Headers found: {reader.fieldnames}")

            records_to_insert = []
            for row in reader:
                uname = row.get(name_key, "").strip()
                if not uname:
                    continue
                city = row.get(city_key, "").strip() if city_key else "Seattle"
                if not city:
                    city = "Seattle"
                orig_comp = row.get(comp_key, "").strip() if comp_key else ""
                records_to_insert.append((uname, orig_comp, city, default_state, "pending", 0, now, now))

        with self._get_connection() as conn:
            cursor = conn.executemany("""
                INSERT OR IGNORE INTO enrichment_queue 
                (username, orig_company, city, state, status, attempts, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, records_to_insert)
            conn.commit()
            imported_count = cursor.rowcount

        logger.info(f"Imported {imported_count} new records into queue database.")
        return imported_count

    def get_pending_batch(self, limit: int = 50) -> List[Dict]:
        """Fetches pending items for async processing workers."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT id, username, orig_company, city, state, attempts 
                FROM enrichment_queue 
                WHERE status = 'pending' 
                ORDER BY id ASC 
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def mark_processing(self, item_ids: List[int]):
        """Marks items as currently being processed."""
        if not item_ids:
            return
        now = time.time()
        placeholders = ",".join(["?"] * len(item_ids))
        with self._get_connection() as conn:
            conn.execute(f"""
                UPDATE enrichment_queue 
                SET status = 'processing', attempts = attempts + 1, updated_at = ? 
                WHERE id IN ({placeholders})
            """, [now] + item_ids)
            conn.commit()

    def update_result(self, item_id: int, company: Optional[str], profile_url: Optional[str], status: str, error: str = ""):
        """Atomically updates enrichment results in SQLite database."""
        now = time.time()
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE enrichment_queue 
                SET current_company = ?, profile_url = ?, status = ?, error = ?, updated_at = ? 
                WHERE id = ?
            """, (company or "Not Found", profile_url or "", status, error, now, item_id))
            conn.commit()

    def export_to_csv(self, output_csv_path: str) -> int:
        """Exports all completed enriched data from SQLite queue to final CSV."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT username, orig_company, city, state, current_company, profile_url, status, updated_at 
                FROM enrichment_queue
                ORDER BY id ASC
            """)
            rows = cursor.fetchall()

        target_path = output_csv_path
        try:
            f = open(target_path, mode="w", newline="", encoding="utf-8")
        except PermissionError:
            # If target file is open in Excel, generate timestamped fallback filename
            base, ext = os.path.splitext(output_csv_path)
            target_path = f"{base}_latest{ext}"
            f = open(target_path, mode="w", newline="", encoding="utf-8")

        with f:
            writer = csv.writer(f)
            writer.writerow(["Username/Contact", "Original Input Company", "City", "State", "Enriched Current Company", "LinkedIn Profile URL", "Enrichment Status"])
            count = 0
            for r in rows:
                writer.writerow([r["username"], r["orig_company"], r["city"], r["state"], r["current_company"], r["profile_url"], r["status"]])
                count += 1

        logger.info(f"Exported {count} records to {target_path}")
        return count



    def get_statistics(self) -> Dict[str, int]:
        """Returns total, completed, pending, processing, and failed item counts."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT status, COUNT(*) as count FROM enrichment_queue GROUP BY status
            """)
            stats = {row["status"]: row["count"] for row in cursor.fetchall()}
            
            total_cursor = conn.execute("SELECT COUNT(*) as total FROM enrichment_queue")
            total = total_cursor.fetchone()["total"]

            return {
                "total": total,
                "pending": stats.get("pending", 0),
                "processing": stats.get("processing", 0),
                "completed": stats.get("completed", 0),
                "failed": stats.get("failed", 0)
            }

    def reset_queue(self):
        """Clears SQLite database table for fresh start."""
        with self._get_connection() as conn:
            conn.execute("DROP TABLE IF EXISTS enrichment_queue")
            conn.commit()
        self._init_db()

