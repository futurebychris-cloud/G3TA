"""Pytest collection settings for the backend suite.

``_smoke_test.py`` is an executable offline smoke script. It monkeypatches
module globals intentionally and is run directly from the command line, so
importing it during pytest collection would leak those patches into unit tests.
"""

collect_ignore = ["_smoke_test.py"]
