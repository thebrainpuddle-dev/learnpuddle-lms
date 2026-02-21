import React from 'react';
import { getBookDemoUrl, isExternalHttpUrl } from '../../config/platform';
import './ProductLandingPage.css';

const industries = [
  {
    title: 'Schools and Colleges',
    description: 'Launch branded academies for institutions with admin controls, cohorts, and reporting.',
  },
  {
    title: 'K12 Programs',
    description: 'Deliver grade-wise pathways, assignments, and progress tracking for K12 learners.',
  },
  {
    title: 'Hotel Management',
    description: 'Train frontline teams with SOP modules, practical assessments, and compliance checklists.',
  },
  {
    title: 'Corporate Training',
    description: 'Enable role-based onboarding, certification tracks, and department analytics at scale.',
  },
  {
    title: 'Independent Academies',
    description: 'Run your own academy with custom branding, content workflows, and learner insights.',
  },
];

const highlights = [
  {
    title: 'Custom LMS per Brand',
    description: 'We tailor UX, roles, workflows, and branding for each training business model.',
  },
  {
    title: 'Automation Workflows',
    description: 'Reduce manual operations using reminders, enrollments, and reporting automations.',
  },
  {
    title: 'AI Assignment Builder',
    description: 'Generate assignments quickly from lessons with configurable difficulty and outcomes.',
  },
  {
    title: 'Multi-Tenant Ready',
    description: 'Run platform-level control with tenant-specific domains and isolated data access.',
  },
];

const faqs = [
  {
    question: 'Can LearnPuddle work for different industries?',
    answer:
      'Yes. We design LMS experiences for schools, corporates, hospitality, and independent training businesses with domain-specific workflows.',
  },
  {
    question: 'Do you support custom domains and tenant branding?',
    answer:
      'Yes. Each tenant can run under its own domain with dedicated branding while you manage everything from a central command center.',
  },
  {
    question: 'How does AI-generated assignments work?',
    answer:
      'Admins can create assignments from learning content using AI assistance and then review, edit, and publish according to policy.',
  },
  {
    question: 'How quickly can we launch?',
    answer:
      'Most teams can launch in phased milestones, starting with core workflows and expanding into advanced automations and analytics.',
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

      <header className="lp-header">
        <div className="lp-container lp-header-inner">
          <a href="/" className="lp-logo" aria-label="LearnPuddle Home">
            LearnPuddle
          </a>
          <nav className="lp-nav" aria-label="Primary">
            <a href="#industries">Industries</a>
            <a href="#solutions">Solutions</a>
            <a href="#how-it-works">How It Works</a>
            <a href="#faq">FAQ</a>
          </nav>
          <div className="lp-header-actions">
            <a href="/super-admin/login" className="lp-link-muted">
              Super Admin
            </a>
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
              <p className="lp-pill">Custom LMS Solutions</p>
              <h1>Custom LMS for Schools, Hospitality, Corporate, and Independent Academies</h1>
              <p>
                LearnPuddle helps organizations launch modern LMS platforms with automation and AI-generated
                assignments, tailored for real operational workflows.
              </p>
              <div className="lp-cta-row">
                <CTAButton href={bookDemoUrl} className="lp-btn lp-btn-primary">
                  Book Demo
                </CTAButton>
                <a href="/signup" className="lp-btn lp-btn-secondary">
                  Get Started
                </a>
              </div>
              <div className="lp-proof-inline">
                <span>Tenant-specific domains</span>
                <span>Automation-first operations</span>
                <span>AI assignment generation</span>
              </div>
            </div>
            <div className="lp-hero-panel">
              <div className="lp-panel-card">
                <h3>Built for Multi-Domain Learning</h3>
                <ul>
                  <li>Platform command center and tenant-level controls</li>
                  <li>Branded learning portals per organization</li>
                  <li>Role-aware dashboards for admins and teachers</li>
                  <li>Outcome tracking with analytics-ready workflows</li>
                </ul>
              </div>
            </div>
          </div>
        </section>

        <section className="lp-stats">
          <div className="lp-container lp-stats-grid">
            <div>
              <strong>Customizable</strong>
              <span>Workflows per industry</span>
            </div>
            <div>
              <strong>Automation-Ready</strong>
              <span>Ops and reminders built in</span>
            </div>
            <div>
              <strong>AI-Enhanced</strong>
              <span>Assignment generation support</span>
            </div>
            <div>
              <strong>Multi-Tenant</strong>
              <span>Domain and data separation</span>
            </div>
          </div>
        </section>

        <section id="industries" className="lp-section">
          <div className="lp-container">
            <div className="lp-section-head">
              <p className="lp-kicker">Industries</p>
              <h2>One product foundation, tailored for each training domain</h2>
            </div>
            <div className="lp-card-grid">
              {industries.map((item) => (
                <article key={item.title} className="lp-card">
                  <h3>{item.title}</h3>
                  <p>{item.description}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section id="solutions" className="lp-section lp-section-alt">
          <div className="lp-container">
            <div className="lp-section-head">
              <p className="lp-kicker">Why LearnPuddle</p>
              <h2>Deliver a neat, modern LMS experience without generic templates</h2>
            </div>
            <div className="lp-highlight-grid">
              {highlights.map((item) => (
                <article key={item.title} className="lp-highlight">
                  <h3>{item.title}</h3>
                  <p>{item.description}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section id="how-it-works" className="lp-section">
          <div className="lp-container">
            <div className="lp-section-head">
              <p className="lp-kicker">How It Works</p>
              <h2>From discovery to launch in three clean phases</h2>
            </div>
            <ol className="lp-timeline">
              <li>
                <h3>1. Discovery and Design</h3>
                <p>We map your learners, admin roles, compliance needs, and reporting requirements.</p>
              </li>
              <li>
                <h3>2. Configuration and Automation</h3>
                <p>We shape tenant setup, domain routing, assignment workflows, and automation logic.</p>
              </li>
              <li>
                <h3>3. Go-Live and Scale</h3>
                <p>Launch your LMS, onboard teams, and expand with analytics and AI-driven workflows.</p>
              </li>
            </ol>
          </div>
        </section>

        <section className="lp-cta-band">
          <div className="lp-container lp-cta-band-inner">
            <h2>Need an LMS that fits your domain and operations?</h2>
            <CTAButton href={bookDemoUrl} className="lp-btn lp-btn-primary">
              Book Demo
            </CTAButton>
          </div>
        </section>

        <section id="faq" className="lp-section lp-section-alt">
          <div className="lp-container">
            <div className="lp-section-head">
              <p className="lp-kicker">FAQ</p>
              <h2>Common questions from teams adopting LearnPuddle</h2>
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

      <footer className="lp-footer">
        <div className="lp-container lp-footer-inner">
          <p>LearnPuddle</p>
          <div>
            <a href="/signup">Start Setup</a>
            <a href="/super-admin/login">Super Admin</a>
          </div>
        </div>
      </footer>
    </div>
  );
};
