"""Shadow-mode social alert draft generation."""

__all__ = [
    "build_review_markdown",
    "build_shadow_payload",
    "write_shadow_payload",
    "write_shadow_review_markdown",
]


def __getattr__(name: str):
    if name in __all__:
        from . import shadow_drafts

        return getattr(shadow_drafts, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
