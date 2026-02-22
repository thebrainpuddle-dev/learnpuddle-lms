import React from 'react';
import { getBookDemoUrl, isExternalHttpUrl } from '../../config/platform';
import './ProductLandingPage.css';

const capabilities = [
  {
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <rect x="3" y="3" width="7" height="7" rx="1.5" fill="currentColor" opacity="0.9" />
        <rect x="14" y="3" width="7" height="7" rx="1.5" fill="currentColor" opacity="0.55" />
        <rect x="3" y="14" width="7" height="7" rx="1.5" fill="currentColor" opacity="0.55" />
        <rect x="14" y="14" width="7" height="7" rx="1.5" fill="currentColor" opacity="0.25" />
      </svg>
    ),
    title: 'Course Builder',
    description:
      'Structured courses with modules, videos, documents, and assessments. Mandatory content flags. Deadline enforcement.',
  },
  {
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M9 11l3 3L22 4"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    ),
    title: 'Compliance Tracking',
    description:
      'CBSE 50-hour CPD requirements. IB educator certifications. Custom training mandates. Exportable compliance reports.',
  },
  {
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" />
        <path d="M12 7v5l3 3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    ),
    title: 'Assessment Engine',
    description:
      'Quiz generation from video transcripts. Multiple choice and short answer formats. Auto-grading for objective questions.',
  },
  {
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M18 20V10M12 20V4M6 20v-6"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    ),
    title: 'Progress Dashboards',
    description:
      'Completion rates by course, group, or learner. Video watch time. Assignment scores. Department-wise breakdowns.',
  },
  {
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <rect x="2" y="3" width="20" height="14" rx="2" stroke="currentColor" strokeWidth="2" />
        <path d="M8 21h8M12 17v4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    ),
    title: 'White-Label Tenants',
    description:
      'Subdomain per organization. Custom logo and colors. Isolated data. Central command center for platform admins.',
  },
  {
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <polygon
          points="23 7 16 12 23 17 23 7"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <rect x="1" y="5" width="15" height="14" rx="2" stroke="currentColor" strokeWidth="2" />
      </svg>
    ),
    title: 'Video Infrastructure',
    description:
      'Any upload format. Automatic transcoding. Thumbnail generation. Captions. Adaptive streaming.',
  },
];

const industries = [
  {
    title: 'Schools & Universities',
    bullets: [
      'CBSE/ICSE/IB compliance tracking',
      '50-hour CPD mandate monitoring',
      'Department-wise progress reports',
      'HOD and principal dashboards',
    ],
  },
  {
    title: 'Corporate Training',
    bullets: [
      'Employee onboarding workflows',
      'SOP certifications',
      'Role-based course assignments',
      'Completion audit trails',
    ],
  },
  {
    title: 'Fitness & Wellness',
    bullets: [
      'Trainer certification modules',
      'Video-based skill assessments',
      'Progress verification for accreditation',
    ],
  },
  {
    title: 'Hospitality & F&B',
    bullets: [
      'Frontline staff training',
      'Compliance checklists',
      'Multi-location deployment',
      'Standardized SOP delivery',
    ],
  },
  {
    title: 'Independent Academies',
    bullets: ['Branded learner portals', 'Course catalog management', 'Learner progress analytics'],
  },
];

