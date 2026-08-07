import sqlite3
import json
import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

class HopperDatabase:
    def __init__(self, db_path: Path, logger):
        self.db_path = db_path
        self.logger = logger
        self.init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS advanced_hoppers (
                        hopper_key TEXT PRIMARY KEY,
                        owner_uuid TEXT,
                        owner_name TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        enabled INTEGER NOT NULL,
                        mode TEXT NOT NULL,
                        horizontal_range INTEGER NOT NULL,
                        vertical_up INTEGER NOT NULL,
                        vertical_down INTEGER NOT NULL,
                        max_items_moved_per_scan INTEGER,
                        max_stacks_moved_per_scan INTEGER,
                        linked_storage TEXT,
                        filters TEXT,
                        stats TEXT
                    )
                """)
                conn.commit()
            self.logger.info("Hopper Database initialized successfully.")
        except Exception as e:
            self.logger.error(f"Failed to initialize hopper database: {e}")

    def get_hopper(self, hopper_key: str) -> Optional[Dict[str, Any]]:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM advanced_hoppers WHERE hopper_key = ?", (hopper_key,))
                row = cursor.fetchone()
                if row:
                    res = dict(row)
                    res["enabled"] = bool(res["enabled"])
                    res["linked_storage"] = json.loads(res["linked_storage"]) if res["linked_storage"] else None
                    res["filters"] = json.loads(res["filters"]) if res["filters"] else {}
                    res["stats"] = json.loads(res["stats"]) if res["stats"] else {}
                    return res
        except Exception as e:
            self.logger.error(f"Error reading hopper {hopper_key}: {e}")
        return None

    def save_hopper(self, hopper_key: str, data: Dict[str, Any]):
        now = datetime.datetime.now().isoformat()
        enabled_int = 1 if data.get("enabled", True) else 0
        linked_storage_json = json.dumps(data.get("linked_storage"))
        filters_json = json.dumps(data.get("filters", {}))
        stats_json = json.dumps(data.get("stats", {}))
        
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO advanced_hoppers (
                        hopper_key, owner_uuid, owner_name, created_at, updated_at, enabled, mode,
                        horizontal_range, vertical_up, vertical_down, max_items_moved_per_scan,
                        max_stacks_moved_per_scan, linked_storage, filters, stats
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(hopper_key) DO UPDATE SET
                        owner_uuid = excluded.owner_uuid,
                        owner_name = excluded.owner_name,
                        updated_at = excluded.updated_at,
                        enabled = excluded.enabled,
                        mode = excluded.mode,
                        horizontal_range = excluded.horizontal_range,
                        vertical_up = excluded.vertical_up,
                        vertical_down = excluded.vertical_down,
                        max_items_moved_per_scan = excluded.max_items_moved_per_scan,
                        max_stacks_moved_per_scan = excluded.max_stacks_moved_per_scan,
                        linked_storage = excluded.linked_storage,
                        filters = excluded.filters,
                        stats = excluded.stats
                """, (
                    hopper_key,
                    data.get("owner_uuid"),
                    data.get("owner_name"),
                    data.get("created_at", now),
                    now,
                    enabled_int,
                    data.get("mode", "whitelist"),
                    data.get("horizontal_range", 8),
                    data.get("vertical_up", 4),
                    data.get("vertical_down", 4),
                    data.get("max_items_moved_per_scan", 8),
                    data.get("max_stacks_moved_per_scan", 3),
                    linked_storage_json,
                    filters_json,
                    stats_json
                ))
                conn.commit()
        except Exception as e:
            self.logger.error(f"Error saving hopper {hopper_key}: {e}")

    def delete_hopper(self, hopper_key: str) -> bool:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM advanced_hoppers WHERE hopper_key = ?", (hopper_key,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            self.logger.error(f"Error deleting hopper {hopper_key}: {e}")
        return False

    def list_hoppers(self) -> List[Dict[str, Any]]:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM advanced_hoppers")
                result = []
                for row in cursor.fetchall():
                    res = dict(row)
                    res["enabled"] = bool(res["enabled"])
                    res["linked_storage"] = json.loads(res["linked_storage"]) if res["linked_storage"] else None
                    res["filters"] = json.loads(res["filters"]) if res["filters"] else {}
                    res["stats"] = json.loads(res["stats"]) if res["stats"] else {}
                    result.append(res)
                return result
        except Exception as e:
            self.logger.error(f"Error listing hoppers: {e}")
        return []

    def count_hoppers_in_chunk(self, dimension: str, chunk_x: int, chunk_z: int) -> int:
        try:
            count = 0
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT hopper_key FROM advanced_hoppers")
                for row in cursor.fetchall():
                    key = row["hopper_key"]
                    parts = key.split(":")
                    if len(parts) >= 5 and parts[1] == dimension:
                        try:
                            x = int(parts[2])
                            z = int(parts[4])
                            if (x >> 4) == chunk_x and (z >> 4) == chunk_z:
                                count += 1
                        except ValueError:
                            continue
            return count
        except Exception as e:
            self.logger.error(f"Error counting hoppers in chunk: {e}")
        return 0

    def count_hoppers_by_owner(self, owner_uuid: str) -> int:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM advanced_hoppers WHERE owner_uuid = ?", (owner_uuid,))
                row = cursor.fetchone()
                return row[0] if row else 0
        except Exception as e:
            self.logger.error(f"Error counting hoppers by owner: {e}")
        return 0
