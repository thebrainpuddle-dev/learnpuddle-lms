import React from 'react';
import {
  getBookDemoCalLink,
  getBookDemoUrl,
  isExternalHttpUrl,
  useInlineBookDemo,
} from '../../../config/platform';
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
  Bars3Icon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import './ProductLandingPage.css';

// ── Inline SVG Components ────────────────────────────────────────────────────

function LogoMark({ className }: { className?: string }) {
  return (
    <img
      src="/logo-lp.png"
      alt=""
      className={`${className || ''} lp-logo-circle`}
      aria-hidden="true"
    />
  );
}

function DashboardMockupSVG() {
  return (
    <svg className="lp-dashboard-svg" viewBox="0 0 560 380" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <defs>
        <linearGradient id="dm-bar1" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#1850b8"/><stop offset="1" stopColor="#2c7be5"/></linearGradient>
        <linearGradient id="dm-bar2" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#00a6a6"/><stop offset="1" stopColor="#16a34a"/></linearGradient>
        <linearGradient id="dm-line" x1="0" y1="0" x2="1" y2="0"><stop stopColor="#2c7be5"/><stop offset="1" stopColor="#00a6a6"/></linearGradient>
        <filter id="dm-shadow"><feDropShadow dx="0" dy="8" stdDeviation="16" floodOpacity="0.1"/></filter>
      </defs>

      {/* Browser frame */}
      <rect x="0" y="0" width="560" height="380" rx="16" fill="#ffffff" filter="url(#dm-shadow)" stroke="#d9e4fb" strokeWidth="1"/>
      <rect x="0" y="0" width="560" height="40" rx="16" fill="#f8faff"/>
      <rect x="0" y="28" width="560" height="12" fill="#f8faff"/>
      <circle cx="20" cy="20" r="5" fill="#fca5a5"/><circle cx="36" cy="20" r="5" fill="#fcd34d"/><circle cx="52" cy="20" r="5" fill="#86efac"/>
      <rect x="180" y="12" width="200" height="16" rx="8" fill="#edf3ff" stroke="#d9e4fb" strokeWidth="0.5"/>
      <text x="280" y="23" textAnchor="middle" fontSize="8" fill="#4b5f7e" fontFamily="sans-serif">app.learnpuddle.com/dashboard</text>

      {/* Sidebar */}
      <rect x="1" y="40" width="120" height="339" fill="#f0f4ff" rx="0"/>
      <rect x="12" y="56" width="96" height="28" rx="8" fill="#1850b8" opacity="0.1"/>
      <rect x="24" y="66" width="48" height="8" rx="4" fill="#1850b8"/>
      <rect x="24" y="100" width="64" height="6" rx="3" fill="#c0d5ff"/><rect x="24" y="118" width="56" height="6" rx="3" fill="#c0d5ff"/>
      <rect x="24" y="136" width="72" height="6" rx="3" fill="#c0d5ff"/><rect x="24" y="154" width="48" height="6" rx="3" fill="#c0d5ff"/>
      <rect x="24" y="172" width="60" height="6" rx="3" fill="#c0d5ff"/>

      {/* Main content area heading */}
      <rect x="140" y="56" width="120" height="12" rx="4" fill="#0f2447"/>
      <rect x="140" y="76" width="200" height="6" rx="3" fill="#b0c4ee"/>

      {/* Stat cards row */}
      <g>
        <rect x="140" y="96" width="122" height="64" rx="12" fill="#ffffff" stroke="#d9e4fb" strokeWidth="1"/>
        <rect x="152" y="108" width="40" height="6" rx="3" fill="#4b5f7e" opacity="0.5"/>
        <text x="152" y="138" fontSize="20" fontWeight="bold" fill="#0f2447" fontFamily="sans-serif">2,847</text>
        <rect x="152" y="146" width="50" height="4" rx="2" fill="#16a34a" opacity="0.3"/>

        <rect x="272" y="96" width="122" height="64" rx="12" fill="#ffffff" stroke="#d9e4fb" strokeWidth="1"/>
        <rect x="284" y="108" width="48" height="6" rx="3" fill="#4b5f7e" opacity="0.5"/>
        <text x="284" y="138" fontSize="20" fontWeight="bold" fill="#0f2447" fontFamily="sans-serif">91%</text>
        <rect x="284" y="146" width="90" height="4" rx="2" fill="#2c7be5" opacity="0.2"/><rect x="284" y="146" width="82" height="4" rx="2" fill="#2c7be5" opacity="0.5"/>

        <rect x="404" y="96" width="138" height="64" rx="12" fill="#ffffff" stroke="#d9e4fb" strokeWidth="1"/>
        <rect x="416" y="108" width="56" height="6" rx="3" fill="#4b5f7e" opacity="0.5"/>
        <text x="416" y="138" fontSize="20" fontWeight="bold" fill="#0f2447" fontFamily="sans-serif">24</text>
        <text x="440" y="138" fontSize="10" fill="#4b5f7e" fontFamily="sans-serif">portals</text>
      </g>

      {/* Chart area */}
      <rect x="140" y="176" width="260" height="180" rx="12" fill="#ffffff" stroke="#d9e4fb" strokeWidth="1"/>
      <rect x="156" y="192" width="80" height="8" rx="4" fill="#0f2447"/>
      {/* Y-axis labels */}
      <text x="158" y="228" fontSize="7" fill="#9ca3af" fontFamily="sans-serif">100</text>
      <text x="162" y="260" fontSize="7" fill="#9ca3af" fontFamily="sans-serif">50</text>
      <text x="166" y="292" fontSize="7" fill="#9ca3af" fontFamily="sans-serif">0</text>
      {/* Grid lines */}
      <line x1="180" y1="224" x2="384" y2="224" stroke="#edf3ff" strokeWidth="0.5"/>
      <line x1="180" y1="256" x2="384" y2="256" stroke="#edf3ff" strokeWidth="0.5"/>
      <line x1="180" y1="288" x2="384" y2="288" stroke="#edf3ff" strokeWidth="0.5"/>
      {/* Bars */}
      <rect x="192" y="240" width="16" height="48" rx="4" fill="url(#dm-bar1)" opacity="0.8"/>
      <rect x="224" y="228" width="16" height="60" rx="4" fill="url(#dm-bar1)" opacity="0.85"/>
      <rect x="256" y="236" width="16" height="52" rx="4" fill="url(#dm-bar1)" opacity="0.9"/>
      <rect x="288" y="220" width="16" height="68" rx="4" fill="url(#dm-bar2)" opacity="0.9"/>
      <rect x="320" y="212" width="16" height="76" rx="4" fill="url(#dm-bar2)"/>
      <rect x="352" y="208" width="16" height="80" rx="4" fill="url(#dm-bar2)"/>
      {/* Trend line */}
      <polyline points="200,236 232,224 264,230 296,216 328,208 360,204" fill="none" stroke="url(#dm-line)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" opacity="0.6"/>
      {/* Month labels */}
      <text x="196" y="302" fontSize="7" fill="#9ca3af" fontFamily="sans-serif">Jan</text>
      <text x="228" y="302" fontSize="7" fill="#9ca3af" fontFamily="sans-serif">Feb</text>
      <text x="260" y="302" fontSize="7" fill="#9ca3af" fontFamily="sans-serif">Mar</text>
      <text x="292" y="302" fontSize="7" fill="#9ca3af" fontFamily="sans-serif">Apr</text>
      <text x="324" y="302" fontSize="7" fill="#9ca3af" fontFamily="sans-serif">May</text>
      <text x="356" y="302" fontSize="7" fill="#9ca3af" fontFamily="sans-serif">Jun</text>
      {/* Legend */}
      <rect x="156" y="320" width="8" height="8" rx="2" fill="url(#dm-bar1)"/><text x="168" y="328" fontSize="7" fill="#4b5f7e" fontFamily="sans-serif">Enrolled</text>
      <rect x="210" y="320" width="8" height="8" rx="2" fill="url(#dm-bar2)"/><text x="222" y="328" fontSize="7" fill="#4b5f7e" fontFamily="sans-serif">Completed</text>

      {/* Right sidebar - recent activity */}
      <rect x="412" y="176" width="132" height="180" rx="12" fill="#ffffff" stroke="#d9e4fb" strokeWidth="1"/>
      <rect x="424" y="192" width="72" height="8" rx="4" fill="#0f2447"/>
      {/* Activity items */}
      <g opacity="0.9">
        <circle cx="434" cy="220" r="8" fill="#deeaff"/><rect x="448" y="216" width="72" height="4" rx="2" fill="#b0c4ee"/><rect x="448" y="224" width="48" height="3" rx="1.5" fill="#d9e4fb"/>
        <circle cx="434" cy="246" r="8" fill="#d1fae5"/><rect x="448" y="242" width="64" height="4" rx="2" fill="#b0c4ee"/><rect x="448" y="250" width="56" height="3" rx="1.5" fill="#d9e4fb"/>
        <circle cx="434" cy="272" r="8" fill="#fef3c7"/><rect x="448" y="268" width="80" height="4" rx="2" fill="#b0c4ee"/><rect x="448" y="276" width="44" height="3" rx="1.5" fill="#d9e4fb"/>
        <circle cx="434" cy="298" r="8" fill="#deeaff"/><rect x="448" y="294" width="60" height="4" rx="2" fill="#b0c4ee"/><rect x="448" y="302" width="52" height="3" rx="1.5" fill="#d9e4fb"/>
        <circle cx="434" cy="324" r="8" fill="#fce7f3"/><rect x="448" y="320" width="68" height="4" rx="2" fill="#b0c4ee"/><rect x="448" y="328" width="40" height="3" rx="1.5" fill="#d9e4fb"/>
      </g>
    </svg>
  );
}

