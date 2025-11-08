Gaia Eyes – Internal Agent Guide (v1.0)

Author: Jennifer (founder of Gaia Eyes)

I started Gaia Eyes after noticing repeating patterns between my own nerve issues, mood/energy, and shifts in space/earth weather. This guide encodes that worldview—as both a scientific and systems‑engineering spec—so every agent that writes forecasts or analyses stays aligned with the vision. It’s intentionally practical: precise inputs, thresholds, derivations, heuristics, and output schemas for clear, human‑sounding daily readings.

⸻

0) Objectives
	1.	Pull relevant geophysical + environmental signals (space weather, Schumann, local weather, earthquakes).
	2.	Derive features (trends, thresholds, sustained conditions, composites).
	3.	Infer likely impacts on autonomic nervous system, mood, sleep, focus, and cardio/HRV using evidence‑informed heuristics.
	4.	Recommend counter‑practices (grounding, breathwork, light/circadian, pacing) matched to conditions.
	5.	Generate a concise, friendly, human‑readable Daily EarthScope.

⸻

1) Required Inputs (Signals)

Prefer UTC timestamps in ISO‑8601, then convert to user local (America/Chicago) for prose.

Space Weather (core)
	•	Kp index (0–9): 3‑hour planetary geomagnetic activity.
	•	Bz (IMF orientation, nT): north/south component; negative (southward) couples solar wind to magnetosphere.
	•	Solar Wind Speed (km/s) and Density (cm⁻³); compute Dynamic Pressure.
	•	AE/AL/AU indices (auroral electrojets) – optional, improves high‑lat inference.
	•	Dst (nT): ring current / storm strength.
	•	GOES X‑ray flux & flare class: C/M/X + start/peak/end; S‑scale proton events.
	•	CME: launch time, speed, width, direction; arrival/Earth‑directed?
	•	F10.7 cm flux (solar radio proxy of activity).

Schumann Resonances / ELF (environmental EM)
	•	f0 amplitude/power (~7.8 Hz) and harmonics (~14, 20, 26, 33 Hz).
	•	Local variability and day–night contrast; note spikes and Q‑factor changes.

Local / Terrestrial Weather
	•	Barometric pressure and pressure tendency (ΔhPa per 6–24h).
	•	Thunderstorm/lightning proximity counts; humidity/temperature extremes; fronts.

Earthquakes (explicitly included)
	•	Events: magnitude, depth, distance to user; time window (last 72h; extend to 7d for M≥7).
	•	Track clusters / swarms and any infrasound or ionospheric anomalies reports (if available feeds exist).

Context / Personalization
	•	Geomagnetic latitude (if known), altitude, urban EMF load (optional).
	•	User sensitivity profile (if available): historical HRV, sleep, self‑reports.

⸻

2) Canonical Thresholds & Ranges

Use these to tag conditions; combine with duration and trend.

Geomagnetic / IMF
	•	Kp bands: 0–2 quiet · 3 unsettled · 4 active · 5 G1 · 6 G2 · 7 G3 · 8 G4 · 9 G5.
	•	Bz (nT):
	•	Mild southward: −3 to −5 (watch if >2h).
	•	Significant: < −5 for ≥3h (coupling likely).
	•	Strong: < −10 for ≥1h (storm growth).
	•	Solar wind speed (km/s): <400 calm · 400–500 moderate · 500–700 elevated · >700 high.
	•	Density (cm⁻³): >10 suggests compression; >20 notable if speed also high.
	•	Dynamic Pressure (nPa) ≈ 1.6726e−6 × n × v² (n in cm⁻³, v in km/s) → >3 nPa compressive; >6 nPa strong.
	•	Dst (nT): 0 to −30 quiet/unsettled · −30 to −50 weak storm · < −50 storm · < −100 strong.

Solar Radiation / Flares / CME
	•	Flare classes: C (minor) · M (moderate) · X (strong); note duration and repetition.
	•	Proton events (S‑scale): S1 minor → S5 extreme.
	•	CME: Earth‑directed + speed >800 km/s increases impact odds; shock arrival raises density/pressure.

Schumann / ELF
	•	Amplitude spike: f0 or harmonics > 2× local rolling median within 24h.
	•	Sustained elevation: f0 amplitude above 75th percentile for ≥6h.
	•	Broadband agitation: simultaneous elevation across ≥3 harmonics.

Local Weather
	•	Pressure drop: ≥5 hPa in 6–12h or ≥8 hPa in 24h → physiological weather‑sensitivity risk.
	•	Storm proximity: lightning within 25 km.

