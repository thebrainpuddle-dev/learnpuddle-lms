/**
 * Tests for VideoPlayer (Phase 9, MAIC-916).
 *
 * Discipline: real React, real DOM (vitest happy-dom). No mocks needed
 * — the <video> element is a pure browser primitive.
 */
import { describe, test, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { VideoPlayer } from '../VideoPlayer';

describe('VideoPlayer', () => {
  test('renders <video> with the provided src for real URLs', () => {
    const { container } = render(
      <VideoPlayer src="https://storage.example/v-1.mp4" alt="demo" />,
    );
    const video = container.querySelector('video');
    expect(video).not.toBeNull();
    expect(video?.getAttribute('src')).toBe('https://storage.example/v-1.mp4');
    // aria-label flows through from alt
    expect(video?.getAttribute('aria-label')).toBe('demo');
  });

  test('renders skeleton when src is empty', () => {
    render(<VideoPlayer src="" alt="pending" />);
    expect(screen.getByTestId('video-skeleton')).toBeInTheDocument();
    expect(screen.getByText('Video generating…')).toBeInTheDocument();
  });

  test('renders skeleton when src is a gen_vid_ placeholder', () => {
    render(<VideoPlayer src="gen_vid_xyz" alt="pending" />);
    expect(screen.getByTestId('video-skeleton')).toBeInTheDocument();
  });

  test('renders error state when underlying <video> emits error event', () => {
    const { container } = render(
      <VideoPlayer src="https://broken.example/x.mp4" alt="broken" />,
    );
    const video = container.querySelector('video');
    expect(video).not.toBeNull();
    fireEvent.error(video!);
    expect(screen.getByText('Video unavailable')).toBeInTheDocument();
  });

  test('controls=true by default', () => {
    const { container } = render(
      <VideoPlayer src="https://storage.example/v.mp4" />,
    );
    expect(container.querySelector('video')?.hasAttribute('controls')).toBe(true);
  });

  test('controls=false renders bare video', () => {
    const { container } = render(
      <VideoPlayer src="https://storage.example/v.mp4" controls={false} />,
    );
    expect(container.querySelector('video')?.hasAttribute('controls')).toBe(false);
  });

  test('autoPlay forces muted=true (browser autoplay policy)', () => {
    const { container } = render(
      <VideoPlayer
        src="https://storage.example/v.mp4"
        autoPlay={true}
        muted={false}
      />,
    );
    const video = container.querySelector('video');
    // Browser blocks autoPlay+unmuted; we force-mute to keep it playing
    expect((video as HTMLVideoElement).muted).toBe(true);
  });

  test('autoPlay=false respects caller-supplied muted=false', () => {
    const { container } = render(
      <VideoPlayer
        src="https://storage.example/v.mp4"
        autoPlay={false}
        muted={false}
      />,
    );
    expect((container.querySelector('video') as HTMLVideoElement).muted).toBe(false);
  });

  test('onError callback fires with the failing URL in the message', () => {
    let captured: Error | null = null;
    const { container } = render(
      <VideoPlayer
        src="https://broken.example/x.mp4"
        onError={(e) => { captured = e; }}
      />,
    );
    fireEvent.error(container.querySelector('video')!);
    expect(captured).not.toBeNull();
    expect((captured as unknown as Error).message).toContain('https://broken.example/x.mp4');
  });

  test('skeleton honors custom skeletonTestId', () => {
    render(<VideoPlayer src="" skeletonTestId="my-custom-skeleton" />);
    expect(screen.getByTestId('my-custom-skeleton')).toBeInTheDocument();
  });

  test('skeleton uses aria-label from alt for accessibility', () => {
    render(<VideoPlayer src="" alt="Lesson video 1" />);
    expect(screen.getByLabelText('Lesson video 1')).toBeInTheDocument();
  });
});