function FeatureIllustration({ variant }: { variant: 'courses' | 'tenants' | 'analytics' | 'security' | 'quizzes' | 'video' }) {
  const illustrations: Record<string, React.ReactNode> = {
    courses: (
      <svg viewBox="0 0 200 120" fill="none" className="lp-feature-illust"><defs><linearGradient id="fc1" x1="0" y1="0" x2="200" y2="120" gradientUnits="userSpaceOnUse"><stop stopColor="#1850b8" stopOpacity="0.08"/><stop offset="1" stopColor="#00a6a6" stopOpacity="0.08"/></linearGradient></defs><rect width="200" height="120" rx="12" fill="url(#fc1)"/>
        <rect x="16" y="16" width="168" height="20" rx="6" fill="#fff" stroke="#d9e4fb" strokeWidth="0.5"/><rect x="22" y="23" width="40" height="6" rx="3" fill="#1850b8" opacity="0.6"/>
        <rect x="16" y="44" width="80" height="60" rx="8" fill="#fff" stroke="#d9e4fb" strokeWidth="0.5"/><rect x="24" y="52" width="48" height="4" rx="2" fill="#0f2447" opacity="0.5"/><rect x="24" y="60" width="64" height="3" rx="1.5" fill="#b0c4ee"/><rect x="24" y="68" width="56" height="3" rx="1.5" fill="#b0c4ee"/><rect x="24" y="80" width="40" height="12" rx="6" fill="#1850b8" opacity="0.15"/><rect x="30" y="84" width="28" height="4" rx="2" fill="#1850b8" opacity="0.5"/>
        <rect x="104" y="44" width="80" height="60" rx="8" fill="#fff" stroke="#d9e4fb" strokeWidth="0.5"/><rect x="112" y="52" width="44" height="4" rx="2" fill="#0f2447" opacity="0.5"/><rect x="112" y="60" width="60" height="3" rx="1.5" fill="#b0c4ee"/><rect x="112" y="68" width="52" height="3" rx="1.5" fill="#b0c4ee"/><rect x="112" y="80" width="40" height="12" rx="6" fill="#16a34a" opacity="0.15"/><rect x="118" y="84" width="28" height="4" rx="2" fill="#16a34a" opacity="0.5"/>
      </svg>
    ),
    tenants: (
      <svg viewBox="0 0 200 120" fill="none" className="lp-feature-illust"><defs><linearGradient id="ft1" x1="0" y1="0" x2="200" y2="120" gradientUnits="userSpaceOnUse"><stop stopColor="#00a6a6" stopOpacity="0.08"/><stop offset="1" stopColor="#1850b8" stopOpacity="0.08"/></linearGradient></defs><rect width="200" height="120" rx="12" fill="url(#ft1)"/>
        <rect x="32" y="20" width="56" height="36" rx="8" fill="#fff" stroke="#d9e4fb" strokeWidth="0.5"/><circle cx="48" cy="32" r="6" fill="#1850b8" opacity="0.15"/><rect x="58" y="30" width="24" height="4" rx="2" fill="#0f2447" opacity="0.4"/><rect x="38" y="44" width="44" height="3" rx="1.5" fill="#b0c4ee"/>
        <rect x="112" y="20" width="56" height="36" rx="8" fill="#fff" stroke="#d9e4fb" strokeWidth="0.5"/><circle cx="128" cy="32" r="6" fill="#00a6a6" opacity="0.15"/><rect x="138" y="30" width="24" height="4" rx="2" fill="#0f2447" opacity="0.4"/><rect x="118" y="44" width="44" height="3" rx="1.5" fill="#b0c4ee"/>
        <rect x="72" y="66" width="56" height="36" rx="8" fill="#fff" stroke="#d9e4fb" strokeWidth="0.5"/><circle cx="88" cy="78" r="6" fill="#d97706" opacity="0.15"/><rect x="98" y="76" width="24" height="4" rx="2" fill="#0f2447" opacity="0.4"/><rect x="78" y="90" width="44" height="3" rx="1.5" fill="#b0c4ee"/>
        <line x1="60" y1="56" x2="88" y2="66" stroke="#d9e4fb" strokeWidth="1" strokeDasharray="3 2"/><line x1="140" y1="56" x2="112" y2="66" stroke="#d9e4fb" strokeWidth="1" strokeDasharray="3 2"/>
      </svg>
    ),
    analytics: (
      <svg viewBox="0 0 200 120" fill="none" className="lp-feature-illust"><defs><linearGradient id="fa1" x1="0" y1="120" x2="200" y2="0" gradientUnits="userSpaceOnUse"><stop stopColor="#1850b8" stopOpacity="0.06"/><stop offset="1" stopColor="#16a34a" stopOpacity="0.06"/></linearGradient><linearGradient id="fa2" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#2c7be5"/><stop offset="1" stopColor="#1850b8"/></linearGradient></defs><rect width="200" height="120" rx="12" fill="url(#fa1)"/>
        <polyline points="20,90 50,70 80,78 110,50 140,42 170,30" fill="none" stroke="url(#fa2)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
        <polygon points="20,90 50,70 80,78 110,50 140,42 170,30 170,100 20,100" fill="url(#fa2)" opacity="0.06"/>
        <circle cx="50" cy="70" r="3" fill="#2c7be5"/><circle cx="110" cy="50" r="3" fill="#2c7be5"/><circle cx="170" cy="30" r="3" fill="#2c7be5"/>
        <rect x="20" y="100" width="160" height="0.5" fill="#d9e4fb"/>
      </svg>
    ),
    security: (
      <svg viewBox="0 0 200 120" fill="none" className="lp-feature-illust"><defs><linearGradient id="fs1" x1="100" y1="10" x2="100" y2="110" gradientUnits="userSpaceOnUse"><stop stopColor="#1850b8" stopOpacity="0.12"/><stop offset="1" stopColor="#1850b8" stopOpacity="0.02"/></linearGradient></defs><rect width="200" height="120" rx="12" fill="#fafcff"/>
        <path d="M100 18 L140 34 V62 C140 86 120 100 100 106 C80 100 60 86 60 62 V34 Z" fill="url(#fs1)" stroke="#1850b8" strokeWidth="1" strokeOpacity="0.2"/>
        <path d="M88 60 L96 68 L114 50" stroke="#16a34a" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
      </svg>
    ),
    quizzes: (
      <svg viewBox="0 0 200 120" fill="none" className="lp-feature-illust"><rect width="200" height="120" rx="12" fill="#fafcff"/>
        <rect x="30" y="16" width="140" height="24" rx="8" fill="#fff" stroke="#d9e4fb" strokeWidth="0.5"/><rect x="40" y="24" width="80" height="6" rx="3" fill="#0f2447" opacity="0.3"/><circle cx="152" cy="28" r="6" fill="#16a34a" opacity="0.15"/><path d="M149 28 L151 30 L155 26" stroke="#16a34a" strokeWidth="1.5" strokeLinecap="round" fill="none"/>
        <rect x="30" y="48" width="140" height="24" rx="8" fill="#fff" stroke="#d9e4fb" strokeWidth="0.5"/><rect x="40" y="56" width="96" height="6" rx="3" fill="#0f2447" opacity="0.3"/><circle cx="152" cy="60" r="6" fill="#16a34a" opacity="0.15"/><path d="M149 60 L151 62 L155 58" stroke="#16a34a" strokeWidth="1.5" strokeLinecap="round" fill="none"/>
        <rect x="30" y="80" width="140" height="24" rx="8" fill="#fff" stroke="#d9e4fb" strokeWidth="0.5"/><rect x="40" y="88" width="72" height="6" rx="3" fill="#0f2447" opacity="0.3"/><circle cx="152" cy="92" r="6" fill="#fef3c7" stroke="#d97706" strokeWidth="1"/>
      </svg>
    ),
    video: (
      <svg viewBox="0 0 200 120" fill="none" className="lp-feature-illust"><defs><linearGradient id="fv1" x1="0" y1="0" x2="200" y2="120" gradientUnits="userSpaceOnUse"><stop stopColor="#0f2447" stopOpacity="0.04"/><stop offset="1" stopColor="#1850b8" stopOpacity="0.04"/></linearGradient></defs><rect width="200" height="120" rx="12" fill="url(#fv1)"/>
        <rect x="24" y="16" width="152" height="72" rx="8" fill="#0f2447" opacity="0.08"/>
        <circle cx="100" cy="52" r="16" fill="#fff" opacity="0.9"/><path d="M95 44 L110 52 L95 60Z" fill="#1850b8"/>
        <rect x="24" y="96" width="120" height="4" rx="2" fill="#d9e4fb"/><rect x="24" y="96" width="72" height="4" rx="2" fill="#2c7be5" opacity="0.5"/>
        <text x="150" y="100" fontSize="8" fill="#4b5f7e" fontFamily="sans-serif">4:32</text>
      </svg>
    ),
  };
  return <>{illustrations[variant]}</>;
}

