// src/components/student/StudySummaryPanel.tsx
//
// AI Study Summary panel — streams SSE when generating, displays cached results,
// and provides tabbed navigation for Summary / Flashcards / Key Terms / Quiz Prep / Mind Map.
// Supports both student and teacher modes.

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Sparkles, BookOpen, Layers, List, HelpCircle, Loader2, AlertCircle,
  RefreshCw, X, ChevronRight, GitBranch, Share2, Users,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { studentService } from '../../services/studentService';
import { getAccessToken } from '../../utils/authSession';
import api from '../../config/api';
import { FlashcardReview } from './FlashcardReview';
import { MindMapTab } from './MindMapTab';
import type { StudySummaryData, Flashcard, QuizQuestion } from '../../types/studySummary';

const API_BASE_URL = api.defaults.baseURL ?? '';

type Tab = 'summary' | 'flashcards' | 'key_terms' | 'quiz_prep' | 'mind_map';

const TABS: { key: Tab; label: string; icon: React.ElementType }[] = [
  { key: 'summary', label: 'Summary', icon: BookOpen },
  { key: 'flashcards', label: 'Flashcards', icon: Layers },
  { key: 'key_terms', label: 'Key Terms', icon: List },
  { key: 'quiz_prep', label: 'Quiz Prep', icon: HelpCircle },
  { key: 'mind_map', label: 'Mind Map', icon: GitBranch },
];

interface StudySummaryPanelProps {
  contentId: string;
  contentTitle: string;
  contentType: string;
  onClose?: () => void;
  mode?: 'student' | 'teacher';
}

