import React from 'react';
import {
  getBookDemoCalLink,
  getBookDemoUrl,
  isExternalHttpUrl,
  useInlineBookDemo,
} from '../../config/platform';
import {
  AcademicCapIcon,
  ChartBarIcon,
  ClipboardDocumentListIcon,
  LockClosedIcon,
  PlayCircleIcon,
  ShieldCheckIcon,
  UserGroupIcon,
  DocumentCheckIcon,
  HeartIcon,
  BuildingOfficeIcon,
  WrenchScrewdriverIcon,
  StarIcon,
  CpuChipIcon,
  MagnifyingGlassCircleIcon,
  Cog6ToothIcon,
  RocketLaunchIcon,
  ArrowTrendingUpIcon,
  MapIcon,
  ServerStackIcon,
  BoltIcon,
  CheckCircleIcon,
  ArrowRightIcon,
} from '@heroicons/react/24/outline';
import './ProductLandingPage.css';

declare global {
  interface CalApi {
    (...args: any[]): any;
    loaded?: boolean;
    ns?: Record<string, (...args: any[]) => any>;
    q?: any[];
  }

  interface Window {
    Cal?: CalApi;
  }
}

const CAL_SCRIPT_SRC = 'https://app.cal.com/embed/embed.js';
const CAL_NAMESPACE = 'learnpuddle30min';
const CAL_CONTAINER_ID = 'lp-cal-inline-30min';

type CalQueueTarget = ((...args: any[]) => any) & { q?: any[] };

const queueCal = (target: CalQueueTarget | CalApi, args: any[]) => {
  target.q = target.q || [];
  target.q.push(args);
};

const ensureCalBootstrap = () => {
  if (window.Cal) return;

  const cal = ((...args: any[]) => {
    const allArgs = [...args];
    if (!cal.loaded) {
      cal.ns = cal.ns || {};
      const script = document.createElement('script');
      script.src = CAL_SCRIPT_SRC;
      script.async = true;
      script.setAttribute('data-cal-embed', 'learnpuddle');
      document.head.appendChild(script);
      cal.loaded = true;
    }

    if (allArgs[0] === 'init') {
      const namespace = allArgs[1];
      if (typeof namespace === 'string') {
        let nsApi = cal.ns?.[namespace] as CalQueueTarget | undefined;
        if (!nsApi) {
          nsApi = ((...nsArgs: any[]) => {
            queueCal(nsApi as CalQueueTarget, [...nsArgs]);
          }) as CalQueueTarget;
          nsApi.q = [];
        }
        cal.ns = cal.ns || {};
        cal.ns[namespace] = nsApi;
        queueCal(nsApi, allArgs);
        queueCal(cal, ['initNamespace', namespace]);
        return;
      }
    }

    queueCal(cal, allArgs);
  }) as CalApi;

  cal.ns = {};
  cal.q = [];
  window.Cal = cal;
};

const ensureCalScriptLoaded = async () => {
  ensureCalBootstrap();
  if (window.Cal?.loaded && document.querySelector('script[data-cal-embed="learnpuddle"][data-loaded="true"]')) {
    return;
  }

  await new Promise<void>((resolve, reject) => {
    let timeoutId: number | undefined;
    const onLoad = (script: HTMLScriptElement) => {
      script.setAttribute('data-loaded', 'true');
      if (timeoutId) window.clearTimeout(timeoutId);
      resolve();
    };
    const onError = () => {
      if (timeoutId) window.clearTimeout(timeoutId);
      reject(new Error('Failed to load Cal embed script'));
    };

    const existing = document.querySelector<HTMLScriptElement>('script[data-cal-embed="learnpuddle"]');
    if (existing) {
      if (existing.getAttribute('data-loaded') === 'true') {
        resolve();
        return;
      }
      existing.addEventListener('load', () => onLoad(existing), { once: true });
      existing.addEventListener('error', onError, { once: true });
      timeoutId = window.setTimeout(() => onError(), 8000);
      return;
    }

    const script = document.createElement('script');
    script.src = CAL_SCRIPT_SRC;
    script.async = true;
    script.setAttribute('data-cal-embed', 'learnpuddle');
    script.onload = () => onLoad(script);
    script.onerror = onError;
    timeoutId = window.setTimeout(() => onError(), 8000);
    document.head.appendChild(script);
  });
};