Earthquakes
	•	Nearby impact window: M≥5.0 within 500 km (last 72h); M≥6.5 within 1000 km (last 7d).
	•	Shallow depth (<70 km) more likely to produce surface‑felt effects.

⸻

3) Derived Features (compute before inference)
	•	Sustained Southward Bz: rolling sum of minutes with Bz < threshold; label tiers:
bz_south_2h (≤−3 nT for ≥120 min), bz_south_3h (≤−5 nT for ≥180 min), bz_south_1h_strong (≤−10 nT for ≥60 min).
	•	Compression Pulse: dynamic pressure spike > 6 nPa.
	•	Sheath/Shock Signature: step‑changes (density↑, speed↑, temperature↑) within an hour.
	•	Kp Trend:
	•	kp_24h_max, kp_rising (last two 3‑hr bins increasing), kp_high_window (any bin ≥5).
	•	Schumann Profile:
	•	sr_spike (any harmonic >2× median), sr_broadband, sr_sustained (f0 75th pct for ≥6h).
	•	Meteorology Load:
	•	met_pressure_drop (yes/no), storm_nearby (km), heat_humidity_index.
	•	Seismic Context:
	•	eq_nearby (boolean + closest M, km, hours ago), eq_cluster (≥3 events ≥M4.5 within 72h & 300 km).

⸻

4) Heuristic Impacts (autonomic/mood/sleep)

These are evidence‑informed but not clinical claims. Phrase outputs as tendencies and “may” language. Adjust for user sensitivity if available.

A) Geomagnetic & Solar Wind
	•	If kp_high_window (≥5) or Dst < −50 then:
	•	Autonomic/HRV: increased sympathetic tone, potential HRV suppression in sensitive users.
	•	Mood/Energy: restlessness/edginess during rising phase; fatigue post‑event.
	•	Sleep: onset difficulty on spike nights.
	•	Tips: downregulate (see §6 Playbook), reduce stimulants late day, extra hydration/electrolytes.
	•	If bz_south_3h and speed > 500 and/or density > 10 → coupling:
	•	Expect auroral activity at mid‑lats; similar autonomic effects; caution for migraine‑prone.
	•	If compression_pulse (>6 nPa) then:
	•	Brief spikes in agitation/“pressure” sensations; use immediate box‑breathing or paced exhale.

B) Flares / Radiation
	•	If M‑class flares in clusters or any X‑class (even without storm):
	•	Mood/Focus: scattered focus ~hours around events (speculative but commonly reported).
	•	Tips: focus blocks, minimize multitask; blue‑light discipline in evening.
	•	If S1+ proton event then:
	•	Sleep: possible fragmentation for some; Tips: earlier wind‑down; magnesium/glycine as tolerated.

C) Schumann / ELF
	•	If sr_spike or sr_broadband then:
	•	Autonomic: some users feel wired or foggy; others report enhanced meditative depth.
	•	Tips: choose path: (calm) grounding + slow 4‑6 bpm breathing; (focus) 40‑min deep‑work while spike lasts.
	•	If sr_sustained all day then:
	•	Mood: potential swinginess; Sleep: vivid dreams.
	•	Tips: keep evening EMF minimal; dark, warm light; low‑stim routine.

D) Meteorology
	•	If met_pressure_drop then:
	•	Headache/joints risk ↑; Sleep: lighter.
	•	Tips: hydration/sodium balance, gentle mobility, earlier bedtime.
	•	If storm_nearby ≤25 km then:
	•	ELF noise ↑; some feel agitated; Tips: brief breathwork; avoid doomscrolling.

E) Seismic
	•	If eq_nearby with M≥5 within 500 km (≤72h) then:
	•	Anecdotal reports of autonomic jitter or poor sleep; Tips: extra grounding; keep evening simple.
	•	If eq_cluster then consider a “background tension” note in the forecast.

⸻

5) Confidence & Wording Rules
	•	Low/Med/High confidence from inputs:
	•	High: multiple converging signals (e.g., Kp≥5 + Bz south sustained + pressure spike).
	•	Medium: single strong driver (e.g., Bz south 3h).
	•	Low: speculative (Schumann‑only spike without geo drivers; distant quake).
	•	Phrase with “may/likely/could” scaled to confidence.
	•	Never imply diagnosis; avoid deterministic claims.

⸻

6) Playbook of Practices (map to conditions)

