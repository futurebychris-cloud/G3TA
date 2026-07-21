"""Destination-aware data-source service layer.

Until live provider APIs are connected, services ask DeepSeek for planning
estimates tied to the exact trip request and mark every record for verification.
Real API adapters can replace individual services without changing agent output.
"""
