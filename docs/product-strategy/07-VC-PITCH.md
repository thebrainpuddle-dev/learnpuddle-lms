# LearnPuddle — VC Pitch Deck (Narrative)

---

## The Problem

Every organization trains people. Schools train teachers. Gyms train members. Companies train employees. Coaching centers train students.

**How do they do it today?**

- WhatsApp groups + Google Drive + Excel spreadsheets
- Or enterprise LMS platforms that cost $25K-$500K/year
- Or bolted-on LMS modules in HR software (Darwinbox partners with Docebo because they couldn't build one)

**There is no affordable, modern, gamified training platform that any organization can use.**

The $31B global LMS market is split between:
- **Enterprise giants** (Cornerstone, Docebo, SAP) → too expensive, 3-6 month implementation
- **Course marketplaces** (Udemy, Coursera) → B2C, you don't own the learner relationship
- **Open source** (Moodle) → needs developers, no gamification, ugly UX
- **HR bolt-ons** (Darwinbox, Keka) → shallow, training is an afterthought

**Nobody serves the 90% of organizations in the middle.**

---

## The Solution

LearnPuddle is a **training platform that any organization can launch in 5 minutes**.

1. Sign up → pick your vertical (school, gym, corporate, coaching)
2. Get a branded training instance on your subdomain
3. Upload courses, assign learners, track progress
4. AI auto-generates quizzes from video content
5. Gamification (XP, badges, streaks, leaderboards) drives engagement
6. Certificates, reports, and compliance tracking built in

**It's the training platform that Darwinbox, Mindbody, and Canvas should have built — but didn't.**

---

## Why Now?

1. **NEP 2020** mandates continuous teacher PD tracking → 1.5M schools in India need a tool
2. **AI** makes content creation 10x faster → auto-transcribe, auto-quiz, auto-skill-mapping
3. **Post-COVID** digital training is permanent → organizations won't go back to classroom-only
4. **Gamification** is proven → 52% adoption in enterprise, 3x engagement lift
5. **India SaaS** is maturing → Darwinbox, Zoho, Freshworks proved Indian B2B can scale globally

---

## Market

| Metric | Value |
|--------|-------|
| Global LMS Market (2026) | $31-37B |
| India LMS Market (2025) | $1.07B |
| India LMS Market (2033) | $3-5B (17-22% CAGR) |
| India Corporate Training | $12.2B (2025) |
| K-12 Schools in India | 1.5M+ |
| Teachers in India | 9.7M+ |
| Organized Gyms/Studios in India | 30,000+ |

**TAM**: $5B (India LMS + adjacent training market)
**SAM**: $500M (SMB + education segment, affordable LMS)
**SOM**: $50M (10,000 organizations at $5K avg annual spend)

---

## Product (Already Built)

| Capability | Status |
|-----------|--------|
| Multi-tenant architecture (branded instances) | Production |
| Video streaming (HLS + adaptive bitrate) | Production |
| AI transcription + auto-quiz generation | Production |
| Full gamification (XP, badges, streaks, leaderboards) | Production |
| Skills tracking + gap analysis | Production |
| Certificate generation (PDF) | Production |
| Stripe billing (4 plan tiers) | Production |
| SSO (Google) + 2FA (TOTP) | Production |
| Reports + analytics + CSV export | Production |
| Discussion forums | Production |
| PWA (installable mobile app) | Production |
| 13 Django apps, 30+ frontend pages | Production |

**This is not a prototype. This is a production-ready platform.**

---

## Business Model

**SaaS subscription per organization:**

| Plan | Price (India) | Target |
|------|--------------|--------|
| Free | ₹0 | Small orgs (<10 learners) |
| Starter | ₹2,499/mo ($30) | Small schools, solo trainers |
| Pro | ₹7,999/mo ($95) | Mid-size schools, gyms |
| Business | ₹19,999/mo ($240) | Large schools, companies |
| Enterprise | ₹49,999+/mo ($600+) | School chains, corporations |

**Future revenue streams**: Template marketplace (15-20% take), content marketplace (20-30% take), AI credits (usage-based), embedded fintech.

**Unit economics target**: 80%+ gross margin, <2 month CAC payback, 110%+ NRR.

---

## Traction / Milestones

- Full product built (13 backend apps, 30+ pages, video pipeline, gamification, billing)
- Production deployed on DigitalOcean + Cloudflare
- Multi-tenant architecture proven (tenant isolation, branded subdomains)
- AI pipeline working end-to-end (upload → transcribe → quiz → skill map)
- First school client in pipeline (Hyderabad)

---

## Competitive Advantage

### What We Have That Others Don't

1. **True multi-tenancy from day 1** — each org gets isolated, branded instance. Competitors offer "portals" (filtered views). Retrofitting takes 6-12 months.

2. **AI-native pipeline** — video → transcript → quiz → skill map. No competitor in our price range has this.

3. **Gamification as core** — not badges bolted on. Full XP system, streaks with freeze mechanics, daily quests, 10 proficiency levels, leaderboards. This is engagement infrastructure.

4. **10-100x cheaper than enterprise** — ₹2,499/mo vs $25K+/year. Schools and gyms can afford us.

5. **Vertical templates on horizontal architecture** — same platform serves schools today, gyms tomorrow, corporate next quarter. No rewrite needed.

### What's Hard to Copy

- Multi-tenant architecture (6-12 months to retrofit)
- AI pipeline depth (video → transcript → quiz → skill → certificate)
- Gamification system (XP ledger, streak mechanics, badge criteria engine)
- India-first pricing with production-ready product

---

## Team

*(To be filled — founder backgrounds, domain expertise, technical capabilities)*

---

## Go-to-Market

**Year 1**: India schools (Hyderabad/Bangalore). Founder-led sales. 50 paying schools.

**Year 2**: Add gym + corporate templates. Inside sales team. 500 paying orgs.

**Year 3**: School chains + state govt pilots. SEA/Middle East expansion. 3,000 orgs.

**Year 4+**: Template marketplace. Content marketplace. 10,000+ orgs.

**Follows Darwinbox playbook**: 4 years India-only focus → SEA → Middle East → Global.

---

## The Ask

*(To be filled — funding amount, use of funds, milestones)*

**Suggested allocation:**
- 40% Engineering (template builder, mobile app, vernacular support)
- 25% Sales & Marketing (founder-led → inside sales team)
- 20% Content (pre-built courses for each vertical)
- 15% Operations (support, infrastructure scaling)

---

## Comparable Exits / Valuations

| Company | Segment | Revenue | Valuation | Multiple |
|---------|---------|---------|-----------|----------|
| Darwinbox | HR Tech (India) | ~$100M ARR | $1.04B | 10x |
| Docebo | Enterprise LMS | ~$200M ARR | ~$2B | 10x |
| Veeva | Vertical SaaS (Life Sciences) | $2.4B ARR | $35B | 15x |
| ServiceTitan | Vertical SaaS (Home Services) | ~$700M ARR | $9B | 13x |
| Mindbody | Wellness/Fitness SaaS | ~$300M ARR | $1.9B (takeout) | 6x |

At 10x revenue multiple:
- ₹120Cr ARR ($14.4M) = **$144M valuation** (Series B)
- ₹360Cr ARR ($43M) = **$430M valuation** (Series C)