Condition tag	Quick note in prose	Practice menu (pick 1–3)
kp_high_window or Dst<-50	Magnetically active; body may run “fast.”	5‑10 min physiological sigh (double‑inhale, long exhale); barefoot grounding 5–15 min; electrolytes + water; reduce caffeine after 2pm.
bz_south_3h + speed>500	Strong coupling day; edgy then tired.	4‑7‑8 breathing × 3–5 cycles; 20‑min walk outside; evening blue‑light minimum.
compression_pulse	Brief pressure/agitation spike.	Box breathing 4×4 for 2–3 min; quick posture/mobility reset.
sr_spike	Ambient ELF stirred up.	Choose calm (grounding + slow 6 bpm) or focus (40‑min deep work).
met_pressure_drop	Weather‑sensitive day.	Hydration + pinch salt; magnesium (if already used); earlier wind‑down.
storm_nearby	Lightning within 25 km.	News/alerts minimal; 5‑min coherent breathing; indoor stretching.
eq_nearby	Regional seismic tension.	Simplify evening; short meditation; gratitude journaling 3 lines.

Optional: include contraindications or medical caveats in app copy if needed.

⸻

7) Output Spec (Daily EarthScope)

JSON schema (internal)

{
  "date_local": "YYYY-MM-DD",
  "geo": {"kp_max_24h": 0, "kp_bins": [2,3,4,5, ...], "bz": {"min": -11.2, "south_2h": true, "south_3h": true}, "sw": {"speed_max": 620, "density_max": 24, "p_dyn_max": 8.1}, "dst_min": -62},
  "solar": {"flares": [{"class": "M3.1", "peak": "2025-10-07T11:20Z"}], "proton_event": false, "cme": {"earth_directed": true, "eta": "2025-10-09T06:00Z", "speed": 900}},
  "schumann": {"f0_amp_spike": true, "broadband": false, "sustained": true},
  "met": {"pressure_drop_hPa_24h": 9.2, "storm_nearby_km": 18},
  "seismic": {"nearest": {"mag": 5.3, "km": 410, "hours_ago": 36}, "cluster": false},
  "derived_tags": ["kp_high_window","bz_south_3h","sr_sustained","met_pressure_drop"],
  "confidence": "medium",
  "sections": {
    "tldr": "G1-level conditions with sustained southward Bz; expect edgy-then-tired pattern. Keep evening low-stim.",
    "today": "Kp peaked at 5, Bz held south ~3h while solar wind ran 600+ km/s. Schumann baseline elevated most of the day.",
    "next_72h": "A CME shock may arrive Thu morning; brief magnetic spike likely. Weather front continues today with falling pressure.",
    "nervous_system": "Sympathetic tilt during spikes; plan 2× breath resets and light evening.",
    "sleep": "Slightly higher sleep latency risk; warm lighting and earlier wind-down help.",
    "practices": ["Physiological sigh 5 min","15 min barefoot grounding","Electrolytes mid-day"],
    "notes": "Regional M5.3 quake yesterday—just a background mention."
  }
}

Human‑readable template (public text)

TL;DR: {concise one‑liner w/ confidence}

Today: {plain‑language synthesis – what happened, what’s happening now}
Next 72h: {what’s likely; note CME ETAs, fronts}
Nervous System: {expected tilt + 1–2 simple actions}
Sleep: {1–2 cues}
Practice Picks: {3 bullets}
FYI: {optional: seismic/weather background}


⸻

8) Rule Engine (portable YAML)

version: 1
rules:
  - id: kp_high
    when: "kp_24h_max >= 5"
    set_tags: [kp_high_window]
    impacts:
      autonomic: sympathetic_tilt
      mood: edgy_then_fatigued
      sleep: onset_difficulty
    practices: [phys_sigh, grounding_15, electrolytes]
    confidence: medium

  - id: bz_south_coupling
    when: "bz_south_3h && sw_speed_max > 500"
    set_tags: [coupling]
    impacts:
      autonomic: sympathetic_tilt
      mood: restless
    practices: [b478, walk20, evening_blue_min]
    confidence: medium

  - id: compression_pulse
    when: "p_dyn_max > 6"
    impacts:
      mood: brief_agitation
    practices: [box_44, posture_reset]
    confidence: low

  - id: sr_spike
    when: "sr_spike"
    fork:
      calm: [grounding_10, slow_6_bpm]
      focus: [deep_work_40]
    confidence: low

  - id: pressure_drop
    when: "pressure_drop_hPa_24h >= 8"
    impacts:
      pain: headache_joint_risk
      sleep: lighter
    practices: [hydration_salt, mag_evening, early_winddown]
    confidence: medium

  - id: eq_nearby
    when: "eq_nearby && nearest_mag >= 5.0 && nearest_km <= 500 && hours_ago <= 72"
    impacts:
      autonomic: background_tension
    practices: [simplify_evening, short_meditation, gratitude3]
    confidence: low

