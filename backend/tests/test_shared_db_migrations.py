import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from booking import shared_db


class SharedDatabaseMigrationTests(unittest.TestCase):
    def test_legacy_transport_table_keeps_rows_and_accepts_car(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "shared.db")
            with sqlite3.connect(path) as db:
                db.execute("""
                    CREATE TABLE shared_transport (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        trip_id TEXT NOT NULL,
                        transport_type TEXT NOT NULL CHECK(transport_type IN ('flight','train','bus','taxi','subway','bike','walk','ferry')),
                        scope TEXT DEFAULT 'national',
                        from_location TEXT NOT NULL,
                        to_location TEXT NOT NULL,
                        departure_time TEXT DEFAULT '',
                        arrival_time TEXT DEFAULT '',
                        carrier TEXT DEFAULT '',
                        flight_number TEXT DEFAULT '',
                        train_number TEXT DEFAULT '',
                        price REAL DEFAULT 0,
                        currency TEXT DEFAULT 'CNY',
                        booking_status TEXT DEFAULT 'pending',
                        booking_ref TEXT DEFAULT '',
                        notes TEXT DEFAULT '',
                        created_at TEXT DEFAULT (datetime('now'))
                    )
                """)
                db.execute(
                    "INSERT INTO shared_transport "
                    "(trip_id, transport_type, from_location, to_location) "
                    "VALUES ('old-trip', 'train', '杭州', '上海')"
                )

            with patch.object(shared_db, "DB_PATH", path):
                shared_db.init_shared_db()
                shared_db.save_transport(
                    "new-trip",
                    transport_type="car",
                    from_location="杭州",
                    to_location="上海",
                )
                old_rows = shared_db.get_transport_by_trip("old-trip")
                new_rows = shared_db.get_transport_by_trip("new-trip")

        self.assertEqual(old_rows[0]["transport_type"], "train")
        self.assertEqual(new_rows[0]["transport_type"], "car")


if __name__ == "__main__":
    unittest.main()
