begin;

insert into content.home_feed_items (
  slug,
  mode,
  kind,
  title,
  body,
  priority
)
values
  (
    'scientific-pressure-context',
    'scientific',
    'fact',
    'Pressure is context',
    'Barometric pressure changes can line up with headache, sinus, or pain logs for some people. Gaia Eyes watches timing, not diagnosis, before it raises the signal.',
    300
  ),
  (
    'scientific-aqi-nearby-signal',
    'scientific',
    'fact',
    'AQI is a nearby signal',
    'AQI describes outdoor air around your area. It does not measure personal exposure, but it can add context when fatigue, fog, or irritation logs cluster.',
    299
  ),
  (
    'scientific-pollen-varies-day',
    'scientific',
    'fact',
    'Pollen can shift fast',
    'Allergen levels can change by plant type, season, wind, and rain. Logging symptoms helps Gaia Eyes see whether those shifts may overlap with your patterns.',
    298
  ),
  (
    'scientific-sleep-anchors-read',
    'scientific',
    'tip',
    'Sleep anchors the read',
    'Short, late, or broken sleep can shape how a day feels. When sleep data is available, Gaia Eyes uses it as recovery context before highlighting other signals.',
    297
  ),
  (
    'scientific-hrv-recovery-context',
    'scientific',
    'fact',
    'HRV reflects recovery context',
    'Heart rate variability can reflect stress and recovery state. Gaia Eyes uses HRV as one context signal, not a score of health or a standalone answer.',
    296
  ),
  (
    'scientific-resting-heart-baseline',
    'scientific',
    'fact',
    'Baselines beat averages',
    'Resting heart rate is most useful when compared with your own usual range. A personal baseline keeps Gaia Eyes from treating every normal variation as meaningful.',
    295
  ),
  (
    'scientific-respiratory-rate-context',
    'scientific',
    'fact',
    'Breathing trends add context',
    'Respiratory rate can shift with sleep, activity, stress, or illness. Gaia Eyes uses it carefully as background context when patterns repeat.',
    294
  ),
  (
    'scientific-temperature-swings',
    'scientific',
    'fact',
    'Temperature swings matter',
    'Rapid temperature changes may overlap with pain, sleep, or energy logs for some users. Gaia Eyes looks for repeated timing instead of assuming a cause.',
    293
  ),
  (
    'scientific-solar-wind-watch',
    'scientific',
    'fact',
    'Solar wind is watched',
    'Solar wind speed and density describe changing space weather near Earth. Gaia Eyes includes them as environmental context, especially when geomagnetic activity rises.',
    292
  ),
  (
    'scientific-kp-field-activity',
    'scientific',
    'fact',
    'Kp tracks magnetic activity',
    'Kp is a global index of geomagnetic activity. It can help frame broad space weather conditions, but it does not explain any single symptom by itself.',
    291
  ),
  (
    'scientific-bz-orientation',
    'scientific',
    'fact',
    'Bz helps frame storms',
    'The Bz direction helps describe how solar wind may connect with our magnetic field. Gaia Eyes keeps it as context, not certainty.',
    290
  ),
  (
    'scientific-schumann-exploratory',
    'scientific',
    'fact',
    'Schumann is exploratory',
    'Schumann resonance data is included as environmental context. Research around human effects is still being explored, so Gaia Eyes uses careful language here.',
    289
  ),
  (
    'scientific-log-same-day',
    'scientific',
    'tip',
    'Log while it is fresh',
    'Same-day symptom logs reduce memory gaps. Even a quick severity update helps Gaia Eyes compare your body state with conditions from the same window.',
    288
  ),
  (
    'scientific-severity-scale',
    'scientific',
    'tip',
    'Severity gives scale',
    'A mild symptom and a severe one should not teach the system the same thing. Severity helps Gaia Eyes weigh repeated patterns more usefully.',
    287
  ),
  (
    'scientific-follow-ups',
    'scientific',
    'tip',
    'Follow-ups fill gaps',
    'When you update a symptom later, Gaia Eyes can see whether the day eased, stayed the same, or intensified. That feedback improves the pattern loop.',
    286
  ),
  (
    'scientific-repeat-patterns',
    'scientific',
    'fact',
    'Patterns need repeats',
    'One unusual day is not enough to prove a relationship. Gaia Eyes looks for repeated overlaps across logs, signals, and timing before surfacing stronger context.',
    285
  ),
  (
    'scientific-correlation-not-cause',
    'scientific',
    'fact',
    'Overlap is not proof',
    'A signal and symptom can appear together without one causing the other. Gaia Eyes presents overlaps as observations, not medical conclusions.',
    284
  ),
  (
    'scientific-location-weather',
    'scientific',
    'tip',
    'Location sharpens context',
    'Local weather, pressure, air quality, and allergens depend on place. Keeping location context current helps Gaia Eyes compare your logs with nearby conditions.',
    283
  ),
  (
    'scientific-permissions-control',
    'scientific',
    'tip',
    'Permissions stay in your hands',
    'Health and location permissions add context only when enabled. You can keep Gaia Eyes useful with logs alone or improve the read with more signal access.',
    282
  ),
  (
    'scientific-cycle-optional',
    'scientific',
    'tip',
    'Cycle context is optional',
    'If enabled, menstrual cycle context can help Gaia Eyes avoid over-crediting the environment for patterns that may line up with body rhythm changes.',
    281
  ),
  (
    'scientific-not-diagnostic',
    'scientific',
    'fact',
    'Not a diagnosis tool',
    'Gaia Eyes is designed for observation and pattern awareness. It does not diagnose conditions, predict outcomes with certainty, or replace medical care.',
    280
  ),
  (
    'scientific-evidence-aware',
    'scientific',
    'fact',
    'Evidence stays careful',
    'Some signals have stronger research support than others. Gaia Eyes uses terms like may overlap, associated with, and still being explored for that reason.',
    279
  ),
  (
    'scientific-personal-history',
    'scientific',
    'fact',
    'Your history changes weight',
    'A signal that matters for one person may not matter for another. Gaia Eyes gives more visibility to conditions that repeatedly overlap with your own logs.',
    278
  ),
  (
    'scientific-quiet-days-count',
    'scientific',
    'tip',
    'Quiet days count too',
    'Logging low-symptom or steady days helps build a baseline. Gaia Eyes needs calm days as much as rough days to tell what is unusual for you.',
    277
  ),
  (
    'scientific-weather-fronts-stack',
    'scientific',
    'fact',
    'Weather signals can stack',
    'Pressure, humidity, temperature, and wind can move together. Gaia Eyes looks at the combined context instead of treating every signal as separate proof.',
    276
  ),
  (
    'scientific-air-pollen-stack',
    'scientific',
    'fact',
    'Air and pollen can stack',
    'Smoke, ozone, fine particles, and allergens may overlap with similar logs. Seeing them together helps Gaia Eyes keep the explanation practical.',
    275
  ),
  (
    'scientific-sleep-debt-blurs',
    'scientific',
    'fact',
    'Sleep debt can blur signals',
    'When recovery is already low, many environmental patterns can look louder than they are. Sleep context helps Gaia Eyes avoid over-reading the day.',
    274
  ),
  (
    'scientific-notes-add-detail',
    'scientific',
    'tip',
    'Notes add useful detail',
    'A short note about travel, stress, meals, or exposure can explain a day better than a metric alone. Notes help Gaia Eyes separate context from noise.',
    273
  ),
  (
    'scientific-feedback-priority',
    'scientific',
    'tip',
    'Feedback tunes priority',
    'When you confirm whether an insight felt useful, Gaia Eyes can learn which signals deserve attention and which should stay in the background.',
    272
  ),
  (
    'scientific-outlook-not-certainty',
    'scientific',
    'fact',
    'Outlooks are not certainty',
    'Future context is a forecast of conditions, not a prediction of how you will feel. Your logs decide whether a signal becomes personally meaningful.',
    271
  ),
  (
    'mystical-day-has-layers',
    'mystical',
    'message',
    'The day has layers',
    'Gaia watches the sky, the air, and your own notes like parts of one landscape. A pattern is not a prophecy; it is a trail marker.',
    260
  ),
  (
    'mystical-body-keeps-weather',
    'mystical',
    'message',
    'Your body keeps weather',
    'Some days carry pressure, heat, dust, or restless sleep in the background. Notice what your body reports, then let time show what repeats.',
    259
  ),
  (
    'mystical-return-baseline',
    'mystical',
    'message',
    'Return to your baseline',
    'A loud signal does not mean you must brace for impact. Gaia Eyes looks for your steady place first, then compares the day with that rhythm.',
    258
  ),
  (
    'mystical-sky-does-not-command',
    'mystical',
    'message',
    'The sky does not command',
    'Solar weather may color the wider field, but it does not decide your day. Gaia keeps it as context beside sleep, logs, and lived experience.',
    257
  ),
  (
    'mystical-air-as-messenger',
    'mystical',
    'message',
    'The air carries clues',
    'Air quality, pollen, and weather can leave small tracks. Gaia Eyes gathers those clues gently and waits for your own pattern before naming them.',
    256
  ),
  (
    'mystical-pressure-tide',
    'mystical',
    'message',
    'Pressure moves like tide',
    'When pressure rises or falls, some bodies may feel the shift. Gaia Eyes watches the tide without claiming it explains every wave.',
    255
  ),
  (
    'mystical-rest-is-signal',
    'mystical',
    'message',
    'Rest is a signal too',
    'Sleep is not just a reset; it is part of the story Gaia reads. A rough night can make every other signal feel louder.',
    254
  ),
  (
    'mystical-quiet-days-teach',
    'mystical',
    'message',
    'Quiet days teach Gaia',
    'Steady days are not empty. They help Gaia Eyes learn what your normal rhythm feels like, so unusual patterns stand out with more care.',
    253
  ),
  (
    'mystical-earth-heartbeat-care',
    'mystical',
    'message',
    'Earth rhythm stays careful',
    'Resonance data can be meaningful to watch, but the human story is still being explored. Gaia keeps this signal gentle and observational.',
    252
  ),
  (
    'mystical-compass-not-oracle',
    'mystical',
    'message',
    'A compass, not an oracle',
    'Gaia Eyes points toward possible context. It does not announce fate, diagnose illness, or turn one strange day into a certainty.',
    251
  ),
  (
    'mystical-journal-as-lantern',
    'mystical',
    'message',
    'Your log is a lantern',
    'A quick note can light up what numbers miss: travel, stress, smoke, meals, or heavy effort. Small details help Gaia read the path.',
    250
  ),
  (
    'mystical-energy-weather',
    'mystical',
    'message',
    'Energy has weather',
    'Your usable energy can rise and fall with sleep, strain, and the environment. Gaia watches for rhythms without forcing a single reason.',
    249
  ),
  (
    'mystical-patterns-grow-slowly',
    'mystical',
    'message',
    'Patterns grow slowly',
    'The first overlap is only a seed. Gaia Eyes waits for repeated seasons of data before lifting a signal into clearer view.',
    248
  ),
  (
    'mystical-gentle-field',
    'mystical',
    'message',
    'Keep the field gentle',
    'If a signal feels intense, the best response may still be simple: water, rest, fewer inputs, and a note for Gaia to compare later.',
    247
  ),
  (
    'mystical-symptom-weather-vane',
    'mystical',
    'message',
    'Symptoms are weather vanes',
    'A symptom log does not need to be perfect. It simply tells Gaia where the wind seemed to turn in your body that day.',
    246
  ),
  (
    'mystical-place-matters',
    'mystical',
    'message',
    'Place shapes the read',
    'The air around your home, work, or travel path can differ. Location context helps Gaia keep the landscape close to where you actually are.',
    245
  ),
  (
    'mystical-moon-as-marker',
    'mystical',
    'message',
    'Moonlight is a marker',
    'Lunar timing can be a rhythm note for comparison, not a command. Gaia only gives it meaning when your history suggests a repeat.',
    244
  ),
  (
    'mystical-magnetic-weather',
    'mystical',
    'message',
    'Magnetic weather is wide',
    'Geomagnetic activity belongs to the shared sky. Gaia Eyes watches it softly, then asks whether your own logs show any personal echo.',
    243
  ),
  (
    'mystical-small-check-in',
    'mystical',
    'message',
    'A small check-in is enough',
    'You do not need a long journal to teach Gaia. One clear check-in can help the system place today on your larger map.',
    242
  ),
  (
    'mystical-avoid-fear-loop',
    'mystical',
    'message',
    'No fear loop needed',
    'A strong environmental signal is not a warning by itself. Gaia Eyes is here to add context, not to make the day feel threatening.',
    241
  ),
  (
    'mystical-body-and-world',
    'mystical',
    'message',
    'Body and world converse',
    'Gaia Eyes listens for conversation between conditions and your logs. It stays curious, because conversation is not the same as proof.',
    240
  ),
  (
    'mystical-weather-front-passage',
    'mystical',
    'message',
    'Fronts pass through',
    'A weather front can change pressure, humidity, wind, and temperature together. Gaia watches the whole passage rather than one lonely number.',
    239
  ),
  (
    'mystical-breathe-before-meaning',
    'mystical',
    'message',
    'Breathe before meaning',
    'Not every signal needs a story today. Sometimes Gaia simply keeps watch while you give your body room to report honestly.',
    238
  ),
  (
    'mystical-clearer-air-read',
    'mystical',
    'message',
    'Clearer air, clearer read',
    'When smoke, pollen, or ozone shift, the background changes. Gaia Eyes marks those changes so your future patterns have better context.',
    237
  ),
  (
    'mystical-feedback-map',
    'mystical',
    'message',
    'Feedback refines the map',
    'When you tell Gaia whether an insight helped, the map gets less noisy. Your response teaches which paths are worth keeping visible.',
    236
  ),
  (
    'mystical-sleep-sets-sky',
    'mystical',
    'message',
    'Sleep sets the sky',
    'A short night can dim the whole inner sky. Gaia Eyes keeps sleep beside the other signals so the reading stays grounded.',
    235
  ),
  (
    'mystical-no-single-star',
    'mystical',
    'message',
    'No single star explains it',
    'Gaia does not ask one signal to explain your whole day. It looks for constellations: sleep, air, pressure, body logs, and time.',
    234
  ),
  (
    'mystical-horizon-not-answer',
    'mystical',
    'message',
    'The horizon is context',
    'Forecasts show the conditions ahead, not the shape of your body tomorrow. Gaia lets future signals stay as context until your logs respond.',
    233
  ),
  (
    'mystical-trust-the-repeat',
    'mystical',
    'message',
    'Trust the repeat',
    'A pattern earns attention by returning. Gaia Eyes gives more weight to signals that meet your logs again and again over time.',
    232
  ),
  (
    'mystical-grounded-curiosity',
    'mystical',
    'message',
    'Stay curious and grounded',
    'Gaia Eyes is built for noticing, not certainty. Let the app hold the wider context while you stay close to what you actually feel.',
    231
  ),
  (
    'all-log-before-memory-fades',
    'all',
    'tip',
    'Log before memory fades',
    'A quick same-day log is often more useful than a perfect note tomorrow. Fresh timing helps Gaia Eyes compare symptoms with the right signal window.',
    230
  ),
  (
    'all-location-unlocks-context',
    'all',
    'tip',
    'Location sharpens context',
    'Weather, pressure, AQI, and allergens are local. Keeping location context current helps the Home feed and Insights speak to the conditions around you.',
    229
  ),
  (
    'all-sleep-adds-recovery',
    'all',
    'tip',
    'Sleep adds recovery context',
    'Sleep data helps Gaia Eyes avoid over-crediting the environment on days when recovery was already low. Logs still work if sleep access is off.',
    228
  ),
  (
    'all-severity-adds-weight',
    'all',
    'tip',
    'Severity adds weight',
    'Severity tells Gaia Eyes whether a symptom was background noise or a major part of the day. That scale makes repeated patterns easier to compare.',
    227
  ),
  (
    'all-follow-up-after-change',
    'all',
    'tip',
    'Update when things change',
    'If a symptom eases or intensifies, a follow-up helps Gaia Eyes learn the shape of the day instead of only the first snapshot.',
    226
  ),
  (
    'all-context-flags-prevent-noise',
    'all',
    'tip',
    'Context flags reduce noise',
    'Travel, illness, heavy activity, smoke, or unusual stress can explain a lot. Flagging context helps Gaia Eyes avoid learning the wrong lesson.',
    225
  ),
  (
    'all-quiet-days-build-baseline',
    'all',
    'tip',
    'Quiet days build baseline',
    'Low-symptom days are useful data. They help Gaia Eyes understand your normal range so future unusual days have a clearer comparison.',
    224
  ),
  (
    'all-notes-capture-missing-context',
    'all',
    'tip',
    'Notes catch what metrics miss',
    'A short note can explain a signal that numbers cannot see, like a late meal, a hard workout, a smoky room, or an emotional day.',
    223
  ),
  (
    'all-use-consistent-symptoms',
    'all',
    'tip',
    'Use consistent symptom names',
    'Choosing the same symptom label over time helps Gaia Eyes compare like with like. Consistency makes patterns cleaner without extra effort.',
    222
  ),
  (
    'all-feedback-improves-ranking',
    'all',
    'tip',
    'Feedback improves ranking',
    'When an insight feels useful or off-base, your feedback helps Gaia Eyes decide what should appear more often and what should fade back.',
    221
  ),
  (
    'all-permissions-are-optional',
    'all',
    'tip',
    'Permissions are optional',
    'You control health and location access. More context can improve personalization, but Gaia Eyes still learns from the symptoms and check-ins you choose to log.',
    220
  ),
  (
    'all-one-card-per-day',
    'all',
    'tip',
    'One card per day',
    'The Home feed shows one unseen active item per day. If there is nothing new for your mode, the card stays hidden instead of repeating itself.',
    219
  ),
  (
    'all-review-insights-after-logging',
    'all',
    'tip',
    'Log, then review Insights',
    'Logging first gives Gaia Eyes fresh context. Reviewing Insights after that can make the patterns feel more relevant to the day you are actually having.',
    218
  ),
  (
    'all-watch-signal-stacks',
    'all',
    'tip',
    'Watch signal stacks',
    'Some days have more than one background shift: poor sleep, pressure change, pollen, or heat. Gaia Eyes looks for stacked context, not single-cause answers.',
    217
  ),
  (
    'all-change-mode-anytime',
    'all',
    'tip',
    'Mode changes presentation',
    'Scientific and Mystical modes use the same truth layer. Switching mode changes the wording, not the safety rules or the underlying signals.',
    216
  )
on conflict (slug) do update
set mode = excluded.mode,
    kind = excluded.kind,
    title = excluded.title,
    body = excluded.body,
    priority = excluded.priority,
    active = true,
    updated_at = now();

commit;