// ── Data ────────────────────────────────────────────────────────────────────

const heroOutcomes = [
  'Launch branded portals for every team, campus, or client.',
  'Automate compliance tracking, deadlines, and certifications.',
  'See who completed what, when — with audit-ready reports.',
];

const proofItems = [
  { label: 'Onboarding Programs', Icon: UserGroupIcon },
  { label: 'Compliance Training', Icon: ShieldCheckIcon },
  { label: 'Sales Enablement', Icon: ChartBarIcon },
  { label: 'Faculty Development', Icon: AcademicCapIcon },
  { label: 'SOP Certification', Icon: DocumentCheckIcon },
];

const platformCapabilities = [
  {
    Icon: AcademicCapIcon,
    title: 'Course Builder',
    description: 'Create structured programs with video, quizzes, and assignments. Set mandatory milestones, deadlines, and completion logic in minutes.',
    bullets: ['Reusable course templates', 'Deadline + reminder automation', 'Mandatory milestone enforcement'],
  },
  {
    Icon: ServerStackIcon,
    title: 'Multi-Tenant Delivery',
    description: 'Roll out branded portals per school, branch, or client — with fully isolated data, delegated admin, and custom domains.',
    bullets: ['Per-tenant branding controls', 'Bulk enrollment and imports', 'Groups and cohort targeting'],
  },
  {
    Icon: ChartBarIcon,
    title: 'Reporting & Analytics',
    description: 'Completion rates, compliance status, and department-level breakdowns — surfaced in real-time dashboards your executives can act on.',
    bullets: ['Executive dashboards', 'Department and manager views', 'Exportable evidence reports'],
  },
  {
    Icon: LockClosedIcon,
    title: 'Security & Access Control',
    description: 'Role-based permissions, strong authentication controls, and tenant-level data isolation — production-ready for enterprise buyers.',
    bullets: ['SSO and 2FA support', 'Centralized audit log', 'Environment and backup controls'],
  },
  {
    Icon: ClipboardDocumentListIcon,
    title: 'Assessment Engine',
    description: 'Generate quizzes from video transcripts automatically. Multiple-choice and short-answer. Auto-graded where applicable.',
    bullets: ['AI-generated from transcripts', 'Auto-graded submissions', 'Configurable pass thresholds'],
  },
  {
    Icon: PlayCircleIcon,
    title: 'Video Infrastructure',
    description: 'Upload any format. Automatic transcoding, thumbnail generation, captions, and adaptive streaming — all handled for you.',
    bullets: ['Any upload format', 'Auto captions and thumbnails', 'Adaptive streaming delivery'],
  },
];

type SolutionKey = 'schools' | 'corporate' | 'franchise' | 'academies';

const solutionTabs: { key: SolutionKey; label: string }[] = [
  { key: 'schools', label: 'Schools & Universities' },
  { key: 'corporate', label: 'Corporate L&D' },
  { key: 'franchise', label: 'Franchise Operations' },
  { key: 'academies', label: 'Academies & Coaching' },
];

