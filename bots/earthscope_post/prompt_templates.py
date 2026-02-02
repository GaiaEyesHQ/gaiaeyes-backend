from typing import Dict, List

SYSTEM_TEMPLATE = """You are Gaia Eyes, a friendly, plain-language space-weather guide.
Write concise, human, helpful updates. Avoid medical claims. Keep it inclusive.
Never use the word "textured". Prefer concrete verbs and everyday words.
Tone: {tone} (humor={humor_level}). Mode: {lens_mode}.
"""


def build_messages(
    data: Dict,
    guides: Dict,
    style: Dict,
    lens_mode: str = "scientific",
    humor: str = "light",
) -> List[Dict]:
    humor_rules = style.get("humor_guidelines", {}).get(humor, {"spice": 0, "rules": []})
    return [
        {
            "role": "system",
            "content": SYSTEM_TEMPLATE.format(
                tone="warm, grounded, optimistic",
                humor_level=humor,
                lens_mode=lens_mode,
            ),
        },
        {
            "role": "user",
            "content": {
                "type": "json_schema",
                "json": {
                    "data": data,
                    "style": {
                        "humor": humor,
                        "humor_rules": humor_rules,
                        "softeners": style.get("softener_synonyms", {}),
                        "banned": style.get("banned_terms", []),
                    },
                    "guides": guides,
                },
            },
        },
    ]
