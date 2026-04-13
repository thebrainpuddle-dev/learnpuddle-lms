import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '../../test-utils';
import { ChatbotChat } from './ChatbotChat';
import { useChatbotStore } from '../../stores/chatbotStore';
import type { ChatSSEEvent } from '../../types/chatbot';

vi.mock('../../utils/authSession', () => ({
  getAccessToken: () => 'test-jwt-token',
}));

vi.mock('../../config/api', () => ({
  default: {
    defaults: {
      baseURL: 'http://api.test',
    },
  },
}));

function createSseResponse(events: ChatSSEEvent[]): Response {
  const encoder = new TextEncoder();
  const chunks = events.map((event) =>
    encoder.encode(`data: ${JSON.stringify(event)}\n`),
  );
  let index = 0;

  return {
    ok: true,
    status: 200,
    body: {
      getReader: () => ({
        read: vi.fn().mockImplementation(async () => {
          if (index < chunks.length) {
            const value = chunks[index];
            index += 1;
            return { done: false, value };
          }
          return { done: true, value: undefined };
        }),
      }),
    },
  } as unknown as Response;
}

describe('ChatbotChat', () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    useChatbotStore.setState({ isStreaming: false, streamingContent: '' });
    if (!Element.prototype.scrollIntoView) {
      Element.prototype.scrollIntoView = () => {};
    }
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('sends preview mode chat requests to the teacher endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      createSseResponse([
        { type: 'content', content: 'Preview answer' },
        { type: 'done', conversation_id: 'preview-conv-1' },
      ]),
    );
    vi.stubGlobal('fetch', fetchMock);

    render(
      <ChatbotChat
        chatbotId="bot-preview"
        welcomeMessage="Welcome to preview"
        mode="preview"
      />,
    );

    fireEvent.change(screen.getByPlaceholderText(/Ask anything about your course/i), {
      target: { value: '  Explain photosynthesis  ' },
    });
    fireEvent.click(screen.getByLabelText(/Send message/i));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('http://api.test/v1/teacher/chatbots/bot-preview/chat/');
    expect(init.method).toBe('POST');
    expect(init.headers).toEqual(
      expect.objectContaining({
        Authorization: 'Bearer test-jwt-token',
        'Content-Type': 'application/json',
      }),
    );

    const body = JSON.parse(String(init.body));
    expect(body).toMatchObject({
      message: 'Explain photosynthesis',
      conversation_id: null,
      history: [{ role: 'user', content: 'Explain photosynthesis' }],
    });

    await waitFor(() => {
      expect(screen.getByText('Preview answer')).toBeInTheDocument();
    });
  });

  it('sends student mode chat requests to the student endpoint by default', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      createSseResponse([
        { type: 'content', content: 'Student answer' },
        { type: 'done', conversation_id: 'student-conv-1' },
      ]),
    );
    vi.stubGlobal('fetch', fetchMock);

    render(
      <ChatbotChat
        chatbotId="bot-student"
        welcomeMessage="Welcome to student chat"
      />,
    );

    fireEvent.change(screen.getByPlaceholderText(/Ask anything about your course/i), {
      target: { value: 'Summarize chapter 2' },
    });
    fireEvent.click(screen.getByLabelText(/Send message/i));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('http://api.test/v1/student/chatbots/bot-student/chat/');
  });
});
