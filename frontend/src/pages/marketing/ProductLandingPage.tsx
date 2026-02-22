import React from 'react';
import { getBookDemoUrl, isExternalHttpUrl } from '../../config/platform';
import './ProductLandingPage.css';

const heroOutcomes = [
  'Launch multi-tenant learning programs in days, not quarters.',
  'Track completion, deadlines, certifications, and audit-ready evidence.',
  'Run one platform across schools, enterprises, and distributed teams.',
];

const platformPillars = [
  {
    title: 'Build Programs Fast',
    description:
      'Create role-based learning paths with video, documents, quizzes, assignments, and completion logic.',
    bullets: ['Reusable templates', 'Deadline + reminder automation', 'Mandatory milestone enforcement'],
  },
  {
    title: 'Deliver At Scale',
    description:
      'Roll out training by team, branch, campus, or region with tenant-safe data boundaries and delegated admin.',
    bullets: ['Tenant branding controls', 'Bulk enrollment and imports', 'Groups and cohort targeting'],
  },
  {
    title: 'Prove Outcomes',
    description:
      'Move from activity metrics to business impact with completion, proficiency, and compliance visibility.',
    bullets: ['Executive dashboards', 'Department and manager views', 'Exportable evidence reports'],
  },
  {
    title: 'Secure By Design',
    description:
      'Role-based permissions, strong auth controls, auditability, and operational readiness for enterprise buyers.',
    bullets: ['SSO and 2FA support', 'Centralized audit events', 'Environment and backup controls'],
  },
];

const solutionTracks = [
  {
    title: 'School Systems',
    subtitle: 'K-12, university, and academic groups',
    description:
      'Coordinate teacher development, curriculum enablement, and policy compliance across campuses from one command center.',
    outcomes: ['CPD and policy completion tracking', 'Principal/HOD visibility', 'Multi-school governance'],
  },
  {
    title: 'Corporate L&D',
    subtitle: 'People, operations, and compliance teams',
    description:
      'Standardize onboarding, SOP enablement, and recurring certifications with clear ownership and reminders.',
    outcomes: ['Faster onboarding ramp', 'Reduced compliance drift', 'Manager-level completion control'],
  },
  {
    title: 'Franchise Operations',
    subtitle: 'Retail, hospitality, and distributed teams',
    description:
      'Ship the same operational playbooks to every location while preserving local manager accountability.',
    outcomes: ['Consistent SOP adoption', 'Location comparison analytics', 'Branch-level training health'],
  },
  {
    title: 'Academies & Coaching',
    subtitle: 'Program-led learning businesses',
    description:
      'Monetize and operationalize blended learning with branded portals, structured milestones, and learner progression.',
    outcomes: ['Branded learner journey', 'Instructor workload reduction', 'Clear completion evidence'],
  },
];

const industryPrograms = [
  {
    title: 'Education',
    programs: ['Faculty development', 'Classroom technology enablement', 'Assessment moderation workflows'],
  },
  {
    title: 'Healthcare',
    programs: ['Clinical protocol updates', 'Mandatory recertification cycles', 'Multi-role competency checks'],
  },
  {
    title: 'BFSI',
    programs: ['Regulatory policy rollout', 'Branch onboarding', 'Periodic compliance attestations'],
  },
  {
    title: 'Manufacturing',
    programs: ['Plant safety training', 'Machine SOP rollout', 'Supervisor readiness pathways'],
  },
  {
    title: 'Hospitality',
    programs: ['Guest experience standards', 'Frontline service drills', 'New outlet launch onboarding'],
  },
  {
    title: 'Technology',
    programs: ['Sales enablement', 'Partner training', 'Release certification tracks'],
  },
];

const rolloutSteps = [
  {
    step: '01',
    title: 'Discovery Blueprint',
    description:
      'Map learner personas, compliance obligations, and success metrics. Align program owners and rollout phases.',
  },
  {
    step: '02',
    title: 'Tenant + Program Setup',
    description:
      'Configure domains, branding, permissions, cohorts, and baseline course architecture for each audience.',
  },
  {
    step: '03',
    title: 'Launch + Adoption',
    description:
      'Run pilot cohorts, tune reminder cadence, and finalize production workflows before broader rollout.',
  },
  {
    step: '04',
    title: 'Measure + Improve',
    description:
      'Use dashboard and completion evidence to continuously optimize pathways and tighten operational outcomes.',
  },
];

