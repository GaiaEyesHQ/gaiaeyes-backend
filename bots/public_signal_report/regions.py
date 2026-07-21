from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class RegionAnchor:
    anchor_id: str
    region_key: str
    region_label: str
    macro_region: str
    location_label: str
    lat: float
    lon: float


def _anchors(
    region_key: str,
    region_label: str,
    macro_region: str,
    points: tuple[tuple[str, float, float], ...],
) -> list[RegionAnchor]:
    return [
        RegionAnchor(
            anchor_id=f"{region_key}:{location.lower().replace(' ', '_')}",
            region_key=region_key,
            region_label=region_label,
            macro_region=macro_region,
            location_label=location,
            lat=lat,
            lon=lon,
        )
        for location, lat, lon in points
    ]


_REGION_GROUPS = (
    ("us_new_england", "New England", "North America", (("Boston", 42.36, -71.06), ("Portland Maine", 43.66, -70.26), ("Burlington", 44.48, -73.21))),
    ("us_mid_atlantic", "Mid-Atlantic US", "North America", (("New York", 40.71, -74.01), ("Philadelphia", 39.95, -75.17), ("Pittsburgh", 40.44, -79.99))),
    ("us_southeast", "Southeastern US", "North America", (("Atlanta", 33.75, -84.39), ("Raleigh", 35.78, -78.64), ("Charleston", 32.78, -79.93))),
    ("us_florida_gulf", "Florida and the Gulf Coast", "North America", (("Miami", 25.76, -80.19), ("Tampa", 27.95, -82.46), ("New Orleans", 29.95, -90.07))),
    ("us_great_lakes", "Great Lakes US", "North America", (("Chicago", 41.88, -87.63), ("Detroit", 42.33, -83.05), ("Cleveland", 41.50, -81.69))),
    ("us_ohio_tennessee", "Ohio and Tennessee Valleys", "North America", (("Cincinnati", 39.10, -84.51), ("Louisville", 38.25, -85.76), ("Nashville", 36.16, -86.78))),
    ("us_northern_plains", "Northern Plains US", "North America", (("Minneapolis", 44.98, -93.27), ("Fargo", 46.88, -96.79), ("Rapid City", 44.08, -103.23))),
    ("us_southern_plains", "Southern Plains US", "North America", (("Dallas", 32.78, -96.80), ("Oklahoma City", 35.47, -97.52), ("Wichita", 37.69, -97.34))),
    ("us_mountain_west", "Mountain West US", "North America", (("Denver", 39.74, -104.99), ("Salt Lake City", 40.76, -111.89), ("Boise", 43.62, -116.20))),
    ("us_desert_southwest", "Desert Southwest US", "North America", (("Phoenix", 33.45, -112.07), ("Las Vegas", 36.17, -115.14), ("Albuquerque", 35.08, -106.65))),
    ("us_california", "California", "North America", (("Los Angeles", 34.05, -118.24), ("San Francisco", 37.77, -122.42), ("Sacramento", 38.58, -121.49))),
    ("us_pacific_northwest", "Pacific Northwest US", "North America", (("Seattle", 47.61, -122.33), ("Portland Oregon", 45.52, -122.68), ("Spokane", 47.66, -117.43))),
    ("us_alaska", "Alaska", "North America", (("Anchorage", 61.22, -149.90), ("Fairbanks", 64.84, -147.72), ("Juneau", 58.30, -134.42))),
    ("us_hawaii", "Hawaii", "Oceania", (("Honolulu", 21.31, -157.86), ("Hilo", 19.71, -155.08), ("Kahului", 20.89, -156.47))),
    ("canada_west", "Western Canada", "North America", (("Vancouver", 49.28, -123.12), ("Calgary", 51.05, -114.07), ("Winnipeg", 49.90, -97.14))),
    ("canada_east", "Eastern Canada", "North America", (("Toronto", 43.65, -79.38), ("Montreal", 45.50, -73.57), ("Halifax", 44.65, -63.57))),
    ("mexico_central_america", "Mexico and Central America", "North America", (("Mexico City", 19.43, -99.13), ("Guatemala City", 14.63, -90.51), ("Panama City", 8.98, -79.52))),
    ("caribbean", "Caribbean", "North America", (("San Juan", 18.47, -66.11), ("Havana", 23.11, -82.37), ("Santo Domingo", 18.49, -69.99))),
    ("uk_ireland", "UK and Ireland", "Europe", (("London", 51.51, -0.13), ("Manchester", 53.48, -2.24), ("Dublin", 53.35, -6.26))),
    ("western_europe", "Western Europe", "Europe", (("Paris", 48.86, 2.35), ("Amsterdam", 52.37, 4.90), ("Brussels", 50.85, 4.35))),
    ("central_europe", "Central Europe", "Europe", (("Berlin", 52.52, 13.41), ("Warsaw", 52.23, 21.01), ("Vienna", 48.21, 16.37))),
    ("northern_europe", "Northern Europe", "Europe", (("Oslo", 59.91, 10.75), ("Stockholm", 59.33, 18.07), ("Helsinki", 60.17, 24.94))),
    ("southern_europe", "Southern Europe", "Europe", (("Madrid", 40.42, -3.70), ("Rome", 41.90, 12.50), ("Athens", 37.98, 23.73))),
    ("north_africa", "North Africa", "Africa", (("Casablanca", 33.57, -7.59), ("Algiers", 36.75, 3.06), ("Cairo", 30.04, 31.24))),
    ("west_central_africa", "West and Central Africa", "Africa", (("Dakar", 14.72, -17.47), ("Lagos", 6.52, 3.38), ("Kinshasa", -4.33, 15.31))),
    ("east_africa", "East Africa", "Africa", (("Addis Ababa", 9.03, 38.74), ("Nairobi", -1.29, 36.82), ("Dar es Salaam", -6.79, 39.21))),
    ("southern_africa", "Southern Africa", "Africa", (("Johannesburg", -26.20, 28.05), ("Cape Town", -33.92, 18.42), ("Harare", -17.83, 31.05))),
    ("middle_east", "Middle East", "Asia", (("Istanbul", 41.01, 28.98), ("Riyadh", 24.71, 46.68), ("Tehran", 35.69, 51.39))),
    ("central_asia", "Central Asia", "Asia", (("Almaty", 43.24, 76.95), ("Tashkent", 41.30, 69.24), ("Astana", 51.17, 71.43))),
    ("south_asia", "South Asia", "Asia", (("Delhi", 28.61, 77.21), ("Mumbai", 19.08, 72.88), ("Dhaka", 23.81, 90.41))),
    ("southeast_asia", "Southeast Asia", "Asia", (("Bangkok", 13.76, 100.50), ("Singapore", 1.35, 103.82), ("Jakarta", -6.21, 106.85))),
    ("east_asia", "East Asia", "Asia", (("Beijing", 39.90, 116.41), ("Seoul", 37.57, 126.98), ("Tokyo", 35.68, 139.69))),
    ("north_asia", "Northern Asia", "Asia", (("Novosibirsk", 55.03, 82.92), ("Irkutsk", 52.29, 104.28), ("Vladivostok", 43.12, 131.89))),
    ("northern_south_america", "Northern South America", "South America", (("Bogota", 4.71, -74.07), ("Caracas", 10.48, -66.90), ("Georgetown", 6.80, -58.16))),
    ("andes", "Andean South America", "South America", (("Quito", -0.18, -78.47), ("Lima", -12.05, -77.04), ("La Paz", -16.49, -68.12))),
    ("brazil_atlantic", "Brazil and the Atlantic Coast", "South America", (("Manaus", -3.12, -60.02), ("Brasilia", -15.79, -47.88), ("Sao Paulo", -23.55, -46.63))),
    ("southern_cone", "Southern South America", "South America", (("Buenos Aires", -34.60, -58.38), ("Santiago", -33.45, -70.67), ("Montevideo", -34.90, -56.16))),
    ("eastern_australia", "Eastern Australia", "Oceania", (("Brisbane", -27.47, 153.03), ("Sydney", -33.87, 151.21), ("Melbourne", -37.81, 144.96))),
    ("western_northern_australia", "Western and Northern Australia", "Oceania", (("Perth", -31.95, 115.86), ("Darwin", -12.46, 130.84), ("Adelaide", -34.93, 138.60))),
    ("new_zealand_pacific", "New Zealand and the South Pacific", "Oceania", (("Auckland", -36.85, 174.76), ("Wellington", -41.29, 174.78), ("Suva", -18.14, 178.44))),
)


PUBLIC_SIGNAL_ANCHORS = tuple(
    anchor
    for region_key, region_label, macro_region, points in _REGION_GROUPS
    for anchor in _anchors(region_key, region_label, macro_region, points)
)

US_SIGNAL_ANCHORS = tuple(anchor for anchor in PUBLIC_SIGNAL_ANCHORS if anchor.region_key.startswith("us_"))


def region_registry_payload() -> list[dict]:
    return [asdict(anchor) for anchor in PUBLIC_SIGNAL_ANCHORS]
