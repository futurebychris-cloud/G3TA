# Provider snapshots

`provider_snapshots.json` contains public, slowly changing provider metadata
that can be downloaded with the repository and used before a network lookup.

The export intentionally excludes credentials, personal information, cookies,
sessions, weather, availability, and live transport/hotel prices. Refresh it
with:

```bash
cd backend
PYTHONPATH=. .venv/bin/python scripts/export_provider_snapshots.py
```

Do not add raw SQLite files to this directory.
