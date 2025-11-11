# Aurora tracker orthographic overlay updates

- Refined both MU and theme fallback aurora detail templates to use the hemisphere-aware orthographic projection with safe-radius culling, sanitized path construction, and polar grid overlays.
- Adjusted UI interactions so the KP Lines control toggles the live viewline visibility without navigating away, while metrics now suppress quiet-sky zeros and clamp mean probability displays to ≤100%.
- Synced fallback overlay rendering, including the polar alignment guides and hemisphere-specific base-map swapping, to match the primary implementation.
