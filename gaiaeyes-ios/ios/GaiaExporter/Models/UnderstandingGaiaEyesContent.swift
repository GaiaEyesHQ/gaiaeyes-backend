import Foundation

struct UnderstandingSource: Identifiable, Codable, Hashable {
    let id: String
    let title: String
    let url: String
    let label: String?
}

struct UnderstandingTopic: Identifiable, Codable, Hashable {
    let id: String
    let title: String
    let summaryLines: [String]
    let evidenceLabel: String?
    let sourceLinks: [UnderstandingSource]
}

struct UnderstandingCategory: Identifiable, Codable, Hashable {
    let id: String
    let title: String
    let summary: String
    let items: [String]
}

struct UnderstandingSourceGroup: Identifiable, Codable, Hashable {
    let id: String
    let title: String
    let description: String?
    let sources: [UnderstandingSource]
}

struct UnderstandingPageContent: Codable, Hashable {
    let title: String
    let subtitle: String
    let introLines: [String]
    let dataCategories: [UnderstandingCategory]
    let howItWorksSteps: [String]
    let limitations: [String]
    let researchTopics: [UnderstandingTopic]
    let sourceGroups: [UnderstandingSourceGroup]
    let futureNote: String?
}

enum UnderstandingGaiaEyesContent {
    static func page(mode: ExperienceMode, tone: ToneStyle) -> UnderstandingPageContent {
        let vocabulary = mode.copyVocabulary

        let title = "Understanding Gaia Eyes"
        let subtitle: String = {
            switch mode {
            case .scientific:
                return tone.resolveCopy(
                    straight: "What Gaia Eyes watches, how it learns, and why these signals matter.",
                    balanced: "A plain-language guide to the data, patterns, and context behind Gaia Eyes.",
                    humorous: "A plain-language guide to the data, patterns, and context behind Gaia Eyes."
                )
            case .mystical:
                return tone.resolveCopy(
                    straight: "A grounded guide to the signals, patterns, and context Gaia Eyes follows.",
                    balanced: "A grounded guide to the data, patterns, and context behind Gaia Eyes.",
                    humorous: "A grounded guide to the data, patterns, and context behind Gaia Eyes."
                )
            }
        }()

        let introLines: [String] = [
            tone.resolveCopy(
                straight: "Gaia Eyes looks at environmental signals, body signals, and what you log so it can surface patterns that may matter for you over time.",
                balanced: "Gaia Eyes watches the conditions around you, the signals from your body, and how you say the day felt so it can surface patterns over time.",
                humorous: "Gaia Eyes watches the conditions around you, the signals from your body, and how you say the day felt so it can surface patterns over time."
            ),
            "It is designed to help you notice what may be shaping your day. It does not diagnose, prove causes, or claim certainty."
        ]

        let dataCategories: [UnderstandingCategory] = [
            UnderstandingCategory(
                id: "environment",
                title: "Environment",
                summary: tone.resolveCopy(
                    straight: "Outside-in signals give Gaia a map of the conditions around you before it compares them with your feedback.",
                    balanced: "Gaia starts with the conditions around you so it can compare your day with the wider environment.",
                    humorous: "Gaia starts with the conditions around you so it can compare your day with the wider environment."
                ),
                items: [
                    "Space weather",
                    vocabulary.geomagneticLabel,
                    vocabulary.solarWindLabel,
                    vocabulary.schumannLabel,
                    "Atmospheric pressure",
                    "Air quality",
                    "Allergens and pollen",
                    "Temperature swings",
                    "Local weather context"
                ]
            ),
            UnderstandingCategory(
                id: "body",
                title: "Body Signals",
                summary: "These signals help Gaia tell the difference between a loud day outside and a body that may already be under strain or recovery.",
                items: [
                    "Heart rate",
                    "HRV",
                    "Sleep",
                    "Resting heart rate",
                    "Respiratory rate",
                    "SpO2 when available",
                    "Blood pressure when available",
                    "Wrist temperature when available",
                    "Cycle tracking when enabled",
                    "Steps and activity context"
                ]
            ),
            UnderstandingCategory(
                id: "input",
                title: "Your Input",
                summary: "Your own logs tell Gaia what actually mattered. That feedback is what turns raw signals into something personal.",
                items: [
                    "Symptoms you log",
                    "Severity",
                    "Symptom follow-ups",
                    "Daily check-ins",
                    "Energy and usable-energy feedback",
                    "Notes and journal context"
                ]
            )
        ]

        let howItWorksSteps: [String] = [
            "Gaia Eyes watches environmental and body signals.",
            "You log how you feel through symptoms, check-ins, and quick feedback.",
            "Gaia looks for repeated overlap across those signals and your own patterns over time.",
            "Signals that appear more relevant for you become more visible in the app.",
            "Ongoing feedback helps Gaia get more useful without pretending certainty."
        ]

        let limitations: [String] = [
            "Gaia Eyes is not a medical diagnosis tool.",
            "It does not predict outcomes with certainty.",
            "It does not prove that a signal caused a symptom.",
            "It is designed to help you observe patterns, context, and timing."
        ]

        let pressureTopic = UnderstandingTopic(
            id: "pressure_headaches",
            title: "Pressure & Headaches",
            summaryLines: [
                "Pressure shifts have been linked to migraine or headache flare-ups in some studies, especially for people who already consider themselves weather-sensitive.",
                "Sensitivity varies a lot from person to person, so Gaia treats pressure as context to watch, not proof of cause."
            ],
            evidenceLabel: "Evidence mixed",
            sourceLinks: [
                UnderstandingSource(
                    id: "weather-migraine-meta",
                    title: "Association between weather conditions and migraine: a systematic review and meta-analysis",
                    url: "https://pubmed.ncbi.nlm.nih.gov/40246758/",
                    label: "View source"
                )
            ]
        )

        let airQualityTopic = UnderstandingTopic(
            id: "air_quality",
            title: "Air Quality & Fatigue / Inflammation",
            summaryLines: [
                "Poorer air quality has been associated with inflammatory markers, headaches, and lower-quality sleep in some populations.",
                "That does not mean AQI explains every fatigue or brain-fog day, but it can be useful context when symptoms cluster on dirtier-air days."
            ],
            evidenceLabel: "Observational context",
            sourceLinks: [
                UnderstandingSource(
                    id: "air-inflammation-meta",
                    title: "Association between gaseous air pollutants and biomarkers of systemic inflammation: A systematic review and meta-analysis",
                    url: "https://pubmed.ncbi.nlm.nih.gov/34634403/",
                    label: "View source"
                ),
                UnderstandingSource(
                    id: "air-sleep-meta",
                    title: "Air pollution and sleep health in middle-aged and older adults: A systematic review and meta-analysis",
                    url: "https://pubmed.ncbi.nlm.nih.gov/40730110/",
                    label: "Learn more"
                )
            ]
        )

        let allergenTopic = UnderstandingTopic(
            id: "allergens",
            title: "Allergens & Sinus / Fatigue",
            summaryLines: [
                "Higher pollen or allergen load may line up with sinus pressure, headaches, cough, or low-energy days, especially in people with allergic rhinitis.",
                "Local exposure can change quickly by season, wind, and source type, so Gaia treats allergens as nearby context rather than certainty."
            ],
            evidenceLabel: "Stronger for sinus symptoms",
            sourceLinks: [
                UnderstandingSource(
                    id: "allergic-rhinitis-review",
                    title: "Allergic Rhinitis: A Review",
                    url: "https://pubmed.ncbi.nlm.nih.gov/38470381/",
                    label: "View source"
                )
            ]
        )

        let sleepTopic = UnderstandingTopic(
            id: "sleep_recovery",
            title: "Sleep & Recovery",
            summaryLines: [
                "Sleep duration, timing, and regularity are associated with recovery, mood, and day-to-day resilience, which is why Gaia pays close attention to sleep patterns.",
                "Sleep is one of Gaia's clearest body-context signals, but it still sits alongside your own logs and the day's environment."
            ],
            evidenceLabel: "Well-established context",
            sourceLinks: [
                UnderstandingSource(
                    id: "sleep-regularity-review",
                    title: "Sleep regularity as an important component of sleep hygiene: a systematic review",
                    url: "https://pubmed.ncbi.nlm.nih.gov/41259946/",
                    label: "View source"
                )
            ]
        )

        let temperatureTopic = UnderstandingTopic(
            id: "temperature_pain",
            title: "Temperature & Pain",
            summaryLines: [
                "Some people report more pain or stiffness during temperature swings or certain weather patterns, but the research is mixed and differs by condition.",
                "Gaia watches temperature shifts because they may be one part of a wider pattern, especially when they repeat next to pain logs."
            ],
            evidenceLabel: "Evidence mixed",
            sourceLinks: [
                UnderstandingSource(
                    id: "weather-pain-review",
                    title: "Are weather conditions associated with chronic musculoskeletal pain? Review of results and methodologies",
                    url: "https://pubmed.ncbi.nlm.nih.gov/32195783/",
                    label: "View source"
                )
            ]
        )

        let geomagneticTopic = UnderstandingTopic(
            id: "geomagnetic_sleep_mood",
            title: mode == .scientific
                ? "Geomagnetic / Solar Activity & Mood / Sleep"
                : "\(vocabulary.geomagneticLabel) / Solar Activity & Mood / Sleep",
            summaryLines: [
                "Some human studies have reported links between geomagnetic activity and measures like HRV or melatonin-related physiology, while other findings weaken after stricter analysis.",
                "Gaia includes this context as exploratory background, not as a settled explanation for mood or sleep changes."
            ],
            evidenceLabel: "Exploratory",
            sourceLinks: [
                UnderstandingSource(
                    id: "geomagnetic-hrv",
                    title: "Exploring the relationship between geomagnetic activity and human heart rate variability",
                    url: "https://pubmed.ncbi.nlm.nih.gov/32306151/",
                    label: "View source"
                ),
                UnderstandingSource(
                    id: "geomagnetic-melatonin",
                    title: "Geomagnetic activity and human melatonin metabolite excretion",
                    url: "https://pubmed.ncbi.nlm.nih.gov/18472329/",
                    label: "Learn more"
                )
            ]
        )

        let schumannTopic = UnderstandingTopic(
            id: "schumann_context",
            title: mode == .scientific
                ? "Schumann / Resonance Context"
                : "\(vocabulary.schumannLabel) Context",
            summaryLines: [
                "Schumann resonance is a real Earth-ionosphere signal generated mostly by global lightning activity.",
                "Gaia treats it as environmental context; claims about direct human effects are still being explored and should be read carefully."
            ],
            evidenceLabel: "Highly exploratory",
            sourceLinks: [
                UnderstandingSource(
                    id: "schumann-review",
                    title: "ELF Electromagnetic Waves from Lightning: The Schumann Resonances",
                    url: "https://www.mdpi.com/2073-4433/7/9/116",
                    label: "View source"
                )
            ]
        )

        let researchTopics = [
            pressureTopic,
            airQualityTopic,
            allergenTopic,
            sleepTopic,
            temperatureTopic,
            geomagneticTopic,
            schumannTopic
        ]

        let sourceGroups: [UnderstandingSourceGroup] = [
            UnderstandingSourceGroup(
                id: "operational_data",
                title: "Operational data sources",
                description: "Gaia combines live provider data with the health and feedback data you allow it to use.",
                sources: [
                    UnderstandingSource(
                        id: "swpc",
                        title: "NOAA Space Weather Prediction Center",
                        url: "https://www.swpc.noaa.gov/about-space-weather",
                        label: "Learn more"
                    ),
                    UnderstandingSource(
                        id: "nws",
                        title: "National Weather Service",
                        url: "https://www.weather.gov/",
                        label: "Learn more"
                    ),
                    UnderstandingSource(
                        id: "airnow",
                        title: "AirNow AQI",
                        url: "https://www.airnow.gov/about-airnow/",
                        label: "Learn more"
                    ),
                    UnderstandingSource(
                        id: "google-pollen",
                        title: "Google Pollen API Overview",
                        url: "https://developers.google.com/maps/documentation/pollen/overview",
                        label: "Learn more"
                    ),
                    UnderstandingSource(
                        id: "healthkit",
                        title: "Apple HealthKit",
                        url: "https://developer.apple.com/documentation/healthkit",
                        label: "Learn more"
                    )
                ]
            )
        ] + researchTopics.map {
            UnderstandingSourceGroup(
                id: "sources-\($0.id)",
                title: $0.title,
                description: "Research context used in this topic summary.",
                sources: $0.sourceLinks
            )
        }

        let futureNote = "Gaia Eyes already learns from your own feedback over time. Future versions may also surface anonymized community patterns when enough data exists, but that would still be observational rather than proof."

        return UnderstandingPageContent(
            title: title,
            subtitle: subtitle,
            introLines: introLines,
            dataCategories: dataCategories,
            howItWorksSteps: howItWorksSteps,
            limitations: limitations,
            researchTopics: researchTopics,
            sourceGroups: sourceGroups,
            futureNote: futureNote
        )
    }
}
