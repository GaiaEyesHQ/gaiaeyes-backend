# Social Share Image Guide

This guide documents how Gaia Eyes selects background images for social share cards. Update this file whenever `ShareBackgroundResolver`, `ShareDraftFactory`, or screen-specific share draft builders change.

## Current Implementation

The iOS share renderer loads images in `gaiaeyes-ios/ios/GaiaExporter/Services/ShareBackgroundResolver.swift`.

Plus lookup order:

1. Explicit `candidateURLs` attached by the screen that created the share draft.
2. Themed images in Supabase Storage, based on the card's `themeKeys`.
3. Style defaults for the card's `ShareBackgroundStyle`.
4. If no image loads, the app renders a generated gradient/background.

Free-user lookup order:

1. Style defaults for the card's `ShareBackgroundStyle`.
2. If no image loads, the app renders a generated gradient/background.

Free shares intentionally skip explicit candidate URLs and Supabase themed packs so they remain a basic branded share card. Plus shares use the full lookup order above.

The resolver stops at the first URL that returns a valid image. Each candidate currently has a short timeout of `0.75s`, so large files can appear to be "missing" even when the path is correct.

## Storage Locations

Preferred Supabase Storage bucket:

`space-visuals`

Themed background folders checked by the app:

- `social/share/backgrounds/`
- `backgrounds/share/`
- `backgrounds/square/`

Most reliable launch path:

`social/share/backgrounds/{name}.jpg`

The resolver caps themed candidates at `24`, so later folders/extensions may not be reached when a draft has several theme keys. Use `social/share/backgrounds/` with `.jpg` first unless there is a reason not to.

Example full public path:

`https://<supabase-project>.supabase.co/storage/v1/object/public/space-visuals/social/share/backgrounds/humidity_1.jpg`

## File Naming

Theme keys are normalized to lowercase snake case. For each theme key, the app tries these stem formats:

- `{theme_key}_{variant}`
- `{theme-key}-{variant}`
- `{theme_key}`
- `{theme-key}`

Supported extensions, in order:

- `.jpg`
- `.png`
- `.jpeg`
- `.webp`

The daily variant is a deterministic number from `1` through `6`, based on the current day and theme key. To rotate images without an app update, upload up to six variants:

```text
humidity_1.jpg
humidity_2.jpg
humidity_3.jpg
humidity_4.jpg
humidity_5.jpg
humidity_6.jpg
```

Dash-form names also work:

```text
air-quality-1.jpg
air-quality-2.jpg
air-quality.jpg
```

If only a base file exists, that file is used whenever the variant file for the day is missing:

```text
humidity.jpg
aqi.jpg
lunar.jpg
```

## Theme Key Map

Use these names when creating image files.

| Share subject | Recommended names |
| --- | --- |
| Current symptoms | `current_symptoms`, `symptoms`, `symptom` |
| Temporary illness | `illness`, `sick`, `temporary_illness` |
| Humidity | `humidity` |
| AQI / air quality | `aqi`, `air_quality`, `air_clarity` |
| Allergens / pollen | `seasonal_irritants`, `allergens`, `allergen`, `pollen` |
| Tree pollen | `tree_pollen` |
| Grass pollen | `grass_pollen` |
| Weed pollen | `weed_pollen` |
| Mold | `mold` |
| Barometric pressure | `pressure` |
| Temperature shift | `temperature` |
| Schumann resonance | `schumann`, `resonance` |
| Lunar patterns | `lunar`, `moon`, `full_moon`, `new_moon` |
| Kp / Bz / solar wind | `geomagnetic`, `solar`, `space_weather` |
| Solar flare | `solar_flare`, `solar` |
| CME | `cme`, `solar` |
| General driver stack | `driver_stack`, `current_drivers`, `mission_control` |
| Mission Control / EarthScope | `mission_control`, `earthscope` |
| Outlook | `outlook` |
| Patterns | `pattern`, `signals` |
| Body context | `body_context`, `symptoms`, `illness` |

## Screen-Specific Defaults

Some share surfaces attach explicit URLs before theme lookup runs:

