import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { CourseViewPage } from './CourseViewPage';
import { teacherService } from '../../services/teacherService';
import { useTenantStore } from '../../stores/tenantStore';

jest.mock('../../stores/tenantStore');
jest.mock('../../services/teacherService', () => ({
  teacherService: {
    getCourse: jest.fn(),
    updateContent: jest.fn(),
    completeContent: jest.fn(),
    getVideoTranscript: jest.fn(),
  },
}));

const mockedUseTenantStore = useTenantStore as unknown as jest.Mock;
const mockedTeacherService = teacherService as jest.Mocked<typeof teacherService>;

const courseResponse = {
  id: 'course-1',
  title: 'Classroom Mastery',
  description: 'Description',
  thumbnail_url: '',
  estimated_hours: 4,
  deadline: null,
  progress: {
    percentage: 25,
    completed_content_count: 1,
    total_content_count: 4,
  },
  modules: [
    {
      id: 'module-1',
      title: 'Module 1',
      description: '<p>Module one</p>',
      order: 1,
      is_active: true,
      completed_content_count: 1,
      total_content_count: 2,
      completion_percentage: 50,
      is_completed: false,
      is_locked: false,
      lock_reason: '',
      contents: [
        {
          id: 'content-1',
          title: 'Lesson 1',
          content_type: 'TEXT',
          order: 1,
          file_url: '',
          hls_url: '',
          thumbnail_url: '',
          text_content: '<p>Hello</p>',
          duration: null,
          status: 'IN_PROGRESS',
          progress_percentage: 30,
          video_progress_seconds: 0,
          is_completed: false,
          is_locked: false,
          lock_reason: '',
        },
      ],
    },
    {
      id: 'module-2',
      title: 'Module 2',
      description: '<p>Module two</p>',
      order: 2,
      is_active: true,
      completed_content_count: 0,
      total_content_count: 1,
      completion_percentage: 0,
      is_completed: false,
      is_locked: true,
      lock_reason: 'Finish the previous module to unlock this one.',
      contents: [
        {
          id: 'content-2',
          title: 'Lesson 2',
          content_type: 'TEXT',
          order: 1,
          file_url: '',
          hls_url: '',
          thumbnail_url: '',
          text_content: '<p>Locked content</p>',
          duration: null,
          status: 'NOT_STARTED',
          progress_percentage: 0,
          video_progress_seconds: 0,
          is_completed: false,
          is_locked: true,
          lock_reason: 'Finish the previous module to unlock this one.',
        },
      ],
    },
  ],
};

describe('CourseViewPage locking behavior', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockedUseTenantStore.mockReturnValue({
      hasFeature: jest.fn(() => true),
    });
    mockedTeacherService.getCourse.mockResolvedValue(courseResponse as any);
    mockedTeacherService.updateContent.mockResolvedValue({} as any);
    mockedTeacherService.completeContent.mockResolvedValue({} as any);
    mockedTeacherService.getVideoTranscript.mockResolvedValue({
      full_text: '',
      segments: [],
    } as any);
  });

  const renderPage = () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });

    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/teacher/courses/course-1']}>
          <Routes>
            <Route path="/teacher/courses/:courseId" element={<CourseViewPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
  };

  it('renders locked modules and disables locked lesson buttons', async () => {
    renderPage();

    expect(await screen.findByText('Classroom Mastery')).toBeInTheDocument();
    expect(screen.getByText('Finish the previous module to unlock this one.')).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole('button', {
        name: /module 2/i,
      }),
    );

    const lockedLessonText = await screen.findByText('Lesson 2');
    const lockedLesson = lockedLessonText.closest('button');
    expect(lockedLesson).not.toBeNull();
    expect(lockedLesson as HTMLButtonElement).toBeDisabled();
  });

  it('submits completion for unlocked text lesson', async () => {
    renderPage();

    expect(await screen.findByText('Classroom Mastery')).toBeInTheDocument();
    const completeButton = await screen.findByRole('button', { name: /mark as complete/i });
    await userEvent.click(completeButton);

    await waitFor(() => {
      expect(mockedTeacherService.completeContent).toHaveBeenCalledWith('content-1');
    });
  });
});
