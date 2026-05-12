// PBLRenderer.test.tsx — verifies the renderer reads upstream's
// PBLProjectConfig shape (MAIC-705 reconciliation).

import { describe, expect, test, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PBLRenderer } from '../PBLRenderer';
import type { MAICPBLContent } from '../../../types/maic-scenes';
import type { PBLProjectConfig } from '../../../types/pbl';
import { useAuthStore } from '../../../stores/authStore';

// streamMAIC is the legacy SSE chat path; MAIC-706 swaps it for WS.
// We don't exercise it here — the WS hook gets its own test.
vi.mock('../../../lib/maicSSE', () => ({
  streamMAIC: vi.fn().mockResolvedValue(undefined),
}));

function _config(): PBLProjectConfig {
  return {
    projectInfo: {
      title: 'Build a Math Tutor',
      description: 'A student-facing PBL on fractions.',
    },
    agents: [
      {
        name: 'Designer',
        actor_role: 'Lead Designer',
        role_division: 'management',
        system_prompt: 'You design.',
        default_mode: 'chat',
        delay_time: 0,
        env: {},
        is_user_role: true,
        is_active: true,
        is_system_agent: false,
      },
      {
        name: 'Helper',
        actor_role: 'Question Agent',
        role_division: 'development',
        system_prompt: 'You ask.',
        default_mode: 'chat',
        delay_time: 0,
        env: {},
        is_user_role: false,
        is_active: true,
        is_system_agent: true,
      },
    ],
    issueboard: {
      agent_ids: ['Designer'],
      issues: [
        {
          id: 'i-1',
          title: 'Wireframe the home screen',
          description: 'Sketch and review.',
          person_in_charge: 'Designer',
          participants: [],
          notes: '',
          parent_issue: null,
          index: 0,
          is_done: true,
          is_active: false,
          generated_questions: '',
          question_agent_name: 'Helper',
          judge_agent_name: 'Judge',
        },
        {
          id: 'i-2',
          title: 'Build interactive prototype',
          description: 'Make it click.',
          person_in_charge: 'Designer',
          participants: [],
          notes: '',
          parent_issue: null,
          index: 1,
          is_done: false,
          is_active: true,
          generated_questions: '',
          question_agent_name: 'Helper',
          judge_agent_name: 'Judge',
        },
        {
          id: 'i-3',
          title: 'Ship to staging',
          description: 'Final QA.',
          person_in_charge: 'Designer',
          participants: [],
          notes: '',
          parent_issue: null,
          index: 2,
          is_done: false,
          is_active: false,
          generated_questions: '',
          question_agent_name: 'Helper',
          judge_agent_name: 'Judge',
        },
      ],
      current_issue_id: 'i-2',
    },
    chat: { messages: [] },
    selectedRole: null,
  };
}

function _content(overrides: Partial<PBLProjectConfig> = {}): MAICPBLContent {
  return {
    type: 'pbl',
    projectConfig: { ..._config(), ...overrides },
  };
}

