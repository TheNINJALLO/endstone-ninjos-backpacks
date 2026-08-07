import json
import sqlite3

from ninjos_backpacks.database import Database


class RecordingLogger:
    def __init__(self):
        self.messages = []

    def info(self, message):
        self.messages.append(("info", message))

    def warning(self, message):
        self.messages.append(("warning", message))

    def error(self, message):
        self.messages.append(("error", message))


def test_ender_chest_json_preserves_unicode_using_ascii_safe_storage(tmp_path):
    database_path = tmp_path / "backpacks.db"
    database = Database(database_path, RecordingLogger())
    items = [
        {
            "slot": 0,
            "slot_type": "slot",
            "type": "minecraft:diamond_sword",
            "name": "Quest complete ✔️",
        }
    ]

    assert database.save_enderchest_items("123", "STR1K3R68", items)

    with sqlite3.connect(database_path) as connection:
        stored_json = connection.execute(
            "SELECT items_json FROM ender_chests_v2 WHERE xuid = ?", ("123",)
        ).fetchone()[0]

    assert "✔️" not in stored_json
    assert "\\u2714\\ufe0f" in stored_json
    assert json.loads(stored_json) == items
    assert database.get_enderchest("123") == items


class RecordingCursor:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, params=None):
        self.calls.append((query, params))

    def fetchall(self):
        return self.rows


class RecordingConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
        self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


def test_mysql_save_uses_mysql_upsert_and_ascii_safe_json():
    cursor = RecordingCursor()
    connection = RecordingConnection(cursor)
    database = Database.__new__(Database)
    database.use_mysql = True
    database.logger = RecordingLogger()
    database._get_connection = lambda: connection

    assert database.save_inventory_items(
        "123", "STR1K3R68", [{"type": "minecraft:paper", "name": "✔️"}]
    )

    query, params = cursor.calls[0]
    assert "ON DUPLICATE KEY UPDATE" in query
    assert "INSERT OR REPLACE" not in query
    assert "\\u2714\\ufe0f" in params[2]
    assert connection.committed
    assert connection.closed


def test_mysql_charset_upgrade_only_alters_reported_legacy_tables():
    cursor = RecordingCursor(
        [
            {"table_name": "ender_chests_v2"},
            {"table_name": "inventories_v2"},
        ]
    )
    database = Database.__new__(Database)
    database.mysql_config = {"database": "s1_player_data"}
    database.logger = RecordingLogger()

    database._upgrade_mysql_charset(cursor)

    inspection_query, inspection_params = cursor.calls[0]
    assert "information_schema.COLUMNS" in inspection_query
    assert inspection_params[0] == "s1_player_data"
    alter_queries = [query for query, _ in cursor.calls[1:]]
    assert alter_queries == [
        "ALTER TABLE `ender_chests_v2` CONVERT TO CHARACTER SET utf8mb4 "
        "COLLATE utf8mb4_unicode_ci",
        "ALTER TABLE `inventories_v2` CONVERT TO CHARACTER SET utf8mb4 "
        "COLLATE utf8mb4_unicode_ci",
    ]
