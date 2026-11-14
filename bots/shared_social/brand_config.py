"""Brand-specific Meta publishing configuration; never print tokens."""
from dataclasses import dataclass
import os


@dataclass(frozen=True)
class BrandConfig:
    brand: str
    facebook_page_id: str
    instagram_user_id: str
    access_token: str

    @classmethod
    def from_environment(cls, brand: str) -> "BrandConfig":
        key = brand.upper().replace("-", "_")
        if key not in {"GAIA_EYES", "MOD_PANIC"}:
            raise ValueError("Unsupported brand")
        values = {
            "facebook_page_id": os.getenv(f"{key}_FB_PAGE_ID", ""),
            "instagram_user_id": os.getenv(f"{key}_IG_USER_ID", ""),
            "access_token": os.getenv(f"{key}_FB_ACCESS_TOKEN", ""),
        }
        missing = [name for name, value in values.items() if not value.strip()]
        if missing:
            raise ValueError(f"Missing {key} configuration: {', '.join(missing)}")
        return cls(brand=brand, **values)