const solutionContent: Record<SolutionKey, {
  subtitle: string;
  description: string;
  outcomes: string[];
  programs: string[];
}> = {
  schools: {
    subtitle: 'K-12, university, and academic groups',
    description: 'Give principals and HODs real-time visibility into teacher CPD hours, IB certifications, and CBSE compliance — without spreadsheets or manual follow-ups.',
    outcomes: ['CPD and policy completion tracking', 'Principal and HOD visibility', 'Multi-school governance'],
    programs: ['CBSE 50-hour CPD mandates', 'IB educator certification logs', 'Department-wise progress reports', 'Curriculum content rollout', 'Policy and induction programs'],
  },
  corporate: {
    subtitle: 'People, operations, and compliance teams',
    description: 'Standardize onboarding, SOP enablement, and recurring certifications with clear ownership, automated reminders, and completion evidence your auditors trust.',
    outcomes: ['Faster onboarding ramp', 'Reduced compliance drift', 'Manager-level completion control'],
    programs: ['Employee onboarding workflows', 'SOP and safety certifications', 'Role-based course assignments', 'Annual compliance renewals', 'Sales and product enablement'],
  },
  franchise: {
    subtitle: 'Retail, hospitality, and distributed teams',
    description: 'Ship the same operational playbooks to every location while preserving local manager accountability and branch-level reporting.',
    outcomes: ['Consistent SOP adoption', 'Location comparison analytics', 'Branch-level training health'],
    programs: ['Guest experience standards', 'Outlet launch onboarding', 'Frontline service drills', 'New hire induction packs', 'Brand standards training'],
  },
  academies: {
    subtitle: 'Program-led learning businesses',
    description: 'Monetize and operationalize blended learning with branded portals, structured milestones, and clear learner progression your instructors can track.',
    outcomes: ['Branded learner journey', 'Instructor workload reduction', 'Clear completion evidence'],
    programs: ['Structured learning paths', 'Cohort-based programs', 'Certification tracks', 'Instructor-led scheduling', 'Learner progress reporting'],
  },
};

const industryPrograms = [
  {
    Icon: AcademicCapIcon,
    title: 'Education',
    description: 'Track CPD mandates, IB certifications, and curriculum rollouts across departments and campuses.',
    programs: ['Faculty development', 'Classroom technology enablement', 'Assessment moderation workflows'],
  },
  {
    Icon: HeartIcon,
    title: 'Healthcare',
    description: 'Keep clinical staff current on protocol updates and mandatory recertifications with automated reminders.',
    programs: ['Clinical protocol updates', 'Mandatory recertification cycles', 'Multi-role competency checks'],
  },
  {
    Icon: BuildingOfficeIcon,
    title: 'BFSI',
    description: 'Roll out regulatory policies and compliance attestations to branches with full audit trail.',
    programs: ['Regulatory policy rollout', 'Branch onboarding', 'Periodic compliance attestations'],
  },
  {
    Icon: WrenchScrewdriverIcon,
    title: 'Manufacturing',
    description: 'Certify plant workers on safety procedures and machine SOPs with supervisor-level oversight.',
    programs: ['Plant safety training', 'Machine SOP rollout', 'Supervisor readiness pathways'],
  },
  {
    Icon: StarIcon,
    title: 'Hospitality',
    description: 'Train frontline teams on guest experience standards consistently across every outlet.',
    programs: ['Guest experience standards', 'Frontline service drills', 'New outlet launch onboarding'],
  },
  {
    Icon: CpuChipIcon,
    title: 'Technology',
    description: 'Enable sales teams, certify partners, and run release training programs at scale.',
    programs: ['Sales enablement', 'Partner training', 'Release certification tracks'],
  },
];

const rolloutSteps = [
  {
    step: '01',
    Icon: MagnifyingGlassCircleIcon,
    title: 'Discover',
    description: 'Map learner personas, compliance obligations, and success metrics. Align program owners and rollout phases.',
  },
  {
    step: '02',
    Icon: Cog6ToothIcon,
    title: 'Configure',
    description: 'Set up domains, branding, permissions, cohorts, and baseline course architecture for each audience.',
  },
  {
    step: '03',
    Icon: RocketLaunchIcon,
    title: 'Launch',
    description: 'Run pilot cohorts, tune reminder cadence, and finalize production workflows before broader rollout.',
  },
  {
    step: '04',
    Icon: ArrowTrendingUpIcon,
    title: 'Optimize',
    description: 'Use dashboards and completion evidence to continuously improve pathways and tighten outcomes.',
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
    question: 'Does it support CBSE CPD and IB certification tracking?',
    answer:
      'Yes. Configure mandatory training hours and generate compliance reports per teacher, department, or organization.',
  },
  {
    question: 'What does the demo include?',
    answer:
      'A role-specific walkthrough of admin workflows, learner experience, analytics, and rollout plan recommendations for your use case.',
  },
  {
    question: 'Can we use this on mobile devices?',
    answer:
      'Yes. The platform is fully responsive across modern desktop and mobile browsers.',
  },
];