export function StudySummaryPanel({
  contentId,
  contentTitle,
  contentType,
  onClose,
  mode = 'student',
}: StudySummaryPanelProps) {
  const [activeTab, setActiveTab] = useState<Tab>('summary');
  const [isGenerating, setIsGenerating] = useState(false);
  const [statusMessage, setStatusMessage] = useState('');
  const [summaryData, setSummaryData] = useState<StudySummaryData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [showFlashcardReview, setShowFlashcardReview] = useState(false);
  const [isShared, setIsShared] = useState(false);
  const [summaryId, setSummaryId] = useState<string | null>(null);
  const [isTogglingShare, setIsTogglingShare] = useState(false);
  const [isSharedByTeacher, setIsSharedByTeacher] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const apiPrefix = mode === 'teacher' ? '/v1/teacher' : '/v1/student';

  // Check for cached summary on mount or when contentId changes
  useEffect(() => {
    let cancelled = false;

    async function checkCached() {
      setIsLoading(true);
      setSummaryData(null);
      setError(null);
      setStatusMessage('');
      setActiveTab('summary');
      setSummaryId(null);
      setIsShared(false);
      setIsSharedByTeacher(false);

      try {
        if (mode === 'teacher') {
          // Teacher mode: fetch from teacher endpoint
          const res = await api.get(`${apiPrefix}/study-summaries/`, {
            params: { content_id: contentId },
          });
          const list = res.data as Array<{
            id: string;
            content_id: string;
            status: string;
            is_shared?: boolean;
            summary_data?: StudySummaryData;
          }>;
          const match = list.find(
            (s) => s.content_id === contentId && s.status === 'READY',
          );
          if (match && !cancelled) {
            const detail = await api.get(
              `${apiPrefix}/study-summaries/${match.id}/`,
            );
            setSummaryData(detail.data.summary_data);
            setSummaryId(match.id);
            setIsShared(!!match.is_shared);
          }
        } else {
          // Student mode
          const cached = await studentService.getStudySummaryForContent(contentId);
          if (cancelled) return;
          if (cached?.summary_data) {
            setSummaryData(cached.summary_data);
            setSummaryId(cached.id);
            setIsSharedByTeacher(!!cached.shared_by);
          }
        }
      } catch {
        // No cached summary — that's fine
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    checkCached();
    return () => {
      cancelled = true;
      abortRef.current?.abort();
    };
  }, [contentId, mode, apiPrefix]);

  // SSE streaming generation
  const generateSummary = useCallback(async () => {
    const token = getAccessToken();
    if (!token) {
      setError('Session expired. Please refresh the page.');
      return;
    }

    setIsGenerating(true);
    setError(null);
    setStatusMessage('Starting generation...');
    setSummaryData(null);

    const controller = new AbortController();
    abortRef.current = controller;

    const partial: StudySummaryData = {
      summary: '',
      flashcards: [],
      key_terms: [],
      quiz_prep: [],
      mind_map: { nodes: [], edges: [] },
    };

    try {
      // Build headers for SSE fetch (mirrors ChatbotChat pattern)
      const fetchHeaders: Record<string, string> = {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      };
      const hostname = window.location.hostname;
      if (hostname === 'localhost' || hostname === '127.0.0.1' || hostname.endsWith('.localhost')) {
        const urlSubdomain = hostname.endsWith('.localhost')
          ? hostname.replace('.localhost', '')
          : null;
        const subdomain =
          urlSubdomain ||
          sessionStorage.getItem('tenant_subdomain') ||
          localStorage.getItem('tenant_subdomain');
        if (subdomain) {
          fetchHeaders['X-Tenant-Subdomain'] = subdomain;
        }
      }

      const res = await fetch(`${API_BASE_URL}${apiPrefix}/study-summaries/generate/`, {
        method: 'POST',
        headers: fetchHeaders,
        body: JSON.stringify({ content_id: contentId }),
        signal: controller.signal,
      });

      if (!res.ok) {
        let errMsg = `Request failed (${res.status})`;
        try {
          const body = await res.json();
          if (res.status === 429) {
            // Throttled — show user-friendly message with retry time
            errMsg = body.error || body.detail || 'Too many requests. Please wait before trying again.';
          } else {
            errMsg = body.detail || body.error || errMsg;
          }
        } catch {
          if (res.status === 429) {
            errMsg = 'Too many requests. Please wait a few minutes before trying again.';
          }
        }
        throw new Error(errMsg);
      }

      // Check if response is a cached JSON response (not SSE)
      const contentTypeHeader = res.headers.get('content-type') || '';
      if (contentTypeHeader.includes('application/json')) {
        const json = await res.json();
        if (json.cached && json.summary_data) {
          setSummaryData(json.summary_data);
          if (json.id) setSummaryId(json.id);
          setIsGenerating(false);
          setStatusMessage('');
          return;
        }
      }

      // SSE streaming
      const reader = res.body?.getReader();
      if (!reader) throw new Error('No readable stream');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        const lastNewline = buffer.lastIndexOf('\n');
        if (lastNewline < 0) continue;

        const completePart = buffer.slice(0, lastNewline + 1);
        buffer = buffer.slice(lastNewline + 1);

        for (const line of completePart.split('\n')) {
          const trimmed = line.trim();
          if (!trimmed || !trimmed.startsWith('data: ')) continue;
          const raw = trimmed.slice(6).trim();
          if (!raw || raw === '[DONE]') continue;

          try {
            const evt = JSON.parse(raw);

            switch (evt.type) {
              case 'status':
                setStatusMessage(evt.message || '');
                break;
              case 'summary':
                partial.summary = evt.content || '';
                setSummaryData({ ...partial });
                break;
              case 'flashcards':
                partial.flashcards = evt.cards || [];
                setSummaryData({ ...partial });
                break;
              case 'key_terms':
                partial.key_terms = evt.terms || [];
                setSummaryData({ ...partial });
                break;
              case 'quiz_prep':
                partial.quiz_prep = evt.questions || [];
                setSummaryData({ ...partial });
                break;
              case 'mind_map':
                partial.mind_map = { nodes: evt.nodes || [], edges: evt.edges || [] };
                setSummaryData({ ...partial });
                break;
              case 'done':
                setStatusMessage('');
                if (evt.summary_id) setSummaryId(evt.summary_id);
                break;
              case 'error':
                setError(evt.error || 'Generation failed');
                break;
            }
          } catch {
            // non-JSON line, skip
          }
        }
      }
    } catch (err: unknown) {
      if ((err as Error).name !== 'AbortError') {
        setError((err as Error).message || 'Failed to generate summary');
      }
    } finally {
      setIsGenerating(false);
      abortRef.current = null;
    }
  }, [contentId, apiPrefix]);

  // Toggle share (teacher mode only)
  const toggleShare = useCallback(async () => {
    if (!summaryId || mode !== 'teacher') return;
    setIsTogglingShare(true);
    try {
      await api.patch(`${apiPrefix}/study-summaries/${summaryId}/`, {
        is_shared: !isShared,
      });
      setIsShared((prev) => !prev);
    } catch {
      // silently fail
    } finally {
      setIsTogglingShare(false);
    }
  }, [summaryId, isShared, mode, apiPrefix]);

  // Loading state
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-6 w-6 text-indigo-500 animate-spin" />
      </div>
    );
  }

  const accentColor = mode === 'teacher' ? 'orange' : 'indigo';

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-gray-100">
        <div className="flex items-start justify-between">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-gray-900 truncate">{contentTitle}</h3>
              {mode === 'student' && isSharedByTeacher && (
                <span className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-orange-600 bg-orange-50 px-2 py-0.5 rounded-full flex-shrink-0">
                  <Users className="h-3 w-3" />
                  Shared by teacher
                </span>
              )}
            </div>
            <p className="text-xs text-gray-400 mt-0.5">
              {contentType === 'VIDEO' ? 'Video' : contentType === 'DOCUMENT' ? 'Document' : 'Text'} content
            </p>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              className="p-1.5 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition-colors ml-3"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {/* Generate / Regenerate button when no data or want to refresh */}
      {!summaryData && !isGenerating && (
        <div className="px-5 py-10 text-center">
          <div className={cn(
            'h-12 w-12 rounded-xl flex items-center justify-center mx-auto mb-3',
            accentColor === 'orange' ? 'bg-orange-50' : 'bg-indigo-50',
          )}>
            <Sparkles className={cn(
              'h-6 w-6',
              accentColor === 'orange' ? 'text-orange-500' : 'text-indigo-500',
            )} />
          </div>
          <p className="text-sm font-medium text-gray-700 mb-1">
            Generate AI Study Materials
          </p>
          <p className="text-xs text-gray-400 mb-5">
            Create a summary, flashcards, key terms, quiz prep, and mind map
          </p>
          {error && (
            <div className="mx-auto max-w-sm mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg">
              <div className="flex items-start gap-2">
                <AlertCircle className="h-4 w-4 text-amber-500 flex-shrink-0 mt-0.5" />
                <p className="text-sm text-amber-700">{error}</p>
              </div>
            </div>
          )}
          <button
            onClick={generateSummary}
            className={cn(
              'px-5 py-2.5 rounded-lg text-sm font-medium text-white transition-colors inline-flex items-center gap-2',
              accentColor === 'orange'
                ? 'bg-orange-600 hover:bg-orange-700'
                : 'bg-indigo-600 hover:bg-indigo-700',
            )}
          >
            <Sparkles className="h-4 w-4" />
            Generate Summary
          </button>
        </div>
      )}

      {/* Generating progress */}
      {isGenerating && (
        <div className="px-5 py-6">
          <div className="flex items-center gap-3 mb-4">
            <Loader2 className={cn(
              'h-5 w-5 animate-spin flex-shrink-0',
              accentColor === 'orange' ? 'text-orange-500' : 'text-indigo-500',
            )} />
            <div>
              <p className="text-sm font-medium text-gray-700">Generating study materials...</p>
              {statusMessage && (
                <p className="text-xs text-gray-400 mt-0.5">{statusMessage}</p>
              )}
            </div>
          </div>
          <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div className={cn(
              'h-full rounded-full animate-pulse w-2/3',
              accentColor === 'orange' ? 'bg-orange-500' : 'bg-indigo-500',
            )} />
          </div>
        </div>
      )}

      {/* Tabbed content when data is available */}
      {summaryData && (
        <>
          {/* Tabs */}
          <div className="flex border-b border-gray-100 px-5 overflow-x-auto">
            {TABS.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-2.5 text-xs font-medium border-b-2 transition-colors -mb-px whitespace-nowrap',
                  activeTab === tab.key
                    ? accentColor === 'orange'
                      ? 'border-orange-600 text-orange-600'
                      : 'border-indigo-600 text-indigo-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700',
                )}
              >
                <tab.icon className="h-3.5 w-3.5" />
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className={cn(
            'px-5 py-4 overflow-y-auto',
            activeTab === 'mind_map' ? 'max-h-[70vh]' : 'max-h-[60vh]',
          )}>
            {activeTab === 'summary' && (
              <SummaryTab summary={summaryData.summary} />
            )}
            {activeTab === 'flashcards' && (
              <FlashcardsTab
                cards={summaryData.flashcards}
                onStartReview={() => setShowFlashcardReview(true)}
                accentColor={accentColor}
              />
            )}
            {activeTab === 'key_terms' && (
              <KeyTermsTab terms={summaryData.key_terms} />
            )}
            {activeTab === 'quiz_prep' && (
              <QuizPrepTab questions={summaryData.quiz_prep} accentColor={accentColor} />
            )}
            {activeTab === 'mind_map' && summaryData.mind_map && (
              <MindMapTab data={summaryData.mind_map} />
            )}
            {activeTab === 'mind_map' && !summaryData.mind_map && (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <GitBranch className="h-6 w-6 text-gray-400 mb-2" />
                <p className="text-sm text-gray-400 italic">No mind map data available.</p>
              </div>
            )}
          </div>

          {/* Footer with Regenerate + Share */}
          <div className="px-5 py-3 border-t border-gray-100 flex items-center justify-between">
            {mode === 'teacher' && summaryId && (
              <button
                onClick={toggleShare}
                disabled={isTogglingShare}
                className={cn(
                  'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors inline-flex items-center gap-1.5 disabled:opacity-50',
                  isShared
                    ? 'bg-green-50 text-green-700 hover:bg-green-100'
                    : 'bg-gray-50 text-gray-500 hover:bg-gray-100',
                )}
              >
                <Share2 className="h-3.5 w-3.5" />
                {isShared ? 'Shared with Students' : 'Share with Students'}
              </button>
            )}
            {mode !== 'teacher' && <div />}
            <button
              onClick={generateSummary}
              disabled={isGenerating}
              className={cn(
                'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors inline-flex items-center gap-1.5 disabled:opacity-50',
                accentColor === 'orange'
                  ? 'text-gray-500 hover:text-orange-600 hover:bg-orange-50'
                  : 'text-gray-500 hover:text-indigo-600 hover:bg-indigo-50',
              )}
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Regenerate
            </button>
          </div>
        </>
      )}

      {/* Flashcard review overlay */}
      {showFlashcardReview && summaryData?.flashcards && (
        <FlashcardReview
          cards={summaryData.flashcards}
          onClose={() => setShowFlashcardReview(false)}
        />
      )}
    </div>
  );
}

