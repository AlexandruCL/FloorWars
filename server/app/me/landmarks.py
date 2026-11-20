"""Landmarks for ``GET /v1/me/season-stats``: a fixed list, sorted by height.

``reached`` is ``ascent_m >= height_m``. Heights are the figures the owners publish (decided by
Ionut, 2026-11-20); sources are listed per entry. Not re-fetched by the agent that wrote this.
"""

# (name, height_m, source)
LANDMARKS: tuple[tuple[str, float, str], ...] = (
    ("Statue of Liberty", 93.0, "US National Park Service: 305 ft from ground to torch tip"),
    ("Big Ben (Elizabeth Tower)", 96.0, "UK Parliament: tower height 96 m"),
    ("Eiffel Tower", 330.0, "Societe d'exploitation de la tour Eiffel: 330 m with antennas"),
    ("Empire State Building", 381.0, "Empire State Realty Trust: roof height 381 m (1,250 ft)"),
    ("Burj Khalifa", 828.0, "Emaar / CTBUH: 828 m"),
)


def progress(ascent_m: float) -> list[dict[str, object]]:
    return [
        {"name": name, "height_m": height, "reached": ascent_m >= height}
        for name, height, _source in LANDMARKS
    ]