const trustControls = [
  'Role-based access controls across platform, tenant admin, and learner roles',
  'Authentication controls including session lifecycle handling and optional 2FA',
  'Tenant data isolation with domain-aware routing and scoped authorization',
  'Operational health checks and deployment verification workflow',
  'Audit-friendly reporting surfaces for progress, assignments, and completion events',
  'Security hardening baseline across headers, CSP, and environment-driven config',
];

const complianceRoadmap = [
  {
    standard: 'SOC 2 (Type I → Type II)',
    status: 'In Planning',
    detail: 'Control inventory, evidence automation, and policy program sequencing.',
  },
  {
    standard: 'ISO/IEC 27001',
    status: 'Gap Assessment',
    detail: 'ISMS scope definition, control mapping, risk register, and treatment plan.',
  },
  {
    standard: 'WCAG 2.2 AA',
    status: 'Active Improvements',
    detail: 'Form semantics, keyboard flows, contrast, and responsive usability hardening.',
  },
  {
    standard: 'LTI / SCORM Compatibility',
    status: 'Roadmap',
    detail: 'Interoperability expansion for third-party content and ecosystem integration.',
  },
];

const faqs = [
  {
    question: 'Who is LearnPuddle designed for?',
    answer:
      'Teams running structured learning programs across schools, enterprises, and distributed operations that need outcomes and auditability.',
  },
  {
    question: 'Can one platform support multiple organizations?',
    answer:
      'Yes. LearnPuddle supports tenant-level isolation with per-organization branding, user management, and domain-aware access.',
  },
  {
    question: 'How do reminders and deadlines work?',
    answer:
      'Programs can enforce due dates with automated reminders and targeted follow-ups by role, cohort, or selected users.',
  },
  {
    question: 'What does the demo include?',
    answer:
      'A role-specific walkthrough of admin workflows, learner experience, analytics, and rollout plan recommendations for your use case.',
  },
  {
    question: 'Can we use this on mobile devices?',
    answer:
      'Yes. The product and marketing experience are optimized for modern desktop and mobile browsers with responsive layouts.',
  },
];

function CTAButton({
  href,
  children,
  className,
}: {
  href: string;
  children: React.ReactNode;
  className?: string;
}) {
  const isExternal = isExternalHttpUrl(href);
  return (
    <a
      href={href}
      className={className}
      target={isExternal ? '_blank' : undefined}
      rel={isExternal ? 'noreferrer' : undefined}
    >
      {children}
    </a>
  );
}

function SectionHeader({
  id,
  kicker,
  title,
  description,
}: {
  id?: string;
  kicker: string;
  title: string;
  description?: string;
}) {
  return (
    <div className="lp-section-head" id={id}>
      <p className="lp-kicker">{kicker}</p>
      <h2>{title}</h2>
      {description ? <p className="lp-section-description">{description}</p> : null}
    </div>
  );
}

