# LearnPuddle — Business Model & Pricing

---

## Revenue Model: SaaS Subscription + Usage

### Primary Revenue: Per-Organization Subscription

Each organization (school, gym, company) pays a monthly fee for their branded LearnPuddle instance.

| Plan | Price (India) | Price (Global) | Target |
|------|--------------|----------------|--------|
| **Free** | ₹0 | $0 | Individuals, tiny orgs (<10 learners) |
| **Starter** | ₹2,499/mo | $30/mo | Small schools, solo trainers (≤50 learners) |
| **Pro** | ₹7,999/mo | $95/mo | Mid-size schools, gyms (≤200 learners) |
| **Business** | ₹19,999/mo | $240/mo | Large schools, companies (≤500 learners) |
| **Chain/Enterprise** | ₹49,999+/mo | $600+/mo | Multi-location, school chains, corporations |
| **Custom** | Quote | Quote | State govts, large chains, 1000+ learners |

### Plan Limits

| Feature | Free | Starter | Pro | Business | Enterprise |
|---------|------|---------|-----|----------|------------|
| Learners | 10 | 50 | 200 | 500 | Unlimited |
| Courses | 3 | 15 | Unlimited | Unlimited | Unlimited |
| Storage | 500MB | 5GB | 25GB | 100GB | Custom |
| Video upload | No | 5 videos | Unlimited | Unlimited | Unlimited |
| AI quiz gen | No | 3/mo | Unlimited | Unlimited | Unlimited |
| Gamification | Basic XP | Full | Full | Full | Full |
| Custom domain | No | No | Yes | Yes | Yes |
| SSO/2FA | No | No | Yes | Yes | Yes |
| White-label | No | No | No | Yes | Yes |
| API access | No | No | No | Yes | Yes |
| Multi-location | No | No | No | No | Yes |
| Priority support | No | Email | Email | Priority | Dedicated |

### Pricing Philosophy

- **India pricing is 60-70% of global pricing** (purchasing power parity)
- **Free tier is generous** — this is the growth engine (Canva model)
- **No per-user fees** at lower tiers — organizations hate unpredictable bills
- **Per-org, not per-user** — aligns incentives (orgs WANT more users on the platform)

### Benchmarks

| Competitor | Comparable Tier | Price |
|-----------|----------------|-------|
| TalentLMS Core (50 users) | Starter | $69/mo |
| Thinkific Basic | Starter | $36/mo |
| LearnPuddle Starter | Starter | **$30/mo** |
| Darwinbox (50 employees) | Pro | ~$150-250/mo |
| LearnPuddle Pro (200 users) | Pro | **$95/mo** |
| Docebo (200 users) | Business | ~$2,000/mo |
| LearnPuddle Business (500 users) | Business | **$240/mo** |

---

## Secondary Revenue Streams (Phase 2+)

### 1. Template Marketplace (Year 2+)

Third-party creators build and sell vertical templates on LearnPuddle.

- Creator sets price ($49-$499 per template)
- LearnPuddle takes 15-20% platform fee
- Precedent: Shopify Themes, Canva Creator Program, WordPress Themes

### 2. Content Marketplace (Year 2+)

Pre-built course content sold to organizations.

- CBSE/ICSE PD courses, POSH compliance, fitness programs
- Content partners upload, organizations purchase
- LearnPuddle takes 20-30% marketplace fee

### 3. AI Credits (Usage-Based)

For heavy AI usage beyond plan limits:

- Additional AI quiz generation: ₹5/quiz ($0.06)
- Additional video transcription: ₹10/hour ($0.12)
- AI learning path recommendations: ₹2/recommendation
- Precedent: Canva AI credits, Cursor usage limits

### 4. Embedded Fintech (Year 3+)

Following the Toast/ServiceTitan playbook:

- Payment processing for course sales (if orgs sell courses externally)
- Certification verification as a service
- Insurance/compliance verification for regulated industries

---

## Unit Economics (Target)

| Metric | Target | Benchmark |
|--------|--------|-----------|
| Monthly ARPU | ₹8,000 ($96) | TalentLMS: ~$100 |
| Gross Margin | 80%+ | SaaS standard: 75-85% |
| CAC | ₹15,000 ($180) | India B2B SaaS: $100-300 |
| LTV | ₹2,88,000 ($3,456) | 36-month avg lifetime |
| LTV:CAC | 19:1 | Target: >3:1 |
| Monthly Churn | <3% | SMB SaaS: 3-5% |
| Net Revenue Retention | 110%+ | Expansion through upsells |
| Payback Period | <2 months | Target: <6 months |

### Infrastructure Cost Per Tenant

| Component | Monthly Cost |
|-----------|-------------|
| Compute (shared VPS slice) | ₹50-200 |
| Database (shared PostgreSQL) | ₹20-50 |
| Storage (S3/Spaces) | ₹10-100 (usage-based) |
| CDN bandwidth | ₹10-50 |
| Redis (shared) | ₹10-20 |
| **Total per tenant** | **₹100-420 ($1.20-$5)** |

At ₹2,499/mo Starter pricing, gross margin is **>95%** per tenant.

---

## Revenue Projections (Conservative)

### Schools-First Scenario

| Year | Paying Orgs | Avg MRR/Org | MRR | ARR |
|------|------------|-------------|-----|-----|
| Y1 | 50 | ₹4,000 | ₹2L | ₹24L ($29K) |
| Y2 | 500 | ₹6,000 | ₹30L | ₹3.6Cr ($430K) |
| Y3 | 3,000 | ₹8,000 | ₹2.4Cr | ₹28.8Cr ($3.5M) |
| Y4 | 10,000 | ₹10,000 | ₹10Cr | ₹120Cr ($14.4M) |
| Y5 | 25,000 | ₹12,000 | ₹30Cr | ₹360Cr ($43M) |

### Multi-Vertical Scenario (Schools + Gyms + Corporate)

| Year | Schools | Gyms | Corporate | Total Orgs | ARR |
|------|---------|------|-----------|-----------|-----|
| Y1 | 50 | — | — | 50 | ₹24L |
| Y2 | 400 | 100 | — | 500 | ₹3.6Cr |
| Y3 | 2,000 | 500 | 500 | 3,000 | ₹28.8Cr |
| Y4 | 5,000 | 2,000 | 3,000 | 10,000 | ₹120Cr |
| Y5 | 8,000 | 5,000 | 12,000 | 25,000 | ₹360Cr |

At ₹120Cr ARR ($14.4M) = strong Series A/B territory.
At ₹360Cr ARR ($43M) = Series C / pre-IPO territory.
