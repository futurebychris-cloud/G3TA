"""Data-source service layer.

Every external data source is wrapped in one function with a fixed signature.
Agents call ONLY these functions — never the mock files directly — so a teammate
can swap a mock for a real API by editing just the file here. See README
"Adding Real APIs" for the full contract table.
"""