// ─── Summary Tab ─────────────────────────────────────────────────────────────

function SummaryTab({ summary }: { summary: string }) {
  if (!summary) {
    return <p className="text-sm text-gray-400 italic">No summary available.</p>;
  }

  // Split into paragraphs and render with basic bold support
  const paragraphs = summary.split('\n\n').filter(Boolean);

  return (
    <div className="space-y-3">
      {paragraphs.map((para, i) => (
        <p key={i} className="text-sm text-gray-700 leading-relaxed">
          {renderBoldText(para)}
        </p>
      ))}
    </div>
  );
}

function renderBoldText(text: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return (
        <strong key={i} className="font-semibold text-gray-900">
          {part.slice(2, -2)}
        </strong>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

// ─── Flashcards Tab ──────────────────────────────────────────────────────────

function FlashcardsTab({
  cards,
  onStartReview,
  accentColor = 'indigo',
}: {
  cards: Flashcard[];
  onStartReview: () => void;
  accentColor?: string;
}) {
  const [flippedCards, setFlippedCards] = useState<Set<number>>(new Set());

  if (cards.length === 0) {
    return <p className="text-sm text-gray-400 italic">No flashcards generated.</p>;
  }

  const toggleCard = (index: number) => {
    setFlippedCards((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-xs text-gray-500">{cards.length} card{cards.length !== 1 ? 's' : ''}</p>
        <button
          onClick={onStartReview}
          className={cn(
            'px-3 py-1.5 rounded-lg text-xs font-medium text-white transition-colors inline-flex items-center gap-1.5',
            accentColor === 'orange'
              ? 'bg-orange-600 hover:bg-orange-700'
              : 'bg-indigo-600 hover:bg-indigo-700',
          )}
        >
          <Layers className="h-3.5 w-3.5" />
          Study Mode
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {cards.map((card, i) => {
          const isFlipped = flippedCards.has(i);
          return (
            <button
              key={i}
              type="button"
              onClick={() => toggleCard(i)}
              className={cn(
                'text-left rounded-lg border p-4 transition-all duration-200 hover:shadow-sm',
                isFlipped
                  ? accentColor === 'orange'
                    ? 'bg-orange-50 border-orange-200'
                    : 'bg-indigo-50 border-indigo-200'
                  : 'bg-gray-50 border-gray-200 hover:border-gray-300',
              )}
            >
              <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400 mb-1.5">
                {isFlipped ? 'Answer' : 'Question'}
              </p>
              <p className="text-sm text-gray-700 leading-relaxed">
                {isFlipped ? card.back : card.front}
              </p>
              <p className="text-[10px] text-gray-400 mt-2">Click to flip</p>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ─── Key Terms Tab ───────────────────────────────────────────────────────────

function KeyTermsTab({ terms }: { terms: { term: string; definition: string }[] }) {
  const [search, setSearch] = useState('');
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);

  if (terms.length === 0) {
    return <p className="text-sm text-gray-400 italic">No key terms generated.</p>;
  }

  const filtered = search.trim()
    ? terms.filter(
        (t) =>
          t.term.toLowerCase().includes(search.toLowerCase()) ||
          t.definition.toLowerCase().includes(search.toLowerCase()),
      )
    : terms;

  return (
    <div>
      {/* Search */}
      {terms.length > 4 && (
        <div className="relative mb-4">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={`Search ${terms.length} terms...`}
            className="w-full pl-8 pr-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-indigo-500 focus:border-indigo-500"
          />
          <List className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-400" />
        </div>
      )}

      {/* Terms grid */}
      <div className="space-y-2">
        {filtered.map((item, i) => {
          const isExpanded = expandedIndex === i;
          return (
            <button
              key={i}
              type="button"
              onClick={() => setExpandedIndex(isExpanded ? null : i)}
              className={cn(
                'w-full text-left rounded-lg border p-3 transition-all duration-200',
                isExpanded
                  ? 'bg-indigo-50 border-indigo-200 shadow-sm'
                  : 'bg-white border-gray-200 hover:border-gray-300 hover:shadow-sm',
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className={cn(
                    'flex-shrink-0 w-6 h-6 rounded-md flex items-center justify-center text-[10px] font-bold',
                    isExpanded
                      ? 'bg-indigo-200 text-indigo-700'
                      : 'bg-gray-100 text-gray-500',
                  )}>
                    {item.term.charAt(0).toUpperCase()}
                  </span>
                  <span className="text-sm font-semibold text-gray-900">{item.term}</span>
                </div>
                <ChevronRight className={cn(
                  'h-3.5 w-3.5 text-gray-400 transition-transform flex-shrink-0 mt-0.5',
                  isExpanded && 'rotate-90',
                )} />
              </div>
              {isExpanded && (
                <p className="text-sm text-gray-600 mt-2 ml-8 leading-relaxed">
                  {item.definition}
                </p>
              )}
              {!isExpanded && (
                <p className="text-xs text-gray-400 mt-1 ml-8 line-clamp-1">
                  {item.definition}
                </p>
              )}
            </button>
          );
        })}
      </div>

      {search && filtered.length === 0 && (
        <p className="text-sm text-gray-400 text-center py-4">
          No terms match &ldquo;{search}&rdquo;
        </p>
      )}
    </div>
  );
}

// ─── Quiz Prep Tab ───────────────────────────────────────────────────────────

function QuizPrepTab({
  questions,
  accentColor = 'indigo',
}: {
  questions: QuizQuestion[];
  accentColor?: string;
}) {
  const [currentQuestion, setCurrentQuestion] = useState(0);
  const [selectedAnswer, setSelectedAnswer] = useState<string | null>(null);
  const [showResult, setShowResult] = useState(false);
  const [score, setScore] = useState({ correct: 0, total: 0 });

  if (questions.length === 0) {
    return <p className="text-sm text-gray-400 italic">No quiz questions generated.</p>;
  }

  const question = questions[currentQuestion];
  const isLastQuestion = currentQuestion === questions.length - 1;

  const checkAnswer = () => {
    if (!selectedAnswer) return;
    setShowResult(true);
    const isCorrect = selectedAnswer.toLowerCase() === question.answer.toLowerCase();
    setScore((prev) => ({
      correct: prev.correct + (isCorrect ? 1 : 0),
      total: prev.total + 1,
    }));
  };

  const nextQuestion = () => {
    if (isLastQuestion) {
      // Reset quiz
      setCurrentQuestion(0);
      setSelectedAnswer(null);
      setShowResult(false);
      setScore({ correct: 0, total: 0 });
      return;
    }
    setCurrentQuestion((prev) => prev + 1);
    setSelectedAnswer(null);
    setShowResult(false);
  };

  const typeLabel =
    question.type === 'mcq' ? 'Multiple Choice' :
    question.type === 'true_false' ? 'True / False' :
    question.type === 'fill_blank' ? 'Fill in the Blank' : 'Short Answer';

  const btnClass = accentColor === 'orange'
    ? 'bg-orange-600 text-white hover:bg-orange-700'
    : 'bg-indigo-600 text-white hover:bg-indigo-700';

  return (
    <div>
      {/* Progress bar + counter */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs text-gray-500">
            Question {currentQuestion + 1} of {questions.length}
          </p>
          {score.total > 0 && (
            <p className={cn(
              'text-xs font-medium',
              accentColor === 'orange' ? 'text-orange-600' : 'text-indigo-600',
            )}>
              {score.correct}/{score.total} correct
            </p>
          )}
        </div>
        <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
          <div
            className={cn(
              'h-full rounded-full transition-all duration-300',
              accentColor === 'orange' ? 'bg-orange-500' : 'bg-indigo-500',
            )}
            style={{ width: `${((currentQuestion + 1) / questions.length) * 100}%` }}
          />
        </div>
      </div>

      {/* Question */}
      <div className="mb-4">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">
          {typeLabel}
        </span>
        <p className="text-sm font-medium text-gray-900 mt-1">{question.question}</p>
      </div>

      {/* Options for MCQ / True-False */}
      {(question.type === 'mcq' || question.type === 'true_false') && question.options && (
        <div className="space-y-2 mb-4">
          {question.options.map((option, i) => {
            const isSelected = selectedAnswer === option;
            const isCorrectOption = showResult && option.toLowerCase() === question.answer.toLowerCase();
            const isWrongSelection = showResult && isSelected && !isCorrectOption;

            return (
              <button
                key={i}
                type="button"
                onClick={() => !showResult && setSelectedAnswer(option)}
                disabled={showResult}
                className={cn(
                  'w-full text-left px-4 py-2.5 rounded-lg border text-sm transition-all',
                  isCorrectOption && showResult
                    ? 'border-emerald-300 bg-emerald-50 text-emerald-700'
                    : isWrongSelection
                      ? 'border-red-300 bg-red-50 text-red-700'
                      : isSelected
                        ? accentColor === 'orange'
                          ? 'border-orange-300 bg-orange-50 text-orange-700'
                          : 'border-indigo-300 bg-indigo-50 text-indigo-700'
                        : 'border-gray-200 hover:border-gray-300 text-gray-700',
                  showResult && 'cursor-default',
                )}
              >
                {option}
              </button>
            );
          })}
        </div>
      )}

      {/* Text input for fill_blank / short_answer */}
      {(question.type === 'fill_blank' || question.type === 'short_answer') && (
        <div className="mb-4">
          <input
            type="text"
            value={selectedAnswer || ''}
            onChange={(e) => !showResult && setSelectedAnswer(e.target.value)}
            disabled={showResult}
            placeholder="Type your answer..."
            className={cn(
              'w-full px-4 py-2.5 border border-gray-200 rounded-lg text-sm disabled:bg-gray-50',
              accentColor === 'orange'
                ? 'focus:ring-orange-500 focus:border-orange-500'
                : 'focus:ring-indigo-500 focus:border-indigo-500',
            )}
          />
          {showResult && (
            <p className="text-xs text-gray-500 mt-2">
              Correct answer: <span className="font-medium text-emerald-600">{question.answer}</span>
            </p>
          )}
        </div>
      )}

      {/* Explanation after answering (MCQ / True-False) */}
      {showResult && (question.type === 'mcq' || question.type === 'true_false') && (
        <div className={cn(
          'mb-4 p-3 rounded-lg text-sm',
          selectedAnswer?.toLowerCase() === question.answer.toLowerCase()
            ? 'bg-emerald-50 border border-emerald-200 text-emerald-700'
            : 'bg-red-50 border border-red-200 text-red-700',
        )}>
          {selectedAnswer?.toLowerCase() === question.answer.toLowerCase()
            ? 'Correct!'
            : `Incorrect. The correct answer is: ${question.answer}`}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-2">
        {!showResult ? (
          <button
            onClick={checkAnswer}
            disabled={!selectedAnswer}
            className={cn(
              'px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed',
              btnClass,
            )}
          >
            Check Answer
          </button>
        ) : (
          <button
            onClick={nextQuestion}
            className={cn(
              'px-4 py-2 rounded-lg text-sm font-medium transition-colors inline-flex items-center gap-1.5',
              btnClass,
            )}
          >
            {isLastQuestion && score.total === questions.length - 1
              ? 'See Results'
              : isLastQuestion
                ? 'Restart Quiz'
                : 'Next Question'}
            <ChevronRight className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Final score summary when all questions answered and quiz resets */}
      {score.total > 0 && score.total === questions.length && !showResult && (
        <div className={cn(
          'mt-4 p-4 rounded-lg border text-center',
          score.correct >= questions.length * 0.7
            ? 'bg-emerald-50 border-emerald-200'
            : score.correct >= questions.length * 0.4
              ? 'bg-amber-50 border-amber-200'
              : 'bg-red-50 border-red-200',
        )}>
          <p className="text-lg font-bold text-gray-900">
            {score.correct}/{questions.length}
          </p>
          <p className="text-xs text-gray-500 mt-1">
            {score.correct >= questions.length * 0.7
              ? 'Great job! You know this material well.'
              : score.correct >= questions.length * 0.4
                ? 'Good effort! Review the tricky areas.'
                : 'Keep studying — you\'ll get there!'}
          </p>
        </div>
      )}
    </div>
  );
}
