import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from booking import shared_db
from services.runtime_cache import cached_call, clear_runtime_cache
from services.provider_snapshots import reset_snapshot_cache, snapshot_scope_key


class ProviderCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = shared_db.DB_PATH
        shared_db.DB_PATH = str(Path(self.temp_dir.name) / "shared-test.db")
        shared_db.init_shared_db()
        clear_runtime_cache()
        reset_snapshot_cache()

    def tearDown(self):
        clear_runtime_cache()
        reset_snapshot_cache()
        shared_db.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_runtime_provider_cache_does_not_write_local_sqlite(self):
        calls = []

        def loader():
            calls.append("browser")
            return [{"name": "Stored Hotel", "price": 880}]

        with patch.dict(
            os.environ,
            {"PYTEST_CURRENT_TEST": "", "G3TA_DISABLE_RUNTIME_CACHE": ""},
        ):
            first = cached_call(
                "hotel-playwright-test",
                {"city": "Shanghai", "dates": ["2026-08-01", "2026-08-03"]},
                loader,
                ttl_seconds=600,
                persist=True,
                source="ctrip_playwright",
            )
            clear_runtime_cache()
            second = cached_call(
                "hotel-playwright-test",
                {"city": "Shanghai", "dates": ["2026-08-01", "2026-08-03"]},
                loader,
                ttl_seconds=600,
                persist=True,
                source="ctrip_playwright",
            )

        self.assertEqual(first, second)
        self.assertEqual(calls, ["browser", "browser"])
        metadata = shared_db.list_provider_cache("hotel-playwright-test")
        self.assertEqual(metadata, [])

    def test_expired_rows_are_not_returned_and_can_be_purged(self):
        shared_db.save_provider_cache(
            "expired-test",
            "key",
            '{"city":"Paris"}',
            {"value": 1},
            ttl_seconds=600,
        )
        with shared_db._conn() as db:
            db.execute(
                "UPDATE shared_provider_cache SET expires_at_epoch=0 "
                "WHERE namespace=? AND cache_key=?",
                ("expired-test", "key"),
            )

        self.assertIsNone(shared_db.get_provider_cache("expired-test", "key"))
        self.assertEqual(shared_db.purge_expired_provider_cache(), 1)
        self.assertEqual(shared_db.list_provider_cache("expired-test"), [])

    def test_repository_snapshot_can_avoid_loader_and_database(self):
        query = ("Shanghai", {"start": "2026-08-01", "end": "2026-08-02"})
        query_json = json.dumps(
            query,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        import hashlib

        key_digest = hashlib.sha256(query_json.encode("utf-8")).hexdigest()
        snapshot_path = Path(self.temp_dir.name) / "provider_snapshots.json"
        snapshot_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "entries": [
                        {
                            "namespace": "hotel-planning-search",
                            "cache_key": "different-exact-query",
                            "scope_key": snapshot_scope_key(
                                "hotel-planning-search",
                                ("Shanghai", {"start": "2025-01-01"}),
                            ),
                            "payload": [{"name": "Bundled Hotel", "source": "snapshot"}],
                        }
                    ],
                }
            )
        )
        calls = []
        with patch.dict(
            os.environ,
            {
                "PYTEST_CURRENT_TEST": "",
                "G3TA_DISABLE_RUNTIME_CACHE": "",
                "G3TA_ALLOW_PROVIDER_SNAPSHOTS": "1",
                "G3TA_PROVIDER_SNAPSHOT_PATH": str(snapshot_path),
            },
        ):
            result = cached_call(
                "hotel-planning-search",
                query,
                lambda: calls.append("network") or [],
                snapshot=True,
            )

        self.assertEqual(result[0]["name"], "Bundled Hotel")
        self.assertEqual(result[0]["source"], "repository_snapshot")
        self.assertTrue(result[0]["verification_required"])
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