const featureIllustMap: Record<string, 'courses' | 'tenants' | 'analytics' | 'security' | 'quizzes' | 'video'> = {
  'Course Builder': 'courses',
  'Multi-Tenant Delivery': 'tenants',
  'Reporting & Analytics': 'analytics',
  'Security & Access Control': 'security',
  'Assessment Engine': 'quizzes',
  'Video Infrastructure': 'video',
};

const statsItems = [
  { value: '10x', label: 'Faster onboarding rollout' },
  { value: '91%', label: 'Average completion rate' },
  { value: '24/7', label: 'Platform availability' },
  { value: '100%', label: 'Audit-ready evidence' },
];

type LiveDemoKey = 'schools' | 'corporate' | 'fitness';

type LiveDemoInputState = {
  organization: string;
  audience: string;
  target: string;
  source: string;
};

type LiveDemoConfig = {
  key: LiveDemoKey;
  label: string;
  eyebrow: string;
  title: string;
  description: string;
  audienceLabel: string;
  targetLabel: string;
  sourceLabel: string;
  previewBadge: string;
  accent: string;
};

type LiveDemoLayerId = 'source' | 'pathway' | 'practice' | 'evidence';

type LiveDemoExplorerLayer = {
  id: LiveDemoLayerId;
  label: string;
  eyebrow: string;
  title: string;
  description: string;
  metric: string;
  metricLabel: string;
};