export const ProductLandingPage: React.FC = () => {
  const bookDemoUrl = getBookDemoUrl();

  return (
    <div className="lp-page">
      <div className="lp-bg-shape lp-bg-shape-a" />
      <div className="lp-bg-shape lp-bg-shape-b" />

      <header className="lp-header">
        <div className="lp-container lp-header-inner">
          <a href="/" className="lp-logo" aria-label="LearnPuddle Home">
            LearnPuddle
          </a>
          <nav className="lp-nav" aria-label="Primary">
            <a href="#platform">Platform</a>
            <a href="#solutions">Solutions</a>
            <a href="#industries">Industries</a>
            <a href="#security">Security</a>
            <a href="#demo">Demo</a>
            <a href="#faq">FAQ</a>
          </nav>
          <div className="lp-header-actions">
            <CTAButton href={bookDemoUrl} className="lp-btn lp-btn-primary">
              Book Demo
            </CTAButton>
          </div>
        </div>
      </header>

      <main>
        <section className="lp-hero">
          <div className="lp-container lp-hero-grid">
            <div className="lp-hero-copy">
              <p className="lp-pill">Enterprise Learning Platform</p>
              <h1>Run every learning program from one operational system.</h1>
              <p>
                LearnPuddle helps you launch, manage, and prove learning outcomes across schools,
                teams, and distributed operations without platform sprawl.
              </p>
              <ul className="lp-hero-outcomes">
                {heroOutcomes.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
              <div className="lp-cta-row">
                <CTAButton href={bookDemoUrl} className="lp-btn lp-btn-primary">
                  Book a Demo
                </CTAButton>
                <a href="#platform" className="lp-btn lp-btn-secondary">
                  Explore Platform
                </a>
              </div>
            </div>

            <div className="lp-hero-panel" aria-label="Learning operations snapshot">
              <div className="lp-insight-card lp-insight-card-main">
                <h3>Program Health</h3>
                <div className="lp-insight-metrics">
                  <div>
                    <span>Completion</span>
                    <strong>91%</strong>
                  </div>
                  <div>
                    <span>At Risk</span>
                    <strong>7%</strong>
                  </div>
                  <div>
                    <span>Overdue</span>
                    <strong>2%</strong>
                  </div>
                </div>
                <p>Track organization-wide readiness in real-time with drill-down by cohort and manager.</p>
              </div>
              <div className="lp-insight-row">
                <div className="lp-insight-card">
                  <h4>Active Portals</h4>
                  <strong>24</strong>
                  <span>Multi-tenant rollout</span>
                </div>
                <div className="lp-insight-card">
                  <h4>Evidence Ready</h4>
                  <strong>100%</strong>
                  <span>Audit export coverage</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="lp-proof-strip" aria-label="Common programs">
          <div className="lp-container lp-proof-items">
            <span>Onboarding Programs</span>
            <span>Compliance Training</span>
            <span>Sales Enablement</span>
            <span>Faculty Development</span>
            <span>SOP Certification</span>
          </div>
        </section>

        <section id="platform" className="lp-section">
          <div className="lp-container">
            <SectionHeader
              kicker="Platform"
              title="Everything needed to design, deliver, and optimize learning operations."
              description="A modular platform for structured learning paths, operational governance, and measurable outcomes."
            />
            <div className="lp-card-grid lp-card-grid-2">
              {platformPillars.map((pillar) => (
                <article key={pillar.title} className="lp-card lp-card-feature">
                  <h3>{pillar.title}</h3>
                  <p>{pillar.description}</p>
                  <ul className="lp-card-bullets">
                    {pillar.bullets.map((bullet) => (
                      <li key={bullet}>{bullet}</li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section id="solutions" className="lp-section lp-section-alt">
          <div className="lp-container">
            <SectionHeader
              kicker="Solutions"
              title="Purpose-built tracks for different learning operating models."
              description="Use the same core platform with playbooks tuned to your delivery model and governance needs."
            />
            <div className="lp-card-grid lp-card-grid-2">
              {solutionTracks.map((track) => (
                <article key={track.title} className="lp-card lp-card-solution">
                  <p className="lp-card-eyebrow">{track.subtitle}</p>
                  <h3>{track.title}</h3>
                  <p>{track.description}</p>
                  <div className="lp-chip-row">
                    {track.outcomes.map((outcome) => (
                      <span key={outcome} className="lp-chip">
                        {outcome}
                      </span>
                    ))}
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section id="industries" className="lp-section">
          <div className="lp-container">
            <SectionHeader
              kicker="Industries"
              title="Learning programs mapped to real-world business and academic workflows."
              description="Start from proven patterns and adapt each program to your teams, timelines, and evidence requirements."
            />
            <div className="lp-card-grid lp-card-grid-3">
              {industryPrograms.map((item) => (
                <article key={item.title} className="lp-card lp-card-industry">
                  <h3>{item.title}</h3>
                  <ul className="lp-card-bullets">
                    {item.programs.map((program) => (
                      <li key={program}>{program}</li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="lp-section lp-section-alt" id="rollout">
          <div className="lp-container">
            <SectionHeader
              kicker="Execution"
              title="A practical rollout model from pilot to scale."
              description="Use this sequence to reduce rollout risk and improve adoption speed across stakeholders."
            />
            <ol className="lp-timeline lp-timeline-4">
              {rolloutSteps.map((step) => (
                <li key={step.step}>
                  <span className="lp-step-num">{step.step}</span>
                  <h3>{step.title}</h3>
                  <p>{step.description}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section id="demo" className="lp-section lp-section-demo">
          <div className="lp-container lp-demo-grid">
            <div>
              <SectionHeader
                kicker="Demo"
                title="See your exact use case mapped in a live walkthrough."
                description="We tailor the session to your program type, operating model, and rollout constraints."
              />
              <ul className="lp-demo-list">
                <li>Role-based walkthrough: super admin, tenant admin, and learner experience.</li>
                <li>Program design review: courses, assessments, reminders, and reporting.</li>
                <li>Implementation blueprint: migration phases, owners, and success KPIs.</li>
                <li>Security and compliance readiness discussion with your IT stakeholders.</li>
              </ul>
            </div>
            <aside className="lp-demo-card" aria-label="Book demo panel">
              <h3>Book your LearnPuddle demo</h3>
              <p>Pick a time and we will run a focused session for your team.</p>
              <CTAButton href={bookDemoUrl} className="lp-btn lp-btn-primary lp-btn-block">
                Schedule Demo
              </CTAButton>
              <a href="mailto:hello@learnpuddle.com" className="lp-btn lp-btn-secondary lp-btn-block">
                Contact Sales Team
              </a>
            </aside>
          </div>
        </section>

        <section id="security" className="lp-section lp-section-alt">
          <div className="lp-container">
            <SectionHeader
              kicker="Trust Center"
              title="Security controls now, compliance validations on a defined path."
              description="Build buyer confidence with transparent control posture and a clear certification roadmap."
            />
            <div className="lp-trust-grid">
              <article className="lp-card lp-trust-card">
                <h3>Security Foundations</h3>
                <ul className="lp-card-bullets">
                  {trustControls.map((control) => (
                    <li key={control}>{control}</li>
                  ))}
                </ul>
              </article>
              <article className="lp-card lp-trust-card">
                <h3>Validation Roadmap</h3>
                <div className="lp-roadmap-list">
                  {complianceRoadmap.map((item) => (
                    <div key={item.standard} className="lp-roadmap-item">
                      <div className="lp-roadmap-title-row">
                        <h4>{item.standard}</h4>
                        <span className="lp-status-chip">{item.status}</span>
                      </div>
                      <p>{item.detail}</p>
                    </div>
                  ))}
                </div>
              </article>
            </div>
          </div>
        </section>

        <section id="faq" className="lp-section">
          <div className="lp-container">
            <SectionHeader kicker="FAQ" title="Questions teams ask before rollout." />
            <div className="lp-faq-list">
              {faqs.map((faq) => (
                <details key={faq.question} className="lp-faq-item">
                  <summary>{faq.question}</summary>
                  <p>{faq.answer}</p>
                </details>
              ))}
            </div>
          </div>
        </section>
      </main>

      <footer className="lp-footer">
        <div className="lp-container lp-footer-inner">
          <a href="/" className="lp-footer-logo" aria-label="LearnPuddle Home">
            LearnPuddle
          </a>
          <nav className="lp-footer-nav" aria-label="Footer">
            <a href="#platform">Platform</a>
            <a href="#solutions">Solutions</a>
            <a href="#industries">Industries</a>
            <a href="#security">Trust Center</a>
            <a href="#demo">Demo</a>
          </nav>
          <div className="lp-footer-actions">
            <CTAButton href={bookDemoUrl} className="lp-footer-link">
              Book Demo
            </CTAButton>
          </div>
        </div>
        <div className="lp-container lp-footer-bottom">
          <span>© {new Date().getFullYear()} LearnPuddle. All rights reserved.</span>
        </div>
      </footer>
    </div>
  );
};
