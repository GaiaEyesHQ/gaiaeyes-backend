# Gaia Eyes App & Web Unification Roadmap  
*Version 1.0 — 2025-11-09*

## Vision  
Enable a unified data experience across the web and mobile, aligned on a single source of truth; launch iOS v1.0 first, then expand to additional platforms with deeper personalization and alerting.

---

## Timeline & Phases  

### Phase 1: Core Stabilization & iOS MVP Launch (Weeks 0-8)  
**Goal:** Lock in stable architecture, migrate key data flows, prepare iOS app for TestFlight.  
- Migrate remaining JSON feeds (e.g., space_news, schumann_metrics) into backend DB + API.  
- Confirm all API endpoints used by mobile share the same canonical sources as the website.  
- Finalize iOS UI/UX: scoped user flows, background sync, caching, fallback logic.  
- Internal TestFlight build (10-20 testers).  
- Prepare App Store metadata: app icon, store description, screenshots, privacy policy.  
- QA & bug-fix sprint.

### Phase 2: External Beta & Feature Parity (Weeks 9-16)  
**Goal:** Broaden test user base, align feature set with website, gather feedback.  
- Release iOS external beta (TestFlight) to broader audience.  
- Add mobile views for web data flows: Daily Features, Space Weather Dashboard, Schumann Resonance, Newsfeed.  
- Optimize mobile performance: offline cache, data freshness badge, push alerts.  
- Integrate analytics and crash-monitoring.  
- Implement feedback-driven improvements; finalize iOS v1 readiness.

### Phase 3: Official iOS Launch & Live Monitoring (Weeks 17-24)  
**Goal:** Publish iOS app publicly, monitor uptake, prepare for platform expansion.  
- Submit to Apple App Store; manage review process; publish.  
- Monitor key metrics: downloads, retention, crash rate, feature usage.  
- Release Version 1.1: enhancements & bug fixes.  
- Begin planning Android/cross-platform expansion.

### Phase 4: Cross-Platform Expansion & Unified Data Experience (Month 7+)  
**Goal:** Decide Android/native or cross-platform scenario; fully unify data and implement advanced features.  
- Choose platform strategy: native Android only vs cross-platform (e.g., Flutter/React Native).  
- Complete migration of all web-only data flows into the backend DB/API so both web & mobile share the same model.  
- Launch Android or multi-platform version.  
- Introduce advanced features: premium alerts, full offline mode, social sharing, personalization.

---

## Platform Strategy  
- **iOS first:** Focus on Swift/iOS only for v1.0 → reduced risk, faster path to market.  
- **Android or cross-platform second:** After iOS launch, evaluate cost/benefit for either native Android or adopt cross-platform framework.  
- Avoid launching both platforms simultaneously for the v1 release to maintain focus and quality.

---

## Milestones & Owners  
| Milestone | Target Date | Owner |
|-----------|-------------|--------|
| Backend data migration (JSON → DB/API) | Week 4 | Data Engineering / Backend Team |
| iOS scoped-user header + caching logic complete | Week 6 | iOS Engineering |
| Internal iOS TestFlight build | Week 7 | QA / iOS Team |
| External Beta release | Week 10 | Product / iOS Team |
| App Store submission | Week 17 | iOS Team / Product |
| Android strategy decision | Week 20 | Product / Engineering |
| Cross-platform or native Android build start | Month 8 | Engineering |

---

## Key Dependencies & Risks  
- Reliable backend connectivity (direct PG pooler on port 5432) remains essential — any reversion to 6543 pooler could destabilize mobile/web sync.  
- Data migration complexity — migrating JSON-only flows to DB may expose schema changes or data gaps.  
- Mobile performance & caching — risk of hangs/freezes if background sync is not optimized for lower-spec devices.  
- App Store delays or rejection — ensure privacy policy and health data handling are compliant.  
- Resource allocation — ensure engineering and QA time are protected, especially as multi-platform work begins.

---

## Success Metrics  
- iOS v1.0 published with ≤ 5% crash rate within first 500 users.  
- Feature parity: > 80% of web dashboard cards available in mobile app.  
- Data consistency: mobile and web show matching key metrics (Kp, Bz, steps, sleep) within ±5%.  
- User retention: Day 1 retention > 40%, Day 7 > 20% for beta testers.

---

## Review Cadence  
- Update this roadmap monthly to reflect progress, risks, and shifted timelines.  [oai_citation:0‡ProductPlan](https://www.productplan.com/learn/creating-a-roadmap/?utm_source=chatgpt.com)  
- Communicate any changes to all stakeholders and maintain version control.

---

_End of document_  