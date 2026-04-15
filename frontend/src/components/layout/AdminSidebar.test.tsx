import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { AdminSidebar } from './AdminSidebar';
import { useAuthStore } from '../../stores/authStore';
import { useTenantStore } from '../../stores/tenantStore';
import { useGuidedTour } from '../tour';

vi.mock('../../stores/authStore');
vi.mock('../../stores/tenantStore');
vi.mock('../tour');

const mockedUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;
const mockedUseTenantStore = useTenantStore as unknown as ReturnType<typeof vi.fn>;
const mockedUseGuidedTour = useGuidedTour as unknown as ReturnType<typeof vi.fn>;

describe('AdminSidebar mobile drawer', () => {
  beforeEach(() => {
    mockedUseAuthStore.mockReturnValue({
      user: {
        id: 'user-1',
        email: 'admin@test.com',
        first_name: 'Admin',
        last_name: 'User',
        role: 'SCHOOL_ADMIN',
        is_active: true,
      },
      accessToken: 'token',
      refreshToken: 'refresh-token',
      isAuthenticated: true,
      isLoading: false,
      setAuth: vi.fn(),
      clearAuth: vi.fn(),
      setUser: vi.fn(),
      setLoading: vi.fn(),
      initializeFromStorage: vi.fn(),
    });

    mockedUseTenantStore.mockReturnValue({
      theme: {
        name: 'Test School',
        subdomain: 'test',
        logo: '',
        primaryColor: '#1F4788',
        secondaryColor: '#2E5C8A',
        fontFamily: 'Inter',
        tenantFound: true,
      },
      plan: 'FREE',
      features: {
        video_upload: false,
        auto_quiz: false,
        transcripts: false,
        reminders: true,
        custom_branding: false,
        reports_export: false,
        groups: true,
        certificates: false,
        teacher_authoring: false,
      },
      limits: null,
      usage: null,
      setTheme: vi.fn(),
      setConfig: vi.fn(),
      hasFeature: () => true,
    });

    mockedUseGuidedTour.mockReturnValue({
      startTour: vi.fn(),
      isActive: false,
    });
  });

  it('closes the drawer when a nav item is clicked', () => {
    const onClose = vi.fn();

    render(
      <MemoryRouter initialEntries={['/admin/dashboard']}>
        <AdminSidebar open onClose={onClose} />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByText('Courses'));
    expect(onClose).toHaveBeenCalled();
  });
});