// ── Components ───────────────────────────────────────────────────────────────

function CTAButton({
  href,
  onClick,
  children,
  className,
}: {
  href?: string;
  onClick?: () => void;
  children: React.ReactNode;
  className?: string;
}) {
  if (onClick) {
    return (
      <button type="button" className={className} onClick={onClick}>
        {children}
      </button>
    );
  }
  const safeHref = href || '#';
  const isExternal = isExternalHttpUrl(safeHref);
  return (
    <a
      href={safeHref}
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

// ── Page ─────────────────────────────────────────────────────────────────────

export const ProductLandingPage: React.FC = () => {
  const bookDemoUrl = getBookDemoUrl();
  const bookDemoCalLink = getBookDemoCalLink();
  const inlineDemoEnabled = useInlineBookDemo();
  const [showCalModal, setShowCalModal] = React.useState(false);
  const [calLoadError, setCalLoadError] = React.useState('');
  const [activeTab, setActiveTab] = React.useState<SolutionKey>('schools');

  React.useEffect(() => {
    if (!showCalModal) return;
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = originalOverflow;
    };
  }, [showCalModal]);

  React.useEffect(() => {
    if (!showCalModal || !inlineDemoEnabled) return;

    let cancelled = false;
    let modalCheckTimeout: number | undefined;

    const initCal = async () => {
      try {
        await ensureCalScriptLoaded();
        if (cancelled || !window.Cal) return;

        window.Cal('init', CAL_NAMESPACE, { origin: 'https://app.cal.com' });
        window.Cal.ns?.[CAL_NAMESPACE]?.('inline', {
          elementOrSelector: `#${CAL_CONTAINER_ID}`,
          config: { layout: 'month_view', useSlotsViewOnSmallScreen: true },
          calLink: bookDemoCalLink,
        });
        window.Cal.ns?.[CAL_NAMESPACE]?.('ui', {
          hideEventTypeDetails: false,
          layout: 'month_view',
        });
        setCalLoadError('');
        modalCheckTimeout = window.setTimeout(() => {
          if (cancelled) return;
          const hasInlineFrame = !!document
            .getElementById(CAL_CONTAINER_ID)
            ?.querySelector('iframe');
          if (!hasInlineFrame) {
            setCalLoadError(
              'Inline scheduler was blocked by your browser or extension. Open the booking page instead.',
            );
          }
        }, 2200);
      } catch {
        if (!cancelled) {
          setCalLoadError(
            'Unable to load the inline scheduler right now. Open the booking page instead.',
          );
        }
      }
    };

    void initCal();
    return () => {
      cancelled = true;
      if (modalCheckTimeout) {
        window.clearTimeout(modalCheckTimeout);
      }
    };
  }, [bookDemoCalLink, inlineDemoEnabled, showCalModal]);

  const openBookDemo = React.useCallback(() => {
    if (!inlineDemoEnabled) {
      window.open(bookDemoUrl, '_blank', 'noopener,noreferrer');
      return;
    }
    setCalLoadError('');
    setShowCalModal(true);
  }, [bookDemoUrl, inlineDemoEnabled]);

  const activeSolution = solutionContent[activeTab];

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
            <a href="#solutions">Solutions</a>
            <a href="#industries">Industries</a>
            <a href="#security">Security</a>
            <a href="#demo">Demo</a>
            <a href="#faq">FAQ</a>
          </nav>
          <div className="lp-header-actions">
            <CTAButton onClick={openBookDemo} className="lp-btn lp-btn-primary">
              Book Demo
            </CTAButton>
          </div>
        </div>
      </header>

      <main>
        {/* ── Hero ── */}
        <section className="lp-hero">
          <div className="lp-container lp-hero-grid">
            <div className="lp-hero-copy">
              <p className="lp-pill">
                <BoltIcon className="lp-pill-icon" aria-hidden="true" />
                Learning Management Platform
              </p>
              <h1>The LMS that runs your entire training operation.</h1>
              <p>
                From onboarding to compliance, LearnPuddle gives schools, enterprises, and academies
                one platform to build courses, track progress, and prove outcomes.
              </p>
              <ul className="lp-hero-outcomes">
                {heroOutcomes.map((item) => (
                  <li key={item}>
                    <CheckCircleIcon className="lp-outcome-icon" aria-hidden="true" />
                    {item}
                  </li>
                ))}
              </ul>
              <div className="lp-cta-row">
                <CTAButton onClick={openBookDemo} className="lp-btn lp-btn-primary">
                  Book a Demo
                  <ArrowRightIcon className="lp-btn-icon" aria-hidden="true" />
                </CTAButton>
                <a href="#platform" className="lp-btn lp-btn-secondary">
                  Explore Platform
                </a>
              </div>
            </div>

            <div className="lp-hero-panel" aria-label="Learning operations snapshot">
              <div className="lp-insight-card lp-insight-card-main">
                <div className="lp-insight-card-header">
                  <ChartBarIcon className="lp-insight-header-icon" aria-hidden="true" />
                  <h3>Program Health</h3>
                </div>
                <div className="lp-insight-metrics">
                  <div className="lp-metric lp-metric-green">
                    <span>Completion</span>
                    <strong>91%</strong>
                  </div>
                  <div className="lp-metric lp-metric-amber">
                    <span>At Risk</span>
                    <strong>7%</strong>
                  </div>
                  <div className="lp-metric lp-metric-red">
                    <span>Overdue</span>
                    <strong>2%</strong>
                  </div>
                </div>
                <p>Track organization-wide readiness in real-time with drill-down by cohort and manager.</p>
              </div>
              <div className="lp-insight-row">
                <div className="lp-insight-card lp-insight-card-mini">
                  <ServerStackIcon className="lp-insight-mini-icon" aria-hidden="true" />
                  <h4>Active Portals</h4>
                  <strong>24</strong>
                  <span>Multi-tenant rollout</span>
                </div>
                <div className="lp-insight-card lp-insight-card-mini">
                  <ShieldCheckIcon className="lp-insight-mini-icon" aria-hidden="true" />
                  <h4>Evidence Ready</h4>
                  <strong>100%</strong>
                  <span>Audit export coverage</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── Proof Strip ── */}
        <section className="lp-proof-strip" aria-label="Common programs">
          <div className="lp-container lp-proof-items">
            {proofItems.map(({ label, Icon }) => (
              <span key={label} className="lp-proof-chip">
                <Icon className="lp-proof-chip-icon" aria-hidden="true" />
                {label}
              </span>
            ))}
          </div>
        </section>

        {/* ── Platform ── */}
        <section id="platform" className="lp-section">
          <div className="lp-container">
            <SectionHeader
              kicker="Platform"
              title="Everything you need to design, deliver, and optimize learning."
              description="A complete platform covering course creation, video delivery, compliance tracking, analytics, and multi-tenant governance."
            />
            <div className="lp-card-grid lp-card-grid-3">
              {platformCapabilities.map((cap) => (
                <article key={cap.title} className="lp-card lp-card-feature">
                  <div className="lp-icon-badge">
                    <cap.Icon className="lp-icon-badge-svg" aria-hidden="true" />
                  </div>
                  <h3>{cap.title}</h3>
                  <p>{cap.description}</p>
                  <ul className="lp-card-bullets">
                    {cap.bullets.map((bullet) => (
                      <li key={bullet}>{bullet}</li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* ── Solutions Tabs ── */}
        <section id="solutions" className="lp-section lp-section-alt">
          <div className="lp-container">
            <SectionHeader
              kicker="Solutions"
              title="Built for every learning operating model."
              description="Pick your use case and see exactly how LearnPuddle maps to your program design, governance needs, and compliance requirements."
            />

            {/* Tab Bar */}
            <div className="lp-tab-bar" role="tablist" aria-label="Solution tracks">
              {solutionTabs.map(({ key, label }) => (
                <button
                  key={key}
                  type="button"
                  role="tab"
                  aria-selected={activeTab === key}
                  className={`lp-tab ${activeTab === key ? 'lp-tab-active' : ''}`}
                  onClick={() => setActiveTab(key)}
                >
                  {label}
                </button>
              ))}
            </div>

            {/* Tab Content */}
            <div className="lp-tab-panel" role="tabpanel">
              <div className="lp-tab-content-grid">
                <div className="lp-tab-content-left">
                  <p className="lp-card-eyebrow">{activeSolution.subtitle}</p>
                  <h3 className="lp-tab-content-title">{solutionTabs.find(t => t.key === activeTab)?.label}</h3>
                  <p className="lp-tab-content-description">{activeSolution.description}</p>
                  <div className="lp-chip-row">
                    {activeSolution.outcomes.map((outcome) => (
                      <span key={outcome} className="lp-chip">
                        <CheckCircleIcon className="lp-chip-icon" aria-hidden="true" />
                        {outcome}
                      </span>
                    ))}
                  </div>
                  <CTAButton onClick={openBookDemo} className="lp-btn lp-btn-primary lp-tab-cta">
                    See this in a demo
                    <ArrowRightIcon className="lp-btn-icon" aria-hidden="true" />
                  </CTAButton>
                </div>
                <div className="lp-tab-content-right">
                  <div className="lp-program-card">
                    <p className="lp-program-card-label">Programs in this track</p>
                    <ul className="lp-program-list">
                      {activeSolution.programs.map((program) => (
                        <li key={program}>
                          <CheckCircleIcon className="lp-program-check" aria-hidden="true" />
                          {program}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── Mid-page CTA Band ── */}
        <section className="lp-mid-cta" aria-label="Mid-page call to action">
          <div className="lp-container lp-mid-cta-inner">
            <div>
              <h2>Ready to centralize your training operations?</h2>
              <p>Join organizations running structured learning programs on LearnPuddle.</p>
            </div>
            <CTAButton onClick={openBookDemo} className="lp-btn lp-btn-light">
              Book a Demo
              <ArrowRightIcon className="lp-btn-icon" aria-hidden="true" />
            </CTAButton>
          </div>
        </section>

        {/* ── Industries ── */}
        <section id="industries" className="lp-section">
          <div className="lp-container">
            <SectionHeader
              kicker="Industries"
              title="Learning programs mapped to real-world workflows."
              description="Start from proven patterns and adapt each program to your teams, timelines, and evidence requirements."
            />
            <div className="lp-card-grid lp-card-grid-3">
              {industryPrograms.map((item) => (
                <article key={item.title} className="lp-card lp-card-industry">
                  <div className="lp-icon-badge lp-icon-badge-sm">
                    <item.Icon className="lp-icon-badge-svg" aria-hidden="true" />
                  </div>
                  <h3>{item.title}</h3>
                  <p className="lp-industry-desc">{item.description}</p>
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

        {/* ── How It Works ── */}
        <section className="lp-section lp-section-alt" id="rollout">
          <div className="lp-container">
            <SectionHeader
              kicker="How It Works"
              title="From discovery to scale in four steps."
              description="A practical rollout model designed to reduce deployment risk and improve adoption speed."
            />
            <ol className="lp-timeline lp-timeline-4">
              {rolloutSteps.map((step, idx) => (
                <li key={step.step} className={idx < rolloutSteps.length - 1 ? 'lp-step-has-connector' : ''}>
                  <div className="lp-step-icon-wrap">
                    <div className="lp-step-icon-badge">
                      <step.Icon className="lp-step-icon-svg" aria-hidden="true" />
                    </div>
                  </div>
                  <span className="lp-step-num">{step.step}</span>
                  <h3>{step.title}</h3>
                  <p>{step.description}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* ── Demo ── */}
        <section id="demo" className="lp-section lp-section-demo">
          <div className="lp-container lp-demo-grid">
            <div>
              <SectionHeader
                kicker="Demo"
                title="See LearnPuddle in action."
                description="We run a focused session tailored to your program type, operating model, and rollout timeline."
              />
              <ul className="lp-demo-list">
                <li>Watch courses, assessments, and compliance tracking work end-to-end.</li>
                <li>See admin, teacher, and learner dashboards tailored to your industry.</li>
                <li>Get a rollout plan with timeline, owners, and success metrics.</li>
                <li>Security and compliance readiness discussion with your IT stakeholders.</li>
              </ul>
            </div>
            <aside className="lp-demo-card" aria-label="Book demo panel">
              <div className="lp-demo-card-icon-wrap">
                <RocketLaunchIcon className="lp-demo-card-icon" aria-hidden="true" />
              </div>
              <h3>Book your LearnPuddle demo</h3>
              <p>Pick a time and we will run a focused session for your team.</p>
              <CTAButton onClick={openBookDemo} className="lp-btn lp-btn-primary lp-btn-block">
                Schedule Demo
              </CTAButton>
              <a href="mailto:hello@learnpuddle.com" className="lp-btn lp-btn-secondary lp-btn-block">
                Contact Sales Team
              </a>
            </aside>
          </div>
        </section>

        {/* ── Security ── */}
        <section id="security" className="lp-section lp-section-alt">
          <div className="lp-container">
            <SectionHeader
              kicker="Trust Center"
              title="Security controls now, compliance validations on a defined path."
              description="Build buyer confidence with transparent control posture and a clear certification roadmap."
            />
            <div className="lp-trust-grid">
              <article className="lp-card lp-trust-card">
                <div className="lp-trust-card-header">
                  <div className="lp-icon-badge lp-icon-badge-sm">
                    <ShieldCheckIcon className="lp-icon-badge-svg" aria-hidden="true" />
                  </div>
                  <h3>Security Foundations</h3>
                </div>
                <ul className="lp-card-bullets">
                  {trustControls.map((control) => (
                    <li key={control}>{control}</li>
                  ))}
                </ul>
              </article>
              <article className="lp-card lp-trust-card">
                <div className="lp-trust-card-header">
                  <div className="lp-icon-badge lp-icon-badge-sm">
                    <MapIcon className="lp-icon-badge-svg" aria-hidden="true" />
                  </div>
                  <h3>Validation Roadmap</h3>
                </div>
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

        {/* ── FAQ ── */}
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

      {/* ── Cal Modal ── */}
      {showCalModal && (
        <div
          className="lp-cal-modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-label="Book a demo"
          onClick={() => setShowCalModal(false)}
        >
          <div className="lp-cal-modal" onClick={(event) => event.stopPropagation()}>
            <div className="lp-cal-modal-head">
              <div>
                <p className="lp-kicker">Book Demo</p>
                <h3>Pick a time for your LearnPuddle walkthrough</h3>
              </div>
              <button
                type="button"
                className="lp-cal-close"
                onClick={() => setShowCalModal(false)}
                aria-label="Close demo scheduler"
              >
                ×
              </button>
            </div>
            {calLoadError ? (
              <div className="lp-cal-fallback">
                <p>{calLoadError}</p>
                <a href={bookDemoUrl} target="_blank" rel="noreferrer" className="lp-btn lp-btn-primary">
                  Open booking page
                </a>
              </div>
            ) : (
              <div id={CAL_CONTAINER_ID} className="lp-cal-embed" />
            )}
          </div>
        </div>
      )}

      {/* ── Footer ── */}
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
            <CTAButton onClick={openBookDemo} className="lp-footer-link">
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
