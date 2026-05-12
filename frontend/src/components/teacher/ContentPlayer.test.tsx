import { render, screen } from '@testing-library/react';
import { ContentPlayer } from './ContentPlayer';

describe('ContentPlayer AI Classroom launch', () => {
  it('uses the linked classroom id instead of the course content id', () => {
    window.history.pushState({}, '', '/teacher/courses/course-1');

    render(
      <ContentPlayer
        content={{
          id: 'content-1',
          maic_classroom_id: 'classroom-1',
          title: 'Fractions Lab',
          content_type: 'AI_CLASSROOM',
        }}
      />,
    );

    expect(screen.getByRole('link', { name: /launch ai classroom/i }))
      .toHaveAttribute('href', '/teacher/ai-classroom/classroom-1');
  });

  it('keeps the student route prefix when launched inside the student portal', () => {
    window.history.pushState({}, '', '/student/courses/course-1');

    render(
      <ContentPlayer
        content={{
          id: 'content-2',
          maic_classroom_id: 'classroom-2',
          title: 'Ratios Lab',
          content_type: 'AI_CLASSROOM',
        }}
      />,
    );

    expect(screen.getByRole('link', { name: /launch ai classroom/i }))
      .toHaveAttribute('href', '/student/ai-classroom/classroom-2');
  });
});