describe('PBLRenderer (MAIC-705)', () => {
  beforeEach(() => {
    useAuthStore.setState({ accessToken: 'test-token' });
  });

  test('renders projectInfo.title and description from projectConfig', () => {
    render(<PBLRenderer content={_content()} sceneId="scene-1" />);
    expect(screen.getByText('Build a Math Tutor')).toBeInTheDocument();
    expect(
      screen.getByText('A student-facing PBL on fractions.'),
    ).toBeInTheDocument();
  });

  test('falls back to legacy is_user_role agents when no development roles exist', () => {
    render(<PBLRenderer content={_content()} sceneId="scene-1" />);
    // Designer is_user_role:true -> present (actor_role label)
    expect(screen.getByText('Lead Designer')).toBeInTheDocument();
    // Helper is system-owned -> NOT present
    expect(screen.queryByText('Question Agent')).not.toBeInTheDocument();
  });

  test('prefers non-system development agents over legacy is_user_role roles', () => {
    const cfg = _config();
    cfg.agents.push({
      name: 'Developer',
      actor_role: 'Software Engineer',
      role_division: 'development',
      system_prompt: 'You build.',
      default_mode: 'chat',
      delay_time: 0,
      env: {},
      is_user_role: false,
      is_active: true,
      is_system_agent: false,
    });

    render(
      <PBLRenderer
        content={{ type: 'pbl', projectConfig: cfg }}
        sceneId="scene-1"
      />,
    );

    expect(screen.getByText('Software Engineer')).toBeInTheDocument();
    expect(screen.queryByText('Lead Designer')).not.toBeInTheDocument();
    expect(screen.queryByText('Question Agent')).not.toBeInTheDocument();
  });

  test('selecting a role highlights the button', () => {
    render(<PBLRenderer content={_content()} sceneId="scene-1" />);
    const btn = screen.getByText('Lead Designer').closest('button')!;
    expect(btn.className).not.toContain('ring-indigo-500');
    fireEvent.click(btn);
    expect(btn.className).toContain('ring-indigo-500');
  });

  test('issue board: 1 done + 1 active + 1 pending across 3 columns', () => {
    render(<PBLRenderer content={_content()} sceneId="scene-1" />);

    // Each title shows once
    expect(screen.getByText('Wireframe the home screen')).toBeInTheDocument();
    expect(screen.getByText('Build interactive prototype')).toBeInTheDocument();
    expect(screen.getByText('Ship to staging')).toBeInTheDocument();

    // Status badges (pending/active/done labels appear inline + as column headers)
    expect(screen.getAllByText('Pending').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('Active').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('Done').length).toBeGreaterThanOrEqual(2);
  });

  test('progress bar reflects done/total ratio', () => {
    render(<PBLRenderer content={_content()} sceneId="scene-1" />);
    expect(screen.getByText('1 of 3 tasks done')).toBeInTheDocument();
  });

  test('issues within a column are sorted by index ascending', () => {
    // Three pending issues with reversed array order — within the
    // pending column, index-2 must come AFTER index-0.
    const cfg = _config();
    cfg.issueboard.issues = [
      { ...cfg.issueboard.issues[0], id: 'p3', title: 'P3', index: 2, is_done: false, is_active: false },
      { ...cfg.issueboard.issues[0], id: 'p1', title: 'P1', index: 0, is_done: false, is_active: false },
      { ...cfg.issueboard.issues[0], id: 'p2', title: 'P2', index: 1, is_done: false, is_active: false },
    ];
    render(
      <PBLRenderer
        content={{ type: 'pbl', projectConfig: cfg }}
        sceneId="scene-1"
      />,
    );
    const titles = screen
      .getAllByText(/^P[123]$/)
      .map((el) => el.textContent);
    expect(titles).toEqual(['P1', 'P2', 'P3']);
  });

  test('done issue title is line-through styled', () => {
    render(<PBLRenderer content={_content()} sceneId="scene-1" />);
    const title = screen.getByText('Wireframe the home screen');
    expect(title.className).toContain('line-through');
  });

  test('renders chat panel with empty-state hint', () => {
    render(<PBLRenderer content={_content()} sceneId="scene-1" />);
    expect(
      screen.getByText('Ask a question to get guidance on your project.'),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText('PBL chat input'),
    ).toBeInTheDocument();
  });

  test('renders existing project chat history before the empty-state hint', () => {
    const cfg = _config();
    cfg.chat.messages = [
      {
        id: 'welcome-1',
        agent_name: 'Question Agent - i-2',
        message: 'What should the first prototype prove?',
        timestamp: 1,
        read_by: [],
      },
    ];

    render(
      <PBLRenderer
        content={{ type: 'pbl', projectConfig: cfg }}
        sceneId="scene-1"
      />,
    );

    expect(screen.getByText('What should the first prototype prove?')).toBeInTheDocument();
    expect(
      screen.queryByText('Ask a question to get guidance on your project.'),
    ).not.toBeInTheDocument();
  });

  test('uses active issue generated_questions as the initial mentor message', () => {
    const cfg = _config();
    cfg.issueboard.issues[1].generated_questions = 'Start by naming the key interaction.';

    render(
      <PBLRenderer
        content={{ type: 'pbl', projectConfig: cfg }}
        sceneId="scene-1"
      />,
    );

    expect(screen.getByText('Start by naming the key interaction.')).toBeInTheDocument();
  });

  test('honors initial selectedRole from projectConfig', () => {
    const cfg = _config();
    cfg.selectedRole = 'Designer';
    render(
      <PBLRenderer
        content={{ type: 'pbl', projectConfig: cfg }}
        sceneId="scene-1"
      />,
    );
    const btn = screen.getByText('Lead Designer').closest('button')!;
    expect(btn.className).toContain('ring-indigo-500');
  });

  test('hides role selector when no selectable agents exist', () => {
    const cfg = _config();
    cfg.agents = cfg.agents.map((a) => ({ ...a, is_user_role: false }));
    render(
      <PBLRenderer
        content={{ type: 'pbl', projectConfig: cfg }}
        sceneId="scene-1"
      />,
    );
    expect(screen.queryByText('Select Your Role')).not.toBeInTheDocument();
  });

  test('person_in_charge appears as badge on issue card', () => {
    render(<PBLRenderer content={_content()} sceneId="scene-1" />);
    // 3 issues all assigned to 'Designer' → at least 1 badge text match
    const badges = screen.getAllByText('Designer');
    expect(badges.length).toBeGreaterThanOrEqual(1);
  });

  test('zero issues → empty board still renders without error', () => {
    const cfg = _config();
    cfg.issueboard.issues = [];
    cfg.issueboard.current_issue_id = null;
    render(
      <PBLRenderer
        content={{ type: 'pbl', projectConfig: cfg }}
        sceneId="scene-1"
      />,
    );
    expect(screen.getByText('0 of 0 tasks done')).toBeInTheDocument();
    // 3 "No items" placeholders, one per column
    expect(screen.getAllByText('No items').length).toBe(3);
  });
});