const faqs = [
  {
    question: 'What is LearnPuddle?',
    answer:
      'A learning management platform for organizations that need course delivery, progress tracking, and compliance reporting.',
  },
  {
    question: 'Does it support CBSE and IB compliance tracking?',
    answer:
      'Yes. Configure mandatory training hours and generate compliance reports per teacher, department, or organization.',
  },
  {
    question: 'Can each organization have its own branding?',
    answer:
      'Yes. Every tenant gets a custom subdomain, logo, and color scheme. Data is fully isolated.',
  },
  {
    question: 'How does assessment generation work?',
    answer:
      'Upload a video. The system transcribes it and generates quiz questions. You review and publish.',
  },
  {
    question: 'Is the platform secure?',
    answer: 'Role-based access. Audit logs. SSO support. Two-factor authentication. Tenant-isolated data.',
  },
  {
    question: 'How long does setup take?',
    answer:
      'Most organizations go live within a day. Course creation and learner onboarding can start immediately.',
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

export const ProductLandingPage: React.FC = () => {
  const bookDemoUrl = getBookDemoUrl();

  return (
    <div className="lp-page">
      <div className="lp-bg-shape lp-bg-shape-a" />
      <div className="lp-bg-shape lp-bg-shape-b" />

      {/* ── Header ── */}
      <header className="lp-header">
        <div className="lp-container lp-header-inner">
          <a href="/" className="lp-logo" aria-label="LearnPuddle Home">
            LearnPuddle
          </a>
          <nav className="lp-nav" aria-label="Primary">
            <a href="#platform">Platform</a>
            <a href="#industries">Industries</a>
            <a href="#how-it-works">How It Works</a>
            <a href="#faq">FAQ</a>
          </nav>
          <div className="lp-header-actions">
            <CTAButton href={bookDemoUrl} className="lp-btn lp-btn-primary">
              Book a Demo
            </CTAButton>
          </div>
        </div>
      </header>

      <main>
        {/* ── Hero ── */}
        <section className="lp-hero">
          <div className="lp-container lp-hero-grid">
            <div className="lp-hero-copy">
              <p className="lp-pill">Learning Management Platform</p>
              <h1>Learning management infrastructure for schools and enterprises.</h1>
              <p>
                Course building. Progress tracking. Compliance reporting. White-label portals for
                every organization you manage.
              </p>
              <div className="lp-cta-row">
                <CTAButton href={bookDemoUrl} className="lp-btn lp-btn-primary">
                  Book a Demo
                </CTAButton>
                <a href="/signup" className="lp-btn lp-btn-secondary">
                  Get Started
                </a>
              </div>
            </div>
            <div className="lp-hero-panel">
              <div className="lp-dashboard-placeholder" aria-label="Platform dashboard preview">
                <div className="lp-dashboard-placeholder-inner">
                  <div className="lp-dp-topbar">
                    <span className="lp-dp-dot" />
                    <span className="lp-dp-dot" />
                    <span className="lp-dp-dot" />
                  </div>
                  <div className="lp-dp-body">
                    <div className="lp-dp-sidebar">
                      <div className="lp-dp-sidebar-item lp-dp-active" />
                      <div className="lp-dp-sidebar-item" />
                      <div className="lp-dp-sidebar-item" />
                      <div className="lp-dp-sidebar-item" />
                    </div>
                    <div className="lp-dp-content">
                      <div className="lp-dp-stat-row">
                        <div className="lp-dp-stat" />
                        <div className="lp-dp-stat" />
                        <div className="lp-dp-stat" />
                      </div>
                      <div className="lp-dp-row lp-dp-row-wide" />
                      <div className="lp-dp-row" />
                      <div className="lp-dp-row lp-dp-row-narrow" />
                      <div className="lp-dp-row" />
                    </div>
                  </div>
                </div>
                <p className="lp-dp-label">Platform Preview</p>
              </div>
            </div>
          </div>
        </section>

        {/* ── Capabilities Bar ── */}
        <section className="lp-capabilities-bar">
          <div className="lp-container lp-capabilities-bar-inner">
            <span>Course Management</span>
            <span className="lp-cap-sep" aria-hidden="true" />
            <span>Progress Tracking</span>
            <span className="lp-cap-sep" aria-hidden="true" />
            <span>Compliance Reports</span>
            <span className="lp-cap-sep" aria-hidden="true" />
            <span>White-Label Portals</span>
          </div>
        </section>

        {/* ── Platform ── */}
        <section id="platform" className="lp-section">
          <div className="lp-container">
            <div className="lp-section-head">
              <p className="lp-kicker">Platform</p>
              <h2>Everything needed to run training operations at scale.</h2>
            </div>
            <div className="lp-card-grid lp-card-grid-6">
              {capabilities.map((cap) => (
                <article key={cap.title} className="lp-card lp-card-cap">
                  <div className="lp-cap-icon">{cap.icon}</div>
                  <h3>{cap.title}</h3>
                  <p>{cap.description}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* ── Industries ── */}
        <section id="industries" className="lp-section lp-section-alt">
          <div className="lp-container">
            <div className="lp-section-head">
              <p className="lp-kicker">Industries</p>
              <h2>Built for the organizations that run structured training programs.</h2>
            </div>
            <div className="lp-card-grid">
              {industries.map((item) => (
                <article key={item.title} className="lp-card lp-card-industry">
                  <h3>{item.title}</h3>
                  <ul className="lp-card-bullets">
                    {item.bullets.map((b) => (
                      <li key={b}>{b}</li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* ── How It Works ── */}
        <section id="how-it-works" className="lp-section">
          <div className="lp-container">
            <div className="lp-section-head">
              <p className="lp-kicker">How It Works</p>
              <h2>Three steps to a fully operational LMS.</h2>
            </div>
            <ol className="lp-timeline">
              <li>
                <span className="lp-step-num">01</span>
                <h3>Configure</h3>
                <p>Set up your subdomain. Upload your logo. Define admin roles and permissions.</p>
              </li>
              <li>
                <span className="lp-step-num">02</span>
                <h3>Build</h3>
                <p>Add courses with videos, documents, and assessments. Set deadlines and mandatory flags.</p>
              </li>
              <li>
                <span className="lp-step-num">03</span>
                <h3>Track</h3>
                <p>Monitor completion across all learners. Export compliance reports. Meet regulatory requirements.</p>
              </li>
            </ol>
          </div>
        </section>

        {/* ── Trust Statement ── */}
        <section className="lp-trust-band">
          <div className="lp-container">
            <p className="lp-trust-text">
              LearnPuddle handles the infrastructure.
              <br />
              You handle the training.
            </p>
          </div>
        </section>

        {/* ── CTA Band ── */}
        <section className="lp-cta-band">
          <div className="lp-container lp-cta-band-inner">
            <h2>Centralize your training operations.</h2>
            <CTAButton href={bookDemoUrl} className="lp-btn lp-btn-primary">
              Book a Demo
            </CTAButton>
          </div>
        </section>

        {/* ── FAQ ── */}
        <section id="faq" className="lp-section lp-section-alt">
          <div className="lp-container">
            <div className="lp-section-head">
              <p className="lp-kicker">FAQ</p>
              <h2>Frequently asked questions.</h2>
            </div>
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

      {/* ── Footer ── */}
      <footer className="lp-footer">
        <div className="lp-container lp-footer-inner">
          <a href="/" className="lp-footer-logo" aria-label="LearnPuddle Home">
            LearnPuddle
          </a>
          <nav className="lp-footer-nav" aria-label="Footer">
            <a href="#platform">Platform</a>
            <a href="#industries">Industries</a>
            <a href="#faq">FAQ</a>
          </nav>
          <div className="lp-footer-actions">
            <CTAButton href={bookDemoUrl} className="lp-footer-link">
              Book a Demo
            </CTAButton>
            <a href="/signup" className="lp-footer-link">
              Get Started
            </a>
          </div>
        </div>
        <div className="lp-container lp-footer-bottom">
          <span>© {new Date().getFullYear()} LearnPuddle. All rights reserved.</span>
        </div>
      </footer>
    </div>
  );
};
