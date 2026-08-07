import sqlite3
import json
import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

try:
    import pymysql
except ImportError:
    pymysql = None

@dataclass
class User:
    xuid: str
    name: str
    last_join: int
    last_leave: int

class Database:
    MYSQL_CHARSET = "utf8mb4"
    MYSQL_COLLATION = "utf8mb4_unicode_ci"
    MYSQL_TABLES = (
        "item_backpacks",
        "users",
        "inventories_v2",
        "ender_chests_v2",
    )

    def __init__(self, db_path: Path, logger, mysql_config: Optional[dict] = None):
        self.db_path = db_path
        self.logger = logger
        self.mysql_config = mysql_config or {"enabled": False}
        self.use_mysql = self.mysql_config.get("enabled", False)
        
        if self.use_mysql and pymysql is None:
            self.logger.error("MySQL is enabled in configuration, but 'pymysql' package is not installed! Falling back to SQLite.")
            self.use_mysql = False

        self.init_db()

    def _get_connection(self):
        if self.use_mysql:
            return pymysql.connect(
                host=self.mysql_config.get("host", "localhost"),
                port=int(self.mysql_config.get("port", 3306)),
                user=self.mysql_config.get("user", "root"),
                password=self.mysql_config.get("password", ""),
                database=self.mysql_config.get("database", "player_data"),
                charset=self.MYSQL_CHARSET,
                use_unicode=True,
                cursorclass=pymysql.cursors.DictCursor
            )
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn

    def init_db(self):
        """Initialize database tables for item backpacks and inventories."""
        if not self.use_mysql:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            
        try:
            if self.use_mysql:
                conn = self._get_connection()
                try:
                    with conn.cursor() as cursor:
                        cursor.execute("""
                            CREATE TABLE IF NOT EXISTS item_backpacks (
                                backpack_id VARCHAR(128) PRIMARY KEY,
                                type VARCHAR(64) NOT NULL,
                                size INT NOT NULL,
                                owner_uuid VARCHAR(64),
                                owner_name VARCHAR(64),
                                created_at VARCHAR(64) NOT NULL,
                                updated_at VARCHAR(64) NOT NULL,
                                contents MEDIUMTEXT NOT NULL
                            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                        """)
                        cursor.execute("""
                            CREATE TABLE IF NOT EXISTS users (
                                xuid VARCHAR(64) PRIMARY KEY,
                                name VARCHAR(64) NOT NULL,
                                last_join INT DEFAULT 0,
                                last_leave INT DEFAULT 0
                            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                        """)
                        cursor.execute("""
                            CREATE TABLE IF NOT EXISTS inventories_v2 (
                                xuid VARCHAR(64) PRIMARY KEY,
                                name VARCHAR(64) NOT NULL,
                                items_json MEDIUMTEXT NOT NULL
                            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                        """)
                        cursor.execute("""
                            CREATE TABLE IF NOT EXISTS ender_chests_v2 (
                                xuid VARCHAR(64) PRIMARY KEY,
                                name VARCHAR(64) NOT NULL,
                                items_json MEDIUMTEXT NOT NULL
                            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                        """)
                        try:
                            self._upgrade_mysql_charset(cursor)
                        except Exception as charset_error:
                            # JSON writes are ASCII-escaped as a safe fallback, but
                            # upgrading the schema is still preferred for names and
                            # any direct SQL consumers of these tables.
                            self.logger.warning(
                                "Could not automatically upgrade existing MySQL "
                                f"tables to utf8mb4: {charset_error}"
                            )
                    conn.commit()
                finally:
                    conn.close()
                self.logger.info("MySQL database initialized successfully.")
                
                # Run automatic SQLite to MySQL migration helper
                self.migrate_sqlite_to_mysql()
            else:
                with self._get_connection() as conn:
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS item_backpacks (
                            backpack_id TEXT PRIMARY KEY,
                            type TEXT NOT NULL,
                            size INTEGER NOT NULL,
                            owner_uuid TEXT,
                            owner_name TEXT,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            contents TEXT NOT NULL
                        )
                    """)
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS users (
                            xuid TEXT PRIMARY KEY,
                            name TEXT NOT NULL,
                            last_join INTEGER DEFAULT 0,
                            last_leave INTEGER DEFAULT 0
                        )
                    """)
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS inventories_v2 (
                            xuid TEXT PRIMARY KEY,
                            name TEXT NOT NULL,
                            items_json TEXT NOT NULL
                        )
                    """)
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS ender_chests_v2 (
                            xuid TEXT PRIMARY KEY,
                            name TEXT NOT NULL,
                            items_json TEXT NOT NULL
                        )
                    """)
                    conn.commit()
                self.logger.info("SQLite database initialized successfully.")
        except Exception as e:
            self.logger.error(f"Failed to initialize database: {e}")

    def _upgrade_mysql_charset(self, cursor) -> None:
        """Upgrade pre-existing MySQL tables that inherited a legacy charset."""
        placeholders = ", ".join(["%s"] * len(self.MYSQL_TABLES))
        cursor.execute(
            f"""
                SELECT DISTINCT t.TABLE_NAME AS table_name
                FROM information_schema.TABLES AS t
                LEFT JOIN information_schema.COLUMNS AS c
                    ON c.TABLE_SCHEMA = t.TABLE_SCHEMA
                    AND c.TABLE_NAME = t.TABLE_NAME
                WHERE t.TABLE_SCHEMA = %s
                    AND t.TABLE_NAME IN ({placeholders})
                    AND (
                        t.TABLE_COLLATION NOT LIKE 'utf8mb4%%'
                        OR (
                            c.CHARACTER_SET_NAME IS NOT NULL
                            AND c.CHARACTER_SET_NAME <> %s
                        )
                    )
            """,
            (
                self.mysql_config.get("database", "player_data"),
                *self.MYSQL_TABLES,
                self.MYSQL_CHARSET,
            ),
        )
        tables_to_upgrade = {row["table_name"] for row in cursor.fetchall()}
        for table_name in sorted(tables_to_upgrade):
            # table_name can only originate from the constant allow-list above.
            cursor.execute(
                f"ALTER TABLE `{table_name}` CONVERT TO CHARACTER SET "
                f"{self.MYSQL_CHARSET} COLLATE {self.MYSQL_COLLATION}"
            )

        if tables_to_upgrade:
            self.logger.info(
                "Upgraded MySQL text storage to utf8mb4 for: "
                + ", ".join(sorted(tables_to_upgrade))
            )

    def migrate_sqlite_to_mysql(self):
        """Migrates all records from local SQLite to the MySQL database if local DB exists."""
        if not self.db_path.exists():
            return

        self.logger.info(f"Local SQLite database file '{self.db_path.name}' found. Starting migration to MySQL...")
        
        try:
            # 1. Connect to SQLite
            sqlite_conn = sqlite3.connect(self.db_path)
            sqlite_conn.row_factory = sqlite3.Row
            
            # 2. Connect to MySQL
            mysql_conn = self._get_connection()
            
            try:
                # Migrate users
                sqlite_cursor = sqlite_conn.cursor()
                sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
                if sqlite_cursor.fetchone():
                    sqlite_cursor.execute("SELECT * FROM users")
                    rows = sqlite_cursor.fetchall()
                    if rows:
                        self.logger.info(f"Migrating {len(rows)} user records to MySQL...")
                        with mysql_conn.cursor() as mysql_cursor:
                            mysql_cursor.executemany("""
                                INSERT INTO users (xuid, name, last_join, last_leave)
                                VALUES (%s, %s, %s, %s)
                                ON DUPLICATE KEY UPDATE
                                    name = VALUES(name),
                                    last_join = VALUES(last_join),
                                    last_leave = VALUES(last_leave)
                            """, [(r["xuid"], r["name"], r["last_join"], r["last_leave"]) for r in rows])
                        mysql_conn.commit()

                # Migrate item_backpacks
                sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='item_backpacks'")
                if sqlite_cursor.fetchone():
                    sqlite_cursor.execute("SELECT * FROM item_backpacks")
                    rows = sqlite_cursor.fetchall()
                    if rows:
                        self.logger.info(f"Migrating {len(rows)} item backpack records to MySQL...")
                        with mysql_conn.cursor() as mysql_cursor:
                            mysql_cursor.executemany("""
                                INSERT INTO item_backpacks (backpack_id, type, size, owner_uuid, owner_name, created_at, updated_at, contents)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                                ON DUPLICATE KEY UPDATE
                                    owner_uuid = VALUES(owner_uuid),
                                    owner_name = VALUES(owner_name),
                                    updated_at = VALUES(updated_at),
                                    contents = VALUES(contents)
                            """, [(r["backpack_id"], r["type"], r["size"], r["owner_uuid"], r["owner_name"], r["created_at"], r["updated_at"], r["contents"]) for r in rows])
                        mysql_conn.commit()

                # Migrate inventories_v2
                sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inventories_v2'")
                if sqlite_cursor.fetchone():
                    sqlite_cursor.execute("SELECT * FROM inventories_v2")
                    rows = sqlite_cursor.fetchall()
                    if rows:
                        self.logger.info(f"Migrating {len(rows)} player inventory records to MySQL...")
                        with mysql_conn.cursor() as mysql_cursor:
                            mysql_cursor.executemany("""
                                INSERT INTO inventories_v2 (xuid, name, items_json)
                                VALUES (%s, %s, %s)
                                ON DUPLICATE KEY UPDATE
                                    name = VALUES(name),
                                    items_json = VALUES(items_json)
                            """, [(r["xuid"], r["name"], r["items_json"]) for r in rows])
                        mysql_conn.commit()

                # Migrate ender_chests_v2
                sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ender_chests_v2'")
                if sqlite_cursor.fetchone():
                    sqlite_cursor.execute("SELECT * FROM ender_chests_v2")
                    rows = sqlite_cursor.fetchall()
                    if rows:
                        self.logger.info(f"Migrating {len(rows)} ender chest records to MySQL...")
                        with mysql_conn.cursor() as mysql_cursor:
                            mysql_cursor.executemany("""
                                INSERT INTO ender_chests_v2 (xuid, name, items_json)
                                VALUES (%s, %s, %s)
                                ON DUPLICATE KEY UPDATE
                                    name = VALUES(name),
                                    items_json = VALUES(items_json)
                            """, [(r["xuid"], r["name"], r["items_json"]) for r in rows])
                        mysql_conn.commit()

                self.logger.info("SQLite to MySQL data migration completed successfully.")
            
            finally:
                sqlite_conn.close()
                mysql_conn.close()

            # Rename SQLite file to prevent running migration again
            backup_path = self.db_path.with_suffix(".db.migrated")
            try:
                if backup_path.exists():
                    backup_path.unlink()
                self.db_path.rename(backup_path)
                self.logger.info(f"Local SQLite database has been safely renamed to '{backup_path.name}'.")
            except Exception as backup_err:
                self.logger.error(f"Failed to rename SQLite database: {backup_err}")
                
        except Exception as e:
            self.logger.error(f"Data migration failed: {e}")

    def get_item_backpack(self, backpack_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve item backpack record from DB."""
        placeholder = "%s" if self.use_mysql else "?"
        query = f"SELECT * FROM item_backpacks WHERE backpack_id = {placeholder}"
        try:
            if self.use_mysql:
                conn = self._get_connection()
                try:
                    with conn.cursor() as cursor:
                        cursor.execute(query, (backpack_id,))
                        row = cursor.fetchone()
                        if row:
                            res = dict(row)
                            res["contents"] = json.loads(res["contents"])
                            return res
                finally:
                    conn.close()
            else:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, (backpack_id,))
                    row = cursor.fetchone()
                    if row:
                        res = dict(row)
                        res["contents"] = json.loads(res["contents"])
                        return res
        except Exception as e:
            self.logger.error(f"Error reading item backpack {backpack_id}: {e}")
        return None

    def save_item_backpack(self, backpack_id: str, bp_type: str, size: int, owner_uuid: Optional[str], owner_name: Optional[str], contents: Dict[str, Any]):
        """Save/upsert item backpack contents and metadata."""
        now = datetime.datetime.now().isoformat()
        contents_json = json.dumps(contents)
        if self.use_mysql:
            query = """
                INSERT INTO item_backpacks (backpack_id, type, size, owner_uuid, owner_name, created_at, updated_at, contents)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    type = VALUES(type),
                    size = VALUES(size),
                    owner_uuid = VALUES(owner_uuid),
                    owner_name = VALUES(owner_name),
                    updated_at = VALUES(updated_at),
                    contents = VALUES(contents)
            """
            try:
                conn = self._get_connection()
                try:
                    with conn.cursor() as cursor:
                        cursor.execute(query, (backpack_id, bp_type, size, owner_uuid, owner_name, now, now, contents_json))
                    conn.commit()
                finally:
                    conn.close()
            except Exception as e:
                self.logger.error(f"Error saving item backpack {backpack_id} to MySQL: {e}")
        else:
            query = """
                INSERT INTO item_backpacks (backpack_id, type, size, owner_uuid, owner_name, created_at, updated_at, contents)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(backpack_id) DO UPDATE SET
                    type = excluded.type,
                    size = excluded.size,
                    owner_uuid = excluded.owner_uuid,
                    owner_name = excluded.owner_name,
                    updated_at = excluded.updated_at,
                    contents = excluded.contents
            """
            try:
                with self._get_connection() as conn:
                    conn.execute(query, (backpack_id, bp_type, size, owner_uuid, owner_name, now, now, contents_json))
                    conn.commit()
            except Exception as e:
                self.logger.error(f"Error saving item backpack {backpack_id} to SQLite: {e}")

    def update_backpack_sizes(self, tier_sizes: Dict[str, int]) -> None:
        """Updates the size of registered backpacks of the given types to match current config sizes."""
        if not tier_sizes:
            return
        
        for bp_type, new_size in tier_sizes.items():
            placeholder = "%s" if self.use_mysql else "?"
            query = f"UPDATE item_backpacks SET size = {placeholder} WHERE type = {placeholder}"
            try:
                if self.use_mysql:
                    conn = self._get_connection()
                    try:
                        with conn.cursor() as cursor:
                            cursor.execute(query, (new_size, bp_type))
                        conn.commit()
                    finally:
                        conn.close()
                else:
                    with self._get_connection() as conn:
                        conn.execute(query, (new_size, bp_type))
                        conn.commit()
            except Exception as e:
                self.logger.error(f"Error updating size to {new_size} for type {bp_type}: {e}")

    def list_item_backpacks(self) -> List[Dict[str, Any]]:
        """List all item backpacks in DB."""
        query = "SELECT * FROM item_backpacks"
        try:
            if self.use_mysql:
                conn = self._get_connection()
                try:
                    with conn.cursor() as cursor:
                        cursor.execute(query)
                        return [dict(r) for r in cursor.fetchall()]
                finally:
                    conn.close()
            else:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query)
                    return [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"Error listing item backpacks: {e}")
        return []

    def cleanup_orphaned_backpacks(self) -> int:
        """Cleanup any empty item backpacks older than 30 days."""
        now = datetime.datetime.now()
        deleted_count = 0
        placeholder = "%s" if self.use_mysql else "?"
        try:
            if self.use_mysql:
                conn = self._get_connection()
                try:
                    with conn.cursor() as cursor:
                        cursor.execute("SELECT backpack_id, contents, updated_at FROM item_backpacks")
                        rows = cursor.fetchall()
                        for row in rows:
                            contents = json.loads(row["contents"])
                            is_empty = True
                            for k, v in contents.items():
                                if v is not None and v.get("type") is not None:
                                    is_empty = False
                                    break
                            if is_empty:
                                updated_at = datetime.datetime.fromisoformat(row["updated_at"])
                                if (now - updated_at).days > 30:
                                    cursor.execute(f"DELETE FROM item_backpacks WHERE backpack_id = {placeholder}", (row["backpack_id"],))
                                    deleted_count += 1
                    conn.commit()
                finally:
                    conn.close()
            else:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT backpack_id, contents, updated_at FROM item_backpacks")
                    for row in cursor.fetchall():
                        contents = json.loads(row["contents"])
                        is_empty = True
                        for k, v in contents.items():
                            if v is not None and v.get("type") is not None:
                                    is_empty = False
                                    break
                        if is_empty:
                            updated_at = datetime.datetime.fromisoformat(row["updated_at"])
                            if (now - updated_at).days > 30:
                                conn.execute(f"DELETE FROM item_backpacks WHERE backpack_id = {placeholder}", (row["backpack_id"],))
                                deleted_count += 1
                    conn.commit()
        except Exception as e:
            self.logger.error(f"Error running database cleanup: {e}")
        return deleted_count

    def delete_item_backpack(self, backpack_id: str) -> bool:
        """Deletes a backpack record from the database. Returns True if deleted successfully."""
        placeholder = "%s" if self.use_mysql else "?"
        query = f"DELETE FROM item_backpacks WHERE backpack_id = {placeholder}"
        try:
            if self.use_mysql:
                conn = self._get_connection()
                try:
                    with conn.cursor() as cursor:
                        cursor.execute(query, (backpack_id,))
                        rowcount = cursor.rowcount
                    conn.commit()
                    return rowcount > 0
                finally:
                    conn.close()
            else:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, (backpack_id,))
                    conn.commit()
                    return cursor.rowcount > 0
        except Exception as e:
            self.logger.error(f"Error deleting item backpack {backpack_id}: {e}")
        return False

    def save_user(self, player, join_time: int):
        if self.use_mysql:
            query = """
                INSERT INTO users (xuid, name, last_join)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    name = VALUES(name),
                    last_join = VALUES(last_join)
            """
            try:
                conn = self._get_connection()
                try:
                    with conn.cursor() as cursor:
                        cursor.execute(query, (player.xuid, player.name, join_time))
                    conn.commit()
                finally:
                    conn.close()
            except Exception as e:
                self.logger.error(f"Error saving user {player.name} to MySQL: {e}")
        else:
            query = """
                INSERT INTO users (xuid, name, last_join)
                VALUES (?, ?, ?)
                ON CONFLICT(xuid) DO UPDATE SET
                    name = excluded.name,
                    last_join = excluded.last_join
            """
            try:
                with self._get_connection() as conn:
                    conn.execute(query, (player.xuid, player.name, join_time))
                    conn.commit()
            except Exception as e:
                self.logger.error(f"Error saving user {player.name} to SQLite: {e}")

    def update_user_leave_time(self, xuid: str, leave_time: int):
        placeholder = "%s" if self.use_mysql else "?"
        query = f"UPDATE users SET last_leave = {placeholder} WHERE xuid = {placeholder}"
        try:
            if self.use_mysql:
                conn = self._get_connection()
                try:
                    with conn.cursor() as cursor:
                        cursor.execute(query, (leave_time, xuid))
                    conn.commit()
                finally:
                    conn.close()
            else:
                with self._get_connection() as conn:
                    conn.execute(query, (leave_time, xuid))
                    conn.commit()
        except Exception as e:
            self.logger.error(f"Error updating leave time for {xuid}: {e}")

    def search_users_by_name(self, name_query: str) -> List[User]:
        placeholder = "%s" if self.use_mysql else "?"
        query = f"SELECT xuid, name, last_join, last_leave FROM users WHERE name LIKE {placeholder}"
        try:
            if self.use_mysql:
                conn = self._get_connection()
                try:
                    with conn.cursor() as cursor:
                        cursor.execute(query, (f"%{name_query}%",))
                        users = []
                        for row in cursor.fetchall():
                            users.append(User(xuid=row["xuid"], name=row["name"], last_join=row["last_join"], last_leave=row["last_leave"]))
                        return users
                finally:
                    conn.close()
            else:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, (f"%{name_query}%",))
                    users = []
                    for row in cursor.fetchall():
                        users.append(User(xuid=row[0], name=row[1], last_join=row[2], last_leave=row[3]))
                    return users
        except Exception as e:
            self.logger.error(f"Error searching users by name {name_query}: {e}")
            return []

    @staticmethod
    def _encode_items_json(items: List[Dict[str, Any]]) -> str:
        """Encode lossless JSON that is safe even on a legacy MySQL text column."""
        return json.dumps(items, ensure_ascii=True, separators=(",", ":"))

    def _save_player_items(
        self,
        table_name: str,
        storage_label: str,
        xuid: str,
        player_name: str,
        items: List[Dict[str, Any]],
    ) -> bool:
        if table_name not in {"inventories_v2", "ender_chests_v2"}:
            raise ValueError(f"Unsupported player storage table: {table_name}")

        items_json = self._encode_items_json(items)
        try:
            if self.use_mysql:
                query = f"""
                    INSERT INTO {table_name} (xuid, name, items_json)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        name = VALUES(name),
                        items_json = VALUES(items_json)
                """
                conn = self._get_connection()
                try:
                    with conn.cursor() as cursor:
                        cursor.execute(query, (xuid, player_name, items_json))
                    conn.commit()
                finally:
                    conn.close()
            else:
                query = f"""
                    INSERT INTO {table_name} (xuid, name, items_json)
                    VALUES (?, ?, ?)
                    ON CONFLICT(xuid) DO UPDATE SET
                        name = excluded.name,
                        items_json = excluded.items_json
                """
                with self._get_connection() as conn:
                    conn.execute(query, (xuid, player_name, items_json))
                    conn.commit()
            return True
        except Exception as e:
            backend = "MySQL" if self.use_mysql else "SQLite"
            self.logger.error(
                f"Error saving {storage_label} for {player_name} to {backend}: {e}"
            )
            return False

    def save_inventory_items(
        self, xuid: str, player_name: str, items: List[Dict[str, Any]]
    ) -> bool:
        """Save already-serialized inventory items for online or offline players."""
        return self._save_player_items(
            "inventories_v2", "inventory", xuid, player_name, items
        )

    def save_enderchest_items(
        self, xuid: str, player_name: str, items: List[Dict[str, Any]]
    ) -> bool:
        """Save already-serialized Ender Chest items for any player."""
        return self._save_player_items(
            "ender_chests_v2", "ender chest", xuid, player_name, items
        )

    def save_inventory(self, player) -> bool:
        items = []

        # Main inventory slots
        for i in range(player.inventory.size):
            items.append(self._serialize_db_item(player.inventory.get_item(i), i, "slot"))

        # Armor slots
        armor_map = {
            "helmet": -1,
            "chestplate": -2,
            "leggings": -3,
            "boots": -4,
            "item_in_off_hand": -5,
        }
        for attr_name, slot_num in armor_map.items():
            item = getattr(player.inventory, attr_name, None)
            items.append(self._serialize_db_item(item, slot_num, attr_name))

        return self.save_inventory_items(player.xuid, player.name, items)

    def _serialize_db_item(self, item, slot_num: int, slot_type: str = "slot") -> dict:
        from ninjos_backpacks.serializer import serialize_item
        if item is None or str(item.type) == "minecraft:air":
            return {"slot": slot_num, "slot_type": slot_type, "type": None}
        
        serialized = serialize_item(item)
        if serialized is None:
            return {"slot": slot_num, "slot_type": slot_type, "type": None}
            
        serialized["slot"] = slot_num
        serialized["slot_type"] = slot_type
        return serialized

    def get_inventory(self, xuid: str) -> List[Dict[str, Any]]:
        placeholder = "%s" if self.use_mysql else "?"
        query = f"SELECT items_json FROM inventories_v2 WHERE xuid = {placeholder}"
        try:
            if self.use_mysql:
                conn = self._get_connection()
                try:
                    with conn.cursor() as cursor:
                        cursor.execute(query, (xuid,))
                        row = cursor.fetchone()
                        if not row or not row["items_json"]:
                            return []
                        items = json.loads(row["items_json"])
                        return [item for item in items if item.get("type") is not None]
                finally:
                    conn.close()
            else:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, (xuid,))
                    row = cursor.fetchone()
                    if not row or not row[0]:
                        return []
                    items = json.loads(row[0])
                    return [item for item in items if item.get("type") is not None]
        except Exception as e:
            self.logger.error(f"Error loading inventory for xuid {xuid}: {e}")
            return []

    def save_enderchest(self, player) -> bool:
        items = []
        for i in range(player.ender_chest.size):
            items.append(self._serialize_db_item(player.ender_chest.get_item(i), i, "slot"))

        return self.save_enderchest_items(player.xuid, player.name, items)

    def get_enderchest(self, xuid: str) -> List[Dict[str, Any]]:
        placeholder = "%s" if self.use_mysql else "?"
        query = f"SELECT items_json FROM ender_chests_v2 WHERE xuid = {placeholder}"
        try:
            if self.use_mysql:
                conn = self._get_connection()
                try:
                    with conn.cursor() as cursor:
                        cursor.execute(query, (xuid,))
                        row = cursor.fetchone()
                        if not row or not row["items_json"]:
                            return []
                        items = json.loads(row["items_json"])
                        return [item for item in items if item.get("type") is not None]
                finally:
                    conn.close()
            else:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, (xuid,))
                    row = cursor.fetchone()
                    if not row or not row[0]:
                        return []
                    items = json.loads(row[0])
                    return [item for item in items if item.get("type") is not None]
        except Exception as e:
            self.logger.error(f"Error loading ender chest for xuid {xuid}: {e}")
            return []