const liveDemoTabs: LiveDemoConfig[] = [
  {
    key: 'schools',
    label: 'Schools LMS',
    eyebrow: 'Faculty development',
    title: 'Build a school PD portal from a real training brief.',
    description: 'Type a school program, CPD mandate, or workshop idea and watch the portal preview reshape around faculty learning.',
    audienceLabel: 'Cohort or role',
    targetLabel: 'CPD hour target',
    sourceLabel: 'Training brief, policy, or workshop notes',
    previewBadge: 'School learning portal',
    accent: '#E8623A',
  },
  {
    key: 'corporate',
    label: 'Corporate L&D',
    eyebrow: 'Workforce enablement',
    title: 'Turn internal knowledge into role-based training.',
    description: 'Draft an onboarding, compliance, sales, or SOP rollout and see the enterprise learning view update live.',
    audienceLabel: 'Role or department',
    targetLabel: 'Due window',
    sourceLabel: 'SOP, policy, product, or onboarding notes',
    previewBadge: 'Enterprise academy',
    accent: '#3156D4',
  },
  {
    key: 'fitness',
    label: 'Gym & Nutrition',
    eyebrow: 'Wellness coaching',
    title: 'Preview a branded gym learning and nutrition tracker.',
    description: 'Set a member goal, calorie target, and training focus to see how LearnPuddle can support fitness education.',
    audienceLabel: 'Member group',
    targetLabel: 'Daily calorie target',
    sourceLabel: 'Training, nutrition, or habit focus',
    previewBadge: 'Fitness learning hub',
    accent: '#1CA978',
  },
];

const liveDemoDefaults: Record<LiveDemoKey, LiveDemoInputState> = {
  schools: {
    organization: 'Keystone International School',
    audience: 'Grade 6-10 faculty',
    target: '50 CPD hours',
    source:
      'Run a teacher development pathway on assessment moderation, AI classroom practice, student feedback, and IB evidence logs.',
  },
  corporate: {
    organization: 'Northstar Operations',
    audience: 'Frontline managers',
    target: '21 days',
    source:
      'Launch SOP certification for new branch managers covering service standards, safety checks, escalation, and product updates.',
  },
  fitness: {
    organization: 'Pulse Performance Gym',
    audience: 'Strength members',
    target: '2,250 kcal',
    source:
      'Coach members through strength basics, protein planning, daily calorie awareness, hydration, recovery, and weekly progress habits.',
  },
};

const liveDemoMetricLabels: Record<LiveDemoKey, string[]> = {
  schools: ['Completion', 'CPD evidence', 'Departments'],
  corporate: ['Readiness', 'SOP checks', 'Teams'],
  fitness: ['Adherence', 'Calories', 'Streak'],
};

const liveDemoActionCopy: Record<LiveDemoKey, string[]> = {
  schools: ['Generate quiz from workshop transcript', 'Send reminder to faculty behind target', 'Export CPD evidence report'],
  corporate: ['Create manager checklist', 'Schedule renewal reminder', 'Export compliance packet'],
  fitness: ['Log daily nutrition lesson', 'Adjust calorie habit prompt', 'Issue weekly progress badge'],
};

const heroProofItems = [
  { value: '10x', label: 'faster course rollout from existing content' },
  { value: '91%', label: 'guided completion benchmark for cohorts' },
  { value: '1 platform', label: 'for schools, teams, branches, and academies' },
];

const trainingTemplateCards = [
  {
    key: 'education',
    icon: AcademicCapIcon,
    title: 'Education',
    description: 'CPD hours, IB certifications, faculty development, curriculum rollout, and department reports.',
    chips: ['CPD tracking', 'HOD views', 'Certificates'],
  },
  {
    key: 'corporate',
    icon: BuildingOfficeIcon,
    title: 'Corporate L&D',
    description: 'Onboarding, compliance, sales enablement, role-based pathways, and manager completion controls.',
    chips: ['SOPs', 'Renewals', 'Evidence'],
  },
  {
    key: 'manufacturing',
    icon: WrenchScrewdriverIcon,
    title: 'Manufacturing',
    description: 'Safety SOPs, machine readiness, supervisor sign-off, recertification cycles, and floor-level visibility.',
    chips: ['Safety', 'Readiness', 'Sign-off'],
  },
  {
    key: 'healthcare',
    icon: HeartIcon,
    title: 'Healthcare',
    description: 'Clinical protocols, recurring certifications, multi-role competency checks, and compliance reminders.',
    chips: ['Protocols', 'Renewals', 'Roles'],
  },
  {
    key: 'hospitality',
    icon: StarIcon,
    title: 'Hospitality',
    description: 'Guest experience standards, outlet launch onboarding, service drills, and branch-level scorecards.',
    chips: ['Frontline', 'Branches', 'Service'],
  },
  {
    key: 'academies',
    icon: RocketLaunchIcon,
    title: 'Academies',
    description: 'Branded learner journeys, cohorts, instructor workflows, paid programs, and certification tracks.',
    chips: ['Cohorts', 'Programs', 'Progress'],
  },
];

