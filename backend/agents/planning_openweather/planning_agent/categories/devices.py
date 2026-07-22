"""DEVICES category: user's device list as a checklist, plus accessory/entertainment suggestions."""

from __future__ import annotations

from ..models import CategoryResult, ChecklistItem, TripScope, UserProfile
from ..reference_data import DEFAULT_ENTERTAINMENT_SUGGESTIONS, DEVICE_ACCESSORY_MAP, UNIVERSAL_ADAPTER_NOTE


def build_devices_category(user_profile: UserProfile) -> CategoryResult:
    checklist: list[ChecklistItem] = []
    next_id = 0
    seen_accessories: set[str] = set()

    for device in user_profile.device_list:
        checklist.append(ChecklistItem(
            id=f"device-{next_id}", name=device, checked=False, note="From your device list.",
        ))
        next_id += 1

        device_key = device.strip().lower()
        for keyword, accessories in DEVICE_ACCESSORY_MAP.items():
            if keyword in device_key:
                for accessory in accessories:
                    if accessory not in seen_accessories:
                        seen_accessories.add(accessory)
                        checklist.append(ChecklistItem(
                            id=f"device-{next_id}", name=accessory, checked=False,
                            note=f"Needed for your {device}.",
                        ))
                        next_id += 1

    if user_profile.trip_scope == TripScope.INTERNATIONAL and UNIVERSAL_ADAPTER_NOTE not in seen_accessories:
        checklist.append(ChecklistItem(
            id=f"device-{next_id}", name=UNIVERSAL_ADAPTER_NOTE, checked=False,
            note="International destination may use a different plug/voltage.",
        ))
        next_id += 1

    existing_names = {i.name.lower() for i in checklist}
    for suggestion in DEFAULT_ENTERTAINMENT_SUGGESTIONS:
        if suggestion.lower() not in existing_names:
            checklist.append(ChecklistItem(
                id=f"device-{next_id}", name=suggestion, checked=False, note="Optional entertainment for the trip.",
            ))
            next_id += 1

    summary = f"{len(user_profile.device_list)} device(s) tracked, {len(checklist)} total item(s) including accessories."
    return CategoryResult(category="devices", summary=summary, items=checklist)
