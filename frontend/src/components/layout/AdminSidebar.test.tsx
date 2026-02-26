import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AdminSidebar } from './AdminSidebar';
import { useAuthStore } from '../../stores/authStore';
import { useTenantStore } from '../../stores/tenantStore';
import { useGuidedTour } from '../tour';

jest.mock('../../stores/authStore');
jest.mock('../../stores/tenantStore');
jest.mock('../tour');

const mockedUseAuthStore = useAuthStore as jest.MockedFunction<typeof useAuthStore>;
const mockedUseTenantStore = useTenantStore as jest.MockedFunction<typeof useTenantStore>;
const mockedUseGuidedTour = useGuidedTour as jest.MockedFunction<typeof useGuidedTour>;

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
      setAuth: jest.fn(),
      clearAuth: jest.fn(),
      setUser: jest.fn(),
      setLoading: jest.fn(),
      initializeFromStorage: jest.fn(),
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
      setTheme: jest.fn(),
      setConfig: jest.fn(),
      hasFeature: () => true,
    });

    mockedUseGuidedTour.mockReturnValue({
      startTour: jest.fn(),
      isActive: false,
    });
  });

  it('closes the drawer when a nav item is clicked', () => {
    const onClose = jest.fn();

    render(
      <MemoryRouter initialEntries={['/admin/dashboard']}>
        <AdminSidebar open onClose={onClose} />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByText('Courses'));
    expect(onClose).toHaveBeenCalled();
  });
});