const liveDemoStopWords = new Set([
  'about',
  'after',
  'along',
  'also',
  'and',
  'covering',
  'daily',
  'from',
  'into',
  'learning',
  'member',
  'members',
  'pathway',
  'through',
  'training',
  'with',
]);

function getLiveDemoConfig(key: LiveDemoKey): LiveDemoConfig {
  return liveDemoTabs.find((item) => item.key === key) ?? liveDemoTabs[0];
}

function getSourceKeywords(source: string): string[] {
  const words = source
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, ' ')
    .split(/\s+/)
    .map((word) => word.trim())
    .filter((word) => word.length > 3 && !liveDemoStopWords.has(word));

  return Array.from(new Set(words)).slice(0, 4);
}

function titleCase(value: string): string {
  return value
    .split(/[\s-]+/)
    .filter(Boolean)
    .map((word) => `${word.charAt(0).toUpperCase()}${word.slice(1)}`)
    .join(' ');
}

function getLiveDemoModules(key: LiveDemoKey, input: LiveDemoInputState, keywords: string[]): string[] {
  const first = titleCase(keywords[0] ?? 'Foundation');
  const second = titleCase(keywords[1] ?? (key === 'fitness' ? 'Nutrition' : 'Practice'));
  const third = titleCase(keywords[2] ?? (key === 'corporate' ? 'Certification' : 'Evidence'));
  const audience = input.audience.trim() || getLiveDemoConfig(key).audienceLabel;

  if (key === 'fitness') {
    return [
      `${first} basics for ${audience}`,
      `${second} plan and daily calories`,
      `${third} habit check-in`,
    ];
  }

  if (key === 'corporate') {
    return [
      `${first} onboarding path`,
      `${second} SOP scenario checks`,
      `${third} sign-off workflow`,
    ];
  }

  return [
    `${first} workshop module`,
    `${second} classroom practice`,
    `${third} and CPD reflection`,
  ];
}

function getLiveDemoMetricValues(key: LiveDemoKey, input: LiveDemoInputState, source: string): string[] {
  const completion = `${Math.min(96, 82 + Math.floor(source.length / 42))}%`;

  if (key === 'fitness') {
    return [completion, input.target.trim() || '2,200 kcal', '12 days'];
  }

  if (key === 'corporate') {
    return [completion, '8 checks', input.audience.trim().split(/\s+/)[0] || '4 roles'];
  }

  return [completion, input.target.trim() || '50 hours', '6 teams'];
}

function getLiveDemoExplorerLayers(
  key: LiveDemoKey,
  input: LiveDemoInputState,
  modules: string[],
  metricValues: string[],
  keywords: string[],
): LiveDemoExplorerLayer[] {
  const config = getLiveDemoConfig(key);
  const audience = input.audience.trim() || config.audienceLabel;
  const target = input.target.trim() || config.targetLabel;
  const source = input.source.trim() || 'Type a brief to reshape this portal preview.';
  const signal = titleCase(keywords[0] ?? (key === 'fitness' ? 'Nutrition' : key === 'corporate' ? 'SOP' : 'CPD'));
  const secondSignal = titleCase(keywords[1] ?? (key === 'fitness' ? 'Recovery' : key === 'corporate' ? 'Readiness' : 'Classroom'));

  if (key === 'fitness') {
    return [
      {
        id: 'source',
        label: 'Brief',
        eyebrow: 'Input layer',
        title: `${signal} coaching brief`,
        description: source,
        metric: target,
        metricLabel: 'daily target',
      },
      {
        id: 'pathway',
        label: 'Plan',
        eyebrow: 'Generated pathway',
        title: modules[0] ?? 'Strength member basics',
        description: `A member-facing path for ${audience} with lessons, check-ins, and habit prompts.`,
        metric: `${modules.length}`,
        metricLabel: 'learning blocks',
      },
      {
        id: 'practice',
        label: 'Habits',
        eyebrow: 'Daily coaching',
        title: `${secondSignal} habit loop`,
        description: 'Calories, protein, hydration, recovery, and weekly reflection stay inside the same branded learning hub.',
        metric: '12',
        metricLabel: 'day streak',
      },
      {
        id: 'evidence',
        label: 'Progress',
        eyebrow: 'Outcome proof',
        title: 'Trainer-ready progress view',
        description: 'Coaches see adherence, lesson completion, and nutrition consistency without spreadsheet follow-up.',
        metric: metricValues[0],
        metricLabel: 'adherence',
      },
    ];
  }

  if (key === 'corporate') {
    return [
      {
        id: 'source',
        label: 'SOP',
        eyebrow: 'Input layer',
        title: `${signal} source pack`,
        description: source,
        metric: '4',
        metricLabel: 'knowledge sources',
      },
      {
        id: 'pathway',
        label: 'Path',
        eyebrow: 'Generated pathway',
        title: modules[0] ?? 'Manager onboarding path',
        description: `Role-based modules for ${audience} with scenario checks and manager sign-off.`,
        metric: `${modules.length}`,
        metricLabel: 'modules',
      },
      {
        id: 'practice',
        label: 'Checks',
        eyebrow: 'Practice layer',
        title: `${secondSignal} scenario checks`,
        description: 'Learners answer branch-level cases, complete checklists, and trigger reminders before deadlines drift.',
        metric: metricValues[1],
        metricLabel: 'SOP checks',
      },
      {
        id: 'evidence',
        label: 'Audit',
        eyebrow: 'Evidence layer',
        title: 'Compliance packet',
        description: 'Every completion, quiz score, checklist, and manager action is ready for audit and leadership review.',
        metric: metricValues[0],
        metricLabel: 'readiness',
      },
    ];
  }

  return [
    {
      id: 'source',
      label: 'Brief',
      eyebrow: 'Input layer',
      title: `${signal} training brief`,
      description: source,
      metric: target,
      metricLabel: 'CPD goal',
    },
    {
      id: 'pathway',
      label: 'Path',
      eyebrow: 'Generated pathway',
      title: modules[0] ?? 'Faculty workshop module',
      description: `Structured faculty development for ${audience}, with video, notes, quiz, and reflection evidence.`,
      metric: `${modules.length}`,
      metricLabel: 'modules',
    },
    {
      id: 'practice',
      label: 'Teach',
      eyebrow: 'Classroom practice',
      title: `${secondSignal} application loop`,
      description: 'Teachers move from lesson content into classroom practice, discussion, quiz checks, and CPD reflection.',
      metric: '5',
      metricLabel: 'quiz prompts',
    },
    {
      id: 'evidence',
      label: 'Proof',
      eyebrow: 'Evidence layer',
      title: 'Principal and HOD evidence view',
      description: 'Completion, reflections, department progress, and CPD reports are visible without manual chasing.',
      metric: metricValues[0],
      metricLabel: 'completion',
    },
  ];
}