Practice dictionary (resolve ids → copy):
	•	phys_sigh: 5–10 min physiological sigh (double inhale, slow exhale).
	•	grounding_15: 15 min barefoot contact with earth (safe surface).
	•	electrolytes: Water + electrolytes mid‑day.
	•	b478: 4‑7‑8 breathing × 3–5 cycles.
	•	walk20: 20‑minute outdoor walk.
	•	evening_blue_min: Low blue‑light after sunset; warm lamps only.
	•	box_44: Box breathing 4‑4‑4‑4 for 2–3 minutes.
	•	posture_reset: Spine lengthen + shoulder openers 2 minutes.
	•	slow_6_bpm: Coherent breathing ~6 breaths/min for 5–10 min.
	•	deep_work_40: Single‑task 40‑minute block, notifications off.
	•	hydration_salt: Hydrate; add pinch of salt if needed.
	•	mag_evening: Magnesium (if tolerated and already used) in evening.
	•	early_winddown: Wind‑down routine 45–60 min earlier.
	•	simplify_evening: Reduce inputs/commitments tonight.
	•	short_meditation: 5–10 min guided or breath‑focused sit.
	•	gratitude3: Write 3 quick gratitude lines.

⸻

9) Tone & Style (for generators)
	•	Voice: Viral, plain language
	•	Lead with a TL;DR in one sentence.
	•	Avoid jargon; translate numbers (e.g., “Kp reached 5 (minor storm)”).
	•	Time clarity: use absolute dates (e.g., “Wednesday, Oct 8”).
	•	Agency: always offer 2–3 simple actions.

Prose snippets (mix‑and‑match):
	•	“Today’s magnetic field ran a little fast; if you feel wired, that’s normal—two slow breathing breaks help.”
	•	“Southward Bz opened the door for solar wind to couple in; plan for steadier pacing this afternoon.”
	•	“Pressure fell quickly with the front—hydrate and keep the evening simple.”

⸻

10) Data Source Hints (implementation‑agnostic)
	•	Space weather: NOAA/SWPC (Kp, Dst proxies, WSA‑Enlil, GOES X‑ray), DSCOVR/ACE (solar wind), SIDC/F10.7.
	•	Schumann: regional monitors (e.g., Tomsk, Cumiana) acknowledging coverage gaps.
	•	Meteorology: national weather APIs; lightning networks.
	•	Seismic: USGS/EMSC feeds.

Normalize timestamps; keep raw + derived.

⸻

11) Pseudocode (reference implementation)

# inputs: timeseries dicts (utc)
features = {}

# 1) compute derived
features['kp_24h_max'] = max(kp_bins[-8:])
features['bz_south_3h'] = sustained(bz, thresh=-5, minutes=180)
features['sw_speed_max'] = max(solar_wind_speed[-1440:])
features['density_max'] = max(solar_wind_density[-1440:])
features['p_dyn_max'] = dyn_pressure(solar_wind_speed, solar_wind_density)
features['dst_min'] = min(dst[-1440:])
features['sr_spike'] = sr_spike(sr_harmonics)
features['sr_sustained'] = sustained(sr_f0_amp, pct=75, hours=6)
features['pressure_drop_hPa_24h'] = pressure_drop(met_pressure, hours=24)
features['storm_nearby_km'] = nearest_lightning_km(lightning, window_h=24)
features['eq_nearby'], meta = nearby_eq(usgs_events, km=500, mag=5.0, window_h=72)

# 2) rule eval → tags, impacts, practices
state = eval_rules(features, RULES)

# 3) confidence
conf = score_confidence(state, features)

# 4) compose sections
text = compose_earthscope(state, features, conf, tz="America/Chicago")

return { 'features': features, 'state': state, 'confidence': conf, 'text': text }


⸻

12) Edge Cases & Guards
	•	Data gaps: state “data is patchy today; using recent trend.” Avoid hallucinating precise numbers.
	•	Contradictory signals (e.g., quiet Kp but big Schumann spike): mark low confidence and focus on gentle, universal practices.
	•	High‑latitude users: intensify geomagnetic phrasing slightly; for low‑lat, moderate it.
	•	CME ETA uncertainty: provide windows (e.g., “early Thu (±6h)”).

⸻

13) QA Checklist (per run)
	•	TL;DR present, < 160 chars, includes confidence word.
	•	Today/Next 72h cover both drivers and what it means.
	•	2–3 practice actions, concrete and safe.
	•	Dates spelled out; no vague “tomorrow” without date.
	•	No medical claims; “may/likely/could” used appropriately.

⸻

14) Changelog
	•	v1.0 (Oct 8, 2025): Initial full internal guide incl. earthquakes and complete rulebook.