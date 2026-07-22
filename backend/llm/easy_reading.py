"""Opt-in prompt guidance for readable prose without changing travel facts."""

EASY_READING_INSTRUCTION = """Rewrite the result for easy reading.

Requirements:
- Use plain language.
- Use short sentences.
- Put one main idea on each line.
- Use clear headings.
- Explain unfamiliar travel abbreviations.
- Briefly explain travel jargon such as boarding gate, layover, terminal, platform, metro, immigration, and JR Pass.
- Put the most important information first.
- Preserve every date, time, price, location, warning, duration, flight number, and factual detail exactly.
- Do not add facts that are not present in the source data."""


def easy_reading_enabled(trip_input: dict) -> bool:
    return bool(trip_input.get("accessibility", {}).get("easy_reading", False))


def with_easy_reading(prompt: str, enabled: bool) -> str:
    if not enabled:
        return prompt
    return f"{prompt}\n\n{EASY_READING_INSTRUCTION}"