- All Drivers and Schumann detail shares first try `social/earthscope/latest/tomsk_share_latest.jpg` and `social/earthscope/latest/cumiana_share_latest.jpg` from the Supabase `space-visuals` bucket, then fall back to the raw station images.
- CME shares first try Supabase `nasa/lasco_c2/latest.jpg` and `nasa/lasco_c3/latest.jpg`.
- Solar / Kp / Bz / solar wind shares first try Supabase `nasa/aia_304/latest.jpg`, `nasa/geospace_3h/latest.jpg`, and sometimes `drap/latest.png`.
- Schumann style fallback tries `social/earthscope/backgrounds/current_drivers.png`, then `daily_caption.jpg`.
- Atmospheric style fallback tries `social/earthscope/backgrounds/checkin.png`, `social/earthscope/backgrounds/current_drivers.png`, then `daily_affects.jpg`.
- Abstract style fallback tries `social/earthscope/backgrounds/current_drivers.png`, `social/earthscope/backgrounds/actions.png`, then `daily_caption.jpg`.

## Image Formatting Recommendations

Use these defaults unless a specific share format changes:

- Canvas: `1080 x 1080 px`.
- Color: sRGB.
- Format: `.jpg` preferred for photos and rendered backgrounds.
- Compression: quality around `75-85`.
- Target file size: ideally under `500 KB`; keep below `1 MB` if possible.
- Avoid alpha channels unless required; opaque JPGs decode faster and use less memory.
- Keep important visual details away from the bottom text zone and outer rounded corners.

Current text overlay behavior:

- The app overlays dynamic text over the lower portion of the card.
- The app adds a full-width SwiftUI lower scrim behind the dynamic text.
- Static themed images should not need baked dark lower panels unless a specific image needs extra treatment.
- Do not bake dynamic text, dates, user-specific stats, buttons, or Gaia Eyes branding into the image. The app owns those.

Text-safe area for baked lower panels:

- Reserve the lower `42-48%` of the square card for text.
- Keep text-safe margins of about `90-110 px` from the left and right edges.
- Keep branding-safe space near the lower-left corner if the app branding is visible.

## Live Solar/NASA Backgrounds

Live solar cards can use current NASA imagery. Those images are dynamic and will not include a baked lower text panel.

Launch-safe options:

- Leave live NASA cards as-is if the image remains readable enough with the current overlay.
- Prefer a future code-side lower scrim/panel if live NASA readability becomes inconsistent. That would make static and dynamic backgrounds behave the same and remove the need to bake panels into every image.
- Do not create separate baked-panel NASA files unless we intentionally stop using live imagery for those cards.

Recommended next implementation if readability is inconsistent:

- Reintroduce a full-width SwiftUI lower scrim behind text.
- Keep it subtle and uniform across all share cards.
- Stop baking lower panels into static images after that change.

## Schumann Latest Images

Current live Schumann candidates, in app lookup order:

```text
social/earthscope/latest/tomsk_share_latest.jpg
social/earthscope/latest/cumiana_share_latest.jpg
social/earthscope/latest/tomsk_latest.png
social/earthscope/latest/cumiana_latest.png
```

The `*_share_latest.jpg` files are generated by the Schumann GitHub Action with `bots/schumann/share_crop.py`. The cropper reads the station overlay and extractor JSON, anchors the crop to the current-time pick, adds a small right-side time margin, and writes a `1080 x 1080 px` JPG for share cards.

Bot-managed latest outputs:

```text
social/earthscope/latest/tomsk_share_latest.jpg
social/earthscope/latest/cumiana_share_latest.jpg
```

The raw `*_latest.png` station images are also mirrored to the same folder as fallbacks. They are wide format and will crop heavily in square cards, so prefer the share-ready JPGs for live Schumann posts.

## Rotation Rules

The app rotates only when variant files exist. It does not randomly choose from every matching file.

For a given theme key, the app computes a daily variant from `1` to `6`, then tries that variant first. Example for `humidity`:

```text
humidity_4.jpg
humidity-4.jpg
humidity.jpg
humidity.png
```

If you want daily rotation, upload numbered variants. If you want a fixed default, upload only the base file.

## Troubleshooting Missing Backgrounds

Check these first:

- File is in the `space-visuals` public bucket.
- File path is one of the checked folders.
- File name matches one of the theme keys above.
- File extension is lowercase `.jpg`, `.png`, `.jpeg`, or `.webp`.
- File is small enough to return within the current `0.75s` candidate timeout.
- The relevant theme key is likely in the first three theme keys for the draft. If not, use a broader key like `aqi`, `humidity`, `solar`, `lunar`, or `driver_stack`.
- Supabase object is public and returns HTTP 200 in a browser.

## Share Copy vs Share Images

Supabase share copy templates control image title, image subtitle, and caption text. They do not currently control the background image path.

Backgrounds are still selected by the iOS resolver using explicit URLs, theme keys, and style defaults.