function CourseBuilderPreview() {
  return (
    <div className="lp-course-builder" aria-label="AI course builder preview">
      <div className="lp-course-builder-bar">
        <span />
        <span />
        <span />
        <strong>learnpuddle.com/course-builder</strong>
      </div>

      <div className="lp-course-builder-source">
        <p>Source knowledge</p>
        {[
          ['VID', 'Workshop recording', '47 min video'],
          ['PDF', 'Policy handbook', '32 pages'],
          ['SOP', 'Safety checklist', 'Plant ops'],
        ].map(([tag, title, meta]) => (
          <div key={tag} className="lp-source-file">
            <span>{tag}</span>
            <div>
              <b>{title}</b>
              <small>{meta}</small>
            </div>
          </div>
        ))}
      </div>

      <div className="lp-course-builder-workspace">
        <div className="lp-builder-heading">
          <div>
            <h2>AI builds the learning path.</h2>
            <p>Modules, transcripts, quizzes, translations, and certificates from the work you already have.</p>
          </div>
          <span>Generating</span>
        </div>

        <div className="lp-builder-flow">
          {[
            ['1', 'Upload', 'Video, PDF, DOCX, PPTX, or SOP.'],
            ['2', 'Structure', 'Modules, outcomes, deadlines, cohorts.'],
            ['3', 'Teach', 'Captions, lesson chat, notes, quizzes.'],
            ['4', 'Prove', 'Reports, skills, certificates, audit trail.'],
          ].map(([step, title, body]) => (
            <div key={step} className="lp-builder-step">
              <i>{step}</i>
              <b>{title}</b>
              <span>{body}</span>
            </div>
          ))}
        </div>

        <div className="lp-builder-live-row">
          <div className="lp-builder-video">
            <div className="lp-builder-play">▶</div>
            <div>
              <b>Lesson: Assessment moderation</b>
              <span />
            </div>
          </div>
          <div className="lp-builder-chat">
            <p>Ask this lesson: "Explain moderation for new teachers."</p>
            <p>Generate 5 quiz questions from this section.</p>
          </div>
        </div>
      </div>

      <div className="lp-course-builder-path">
        <p>Published path</p>
        {[
          ['Module 1: Foundations', 'Video + transcript'],
          ['Module 2: Practice', 'Quiz + reflection'],
          ['Certificate', 'Auto-issued at 80%'],
        ].map(([title, meta]) => (
          <div key={title} className="lp-published-module">
            <b>{title}</b>
            <small>{meta}</small>
            <span>Ready</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function LiveTemplateStudio({
  activeDemo,
  liveDemoInput,
  onSelectDemo,
  onUpdateField,
}: {
  activeDemo: LiveDemoKey;
  liveDemoInput: LiveDemoInputState;
  onSelectDemo: (key: LiveDemoKey) => void;
  onUpdateField: (field: keyof LiveDemoInputState, value: string) => void;
}) {
  const config = getLiveDemoConfig(activeDemo);
  const keywords = getSourceKeywords(liveDemoInput.source);
  const modules = getLiveDemoModules(activeDemo, liveDemoInput, keywords);
  const metricValues = getLiveDemoMetricValues(activeDemo, liveDemoInput, liveDemoInput.source);
  const metricLabels = liveDemoMetricLabels[activeDemo];
  const explorerLayers = getLiveDemoExplorerLayers(activeDemo, liveDemoInput, modules, metricValues, keywords);
  const [activeLayerId, setActiveLayerId] = React.useState<LiveDemoLayerId>('pathway');
  const activeLayer = explorerLayers.find((layer) => layer.id === activeLayerId) ?? explorerLayers[1] ?? explorerLayers[0]!;
  const organization = liveDemoInput.organization.trim() || 'Your organization';
  const audience = liveDemoInput.audience.trim() || config.audienceLabel;
  const target = liveDemoInput.target.trim() || config.targetLabel;
  const sourcePreview = liveDemoInput.source.trim() || 'Type a brief to reshape this portal preview.';
  const modelTitle =
    activeDemo === 'fitness'
      ? 'Wellness learning model'
      : activeDemo === 'corporate'
        ? 'Enterprise academy model'
        : 'Faculty development model';

  return (
    <div className={`lp-live-demo-shell lp-live-demo-${activeDemo}`}>
      <div className="lp-live-demo-input-panel">
        <div className="lp-live-demo-tabs" role="tablist" aria-label="Live demo templates">
          {liveDemoTabs.map((item) => (
            <button
              key={item.key}
              type="button"
              role="tab"
              aria-selected={activeDemo === item.key}
              className={`lp-live-demo-tab ${activeDemo === item.key ? 'is-active' : ''}`}
              onClick={() => onSelectDemo(item.key)}
              style={{ '--demo-accent': item.accent } as React.CSSProperties}
            >
              <span>{item.eyebrow}</span>
              {item.label}
            </button>
          ))}
        </div>

        <div className="lp-live-demo-editor">
          <div className="lp-live-demo-editor-head">
            <p className="lp-card-eyebrow">{config.eyebrow}</p>
            <h3>{config.title}</h3>
            <p>{config.description}</p>
          </div>

          <label className="lp-live-field">
            <span>Organization name</span>
            <input
              type="text"
              aria-label="Organization name"
              value={liveDemoInput.organization}
              onChange={(event) => onUpdateField('organization', event.target.value)}
            />
          </label>

          <div className="lp-live-field-row">
            <label className="lp-live-field">
              <span>{config.audienceLabel}</span>
              <input
                type="text"
                aria-label={config.audienceLabel}
                value={liveDemoInput.audience}
                onChange={(event) => onUpdateField('audience', event.target.value)}
              />
            </label>
            <label className="lp-live-field">
              <span>{config.targetLabel}</span>
              <input
                type="text"
                aria-label={config.targetLabel}
                value={liveDemoInput.target}
                onChange={(event) => onUpdateField('target', event.target.value)}
              />
            </label>
          </div>

          <label className="lp-live-field">
            <span>{config.sourceLabel}</span>
            <textarea
              aria-label={config.sourceLabel}
              value={liveDemoInput.source}
              onChange={(event) => onUpdateField('source', event.target.value)}
              rows={5}
            />
          </label>

          <div className="lp-live-token-row" aria-label="Detected learning signals">
            {(keywords.length ? keywords : ['course', 'quiz', 'insight']).map((keyword) => (
              <span key={keyword}>{titleCase(keyword)}</span>
            ))}
          </div>
        </div>
      </div>

      <div className="lp-live-preview-panel" style={{ '--demo-accent': config.accent } as React.CSSProperties}>
        <div className="lp-live-browser-bar">
          <span />
          <span />
          <span />
          <strong>{organization.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'tenant'}.learnpuddle.com</strong>
        </div>

        <div className="lp-live-preview-body">
          <div className="lp-live-preview-top">
            <div>
              <p>{config.previewBadge}</p>
              <h3>{organization}</h3>
              <span>{audience} · {target}</span>
            </div>
            <div className="lp-live-preview-mark">
              {activeDemo === 'schools' ? 'PD' : activeDemo === 'corporate' ? 'L&D' : 'GYM'}
            </div>
          </div>

          <div className="lp-live-metrics">
            {metricLabels.map((label, index) => (
              <div key={label} className="lp-live-metric">
                <strong>{metricValues[index]}</strong>
                <span>{label}</span>
              </div>
            ))}
          </div>

          <div className="lp-live-forge-layout">
            <section className="lp-live-forge-stage" aria-label="Interactive learning model explorer">
              <div className="lp-live-forge-toolbar">
                <div>
                  <span>Learning Forge</span>
                  <strong>{modelTitle}</strong>
                </div>
                <small>{keywords.length ? `${keywords.length} signals detected` : 'Ready for your brief'}</small>
              </div>

              <div className="lp-live-forge-body">
                <div className="lp-live-layer-list" aria-label="Learning model layers">
                  {explorerLayers.map((layer) => (
                    <button
                      key={layer.id}
                      type="button"
                      className={`lp-live-layer-button ${activeLayer.id === layer.id ? 'is-active' : ''}`}
                      onClick={() => setActiveLayerId(layer.id)}
                      aria-pressed={activeLayer.id === layer.id}
                    >
                      <span>{layer.label}</span>
                      <strong>{layer.title}</strong>
                    </button>
                  ))}
                </div>

                <div className="lp-live-orbit-stage">
                  <div className="lp-live-orbit" aria-label="Learning layer map">
                    <span className="lp-live-orbit-ring lp-live-orbit-ring-a" />
                    <span className="lp-live-orbit-ring lp-live-orbit-ring-b" />
                    <span className="lp-live-orbit-ring lp-live-orbit-ring-c" />
                    <div className="lp-live-orbit-core">
                      <b>{keywords[0] ? titleCase(keywords[0]) : activeDemo === 'fitness' ? 'Wellness' : activeDemo === 'corporate' ? 'SOP' : 'CPD'}</b>
                      <span>{organization}</span>
                    </div>
                    {explorerLayers.map((layer) => (
                      <button
                        key={layer.id}
                        type="button"
                        className={`lp-live-orbit-node lp-live-orbit-node-${layer.id} ${activeLayer.id === layer.id ? 'is-active' : ''}`}
                        onClick={() => setActiveLayerId(layer.id)}
                        aria-label={`Focus ${layer.label} layer`}
                      >
                        <span />
                        <b>{layer.label}</b>
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <article className="lp-live-layer-detail">
                <div>
                  <p>{activeLayer.eyebrow}</p>
                  <h4>{activeLayer.title}</h4>
                  <span>{activeLayer.description}</span>
                </div>
                <aside>
                  <strong>{activeLayer.metric}</strong>
                  <span>{activeLayer.metricLabel}</span>
                </aside>
              </article>
            </section>

            <aside className="lp-live-stack-panel">
              <div className="lp-live-course-list">
                <div className="lp-live-panel-label">Generated pathway</div>
                {modules.map((module, index) => (
                  <article key={module} className="lp-live-module-card">
                    <span>{String(index + 1).padStart(2, '0')}</span>
                    <div>
                      <h4>{module}</h4>
                      <p>{index === 0 ? 'Video, notes, and discussion' : index === 1 ? 'Quiz and practical checklist' : 'Certificate-ready evidence'}</p>
                    </div>
                  </article>
                ))}
              </div>

              <div className="lp-live-action-card">
                <div className="lp-live-panel-label">
                  {activeDemo === 'fitness' ? 'Nutrition and habit layer' : 'Action queue'}
                </div>
                {activeDemo === 'fitness' ? (
                  <div className="lp-live-nutrition">
                    <div>
                      <strong>{target}</strong>
                      <span>Daily calorie plan</span>
                    </div>
                    <div>
                      <strong>140g</strong>
                      <span>Protein target</span>
                    </div>
                    <div>
                      <strong>3.2L</strong>
                      <span>Hydration reminder</span>
                    </div>
                  </div>
                ) : (
                  <ul className="lp-live-action-list">
                    {liveDemoActionCopy[activeDemo].map((action) => (
                      <li key={action}>
                        <CheckCircleIcon className="lp-live-action-icon" aria-hidden="true" />
                        {action}
                      </li>
                    ))}
                  </ul>
                )}
                <div className="lp-live-source-card">
                  <span>Source signal</span>
                  <p>{sourcePreview}</p>
                </div>
              </div>
            </aside>
          </div>
        </div>
      </div>
    </div>
  );
}

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
  const [activeLiveDemo, setActiveLiveDemo] = React.useState<LiveDemoKey>('schools');
  const [liveDemoInputs, setLiveDemoInputs] =
    React.useState<Record<LiveDemoKey, LiveDemoInputState>>(liveDemoDefaults);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = React.useState(false);

  React.useEffect(() => {
    if (!showCalModal) return;
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = originalOverflow;
    };
  }, [showCalModal]);

  React.useEffect(() => {
    const closeMenuOnDesktop = () => {
      if (window.innerWidth > 900) {
        setIsMobileMenuOpen(false);
      }
    };

    window.addEventListener('resize', closeMenuOnDesktop);
    return () => window.removeEventListener('resize', closeMenuOnDesktop);
  }, []);

  React.useEffect(() => {
    if (!isMobileMenuOpen) return undefined;

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsMobileMenuOpen(false);
      }
    };

    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [isMobileMenuOpen]);

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
    setIsMobileMenuOpen(false);
    if (!inlineDemoEnabled) {
      window.open(bookDemoUrl, '_blank', 'noopener,noreferrer');
      return;
    }
    setCalLoadError('');
    setShowCalModal(true);
  }, [bookDemoUrl, inlineDemoEnabled]);

  const closeMobileMenu = React.useCallback(() => {
    setIsMobileMenuOpen(false);
  }, []);

  const updateLiveDemoField = React.useCallback((field: keyof LiveDemoInputState, value: string) => {
    setLiveDemoInputs((current) => ({
      ...current,
      [activeLiveDemo]: {
        ...current[activeLiveDemo],
        [field]: value,
      },
    }));
  }, [activeLiveDemo]);

  const activeSolution = solutionContent[activeTab];
  const activeLiveDemoInput = liveDemoInputs[activeLiveDemo];

  return (
    <div className="lp-page">
      <div className="lp-bg-shape lp-bg-shape-a" />
      <div className="lp-bg-shape lp-bg-shape-b" />

      {/* ── Header ── */}
      <header className="lp-header">
        <div className="lp-container lp-header-inner">
          <a href="/" className="lp-logo" aria-label="LearnPuddle Home">
            <LogoMark className="lp-logo-mark" />
            LearnPuddle
          </a>
          <nav className={`lp-nav ${isMobileMenuOpen ? 'is-open' : ''}`} aria-label="Primary">
            <a href="#templates" onClick={closeMobileMenu}>Templates</a>
            <a href="#live-demo" onClick={closeMobileMenu}>Live Demo</a>
            <a href="#platform" onClick={closeMobileMenu}>Platform</a>
            <a href="#solutions" onClick={closeMobileMenu}>Solutions</a>
            <a href="#industries" onClick={closeMobileMenu}>Industries</a>
            <a href="#security" onClick={closeMobileMenu}>Security</a>
            <a href="#demo" onClick={closeMobileMenu}>Demo</a>
          </nav>
          <div className="lp-header-actions">
            <CTAButton onClick={openBookDemo} className="lp-btn lp-btn-primary lp-header-cta-desktop">
              Book Demo
            </CTAButton>
            <button
              type="button"
              className="lp-menu-toggle"
              aria-label={isMobileMenuOpen ? 'Close navigation menu' : 'Open navigation menu'}
              aria-expanded={isMobileMenuOpen}
              onClick={() => setIsMobileMenuOpen((value) => !value)}
            >
              {isMobileMenuOpen ? (
                <XMarkIcon className="lp-menu-icon" aria-hidden="true" />
              ) : (
                <Bars3Icon className="lp-menu-icon" aria-hidden="true" />
              )}
            </button>
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
                AI-era learning platform
              </p>
              <h1>Turn knowledge into learning that <em>responds.</em></h1>
              <p>
                LearnPuddle turns videos, documents, policies, and playbooks into branded learning
                portals with courses, quizzes, captions, progress tracking, and insight-rich reports.
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
                <a href="#templates" className="lp-btn lp-btn-secondary">
                  Explore Templates
                </a>
              </div>
              <div className="lp-hero-proof-grid" aria-label="Product proof">
                {heroProofItems.map((item) => (
                  <div key={item.label} className="lp-hero-proof-card">
                    <strong>{item.value}</strong>
                    <span>{item.label}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="lp-hero-panel">
              <CourseBuilderPreview />
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

        {/* ── Stats Strip ── */}
        <section className="lp-stats-strip" aria-label="Key metrics">
          <div className="lp-container lp-stats-grid">
            {statsItems.map((stat) => (
              <div key={stat.label} className="lp-stat-item">
                <span className="lp-stat-value">{stat.value}</span>
                <span className="lp-stat-label">{stat.label}</span>
              </div>
            ))}
          </div>
        </section>

        {/* ── Template Gallery ── */}
        <section id="templates" className="lp-section lp-section-templates">
          <div className="lp-container">
            <SectionHeader
              kicker="Templates"
              title="Start with the right training world."
              description="LearnPuddle should feel purpose-built for each audience. Same engine underneath, different vocabulary, metrics, program templates, and learner motivation on top."
            />
            <div className="lp-template-grid">
              {trainingTemplateCards.map((template) => (
                <article key={template.key} className={`lp-template-card lp-template-card-${template.key}`}>
                  <div className="lp-template-card-top">
                    <h3>{template.title}</h3>
                    <span className="lp-template-icon">
                      <template.icon className="lp-template-icon-svg" aria-hidden="true" />
                    </span>
                  </div>
                  <p>{template.description}</p>
                  <div className="lp-template-chip-row">
                    {template.chips.map((chip) => (
                      <span key={chip}>{chip}</span>
                    ))}
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* ── Live Template Studio ── */}
        <section id="live-demo" className="lp-section lp-section-live-demo">
          <div className="lp-container">
            <SectionHeader
              kicker="Live Demo Lab"
              title="Type a use case. Watch a branded LMS take shape."
              description="A website-native preview for buyers: schools, enterprise teams, and fitness operators can see the tenant language, pathways, analytics, and next actions adapt to their own training context."
            />
            <LiveTemplateStudio
              activeDemo={activeLiveDemo}
              liveDemoInput={activeLiveDemoInput}
              onSelectDemo={setActiveLiveDemo}
              onUpdateField={updateLiveDemoField}
            />
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
            <div className="lp-stack-container">
              {platformCapabilities.map((cap, index) => (
                <article
                  key={cap.title}
                  className="lp-stack-card lp-card-feature"
                  style={{ '--stack-index': index } as React.CSSProperties}
                >
                  <div className="lp-stack-card-inner">
                    {featureIllustMap[cap.title] && (
                      <div className="lp-stack-illust">
                        <FeatureIllustration variant={featureIllustMap[cap.title]} />
                      </div>
                    )}
                    <div className="lp-stack-content">
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
                    </div>
                  </div>
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
            <LogoMark className="lp-logo-mark" />
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
