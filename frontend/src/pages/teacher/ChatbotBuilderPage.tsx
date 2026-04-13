// src/pages/teacher/ChatbotBuilderPage.tsx
//
// Single-page NotebookLM-style chatbot builder.
// Layout: Name + Section picker at top, three columns below:
//   Left: Knowledge sources (drag-drop, URL, paste) with auto/manual split
//   Center: Persona cards + custom rules + welcome message
//   Right: Live chat preview (teacher can test the bot)

import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Save, Loader2, MessageSquare, X } from 'lucide-react';
import { usePageTitle } from '../../hooks/usePageTitle';
import { useToast } from '../../components/common';
import { chatbotApi } from '../../services/openmaicService';
import { GuardrailConfig } from '../../components/maic/GuardrailConfig';
import { KnowledgeUploader } from '../../components/maic/KnowledgeUploader';
import { ChatbotChat } from '../../components/maic/ChatbotChat';
import type {
  AIChatbot,
  AIChatbotCreatePayload,
  TeacherSection,
} from '../../types/chatbot';
import { cn } from '../../lib/utils';

// ─── Main Component ──────────────────────────────────────────────────────────

export function ChatbotBuilderPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const toast = useToast();

  // After create, we get the new ID for knowledge uploader and edit-mode saves.
  const [chatbotId, setChatbotId] = useState<string | null>(id ?? null);
  const effectiveChatbotId = id ?? chatbotId;
  const isEditMode = Boolean(effectiveChatbotId);
  usePageTitle(isEditMode ? 'Edit Chatbot' : 'New Chatbot');

  // Form state
  const [name, setName] = useState('');
  const [customRules, setCustomRules] = useState('');
  const [blockOffTopic, setBlockOffTopic] = useState(true);
  const [welcomeMessage, setWelcomeMessage] = useState('');
  const [selectedSectionIds, setSelectedSectionIds] = useState<string[]>([]);

  // Data state
  const [availableSections, setAvailableSections] = useState<TeacherSection[]>([]);

  // UI state
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [showChatPreview, setShowChatPreview] = useState(false);

  // Load sections on mount
  useEffect(() => {
    chatbotApi.mySections().then((res) => {
      setAvailableSections(res.data);
    }).catch(() => {
      // Sections may not be set up yet — non-blocking
    });
  }, []);

  // Load existing chatbot in edit mode
  useEffect(() => {
    if (!id) return;
    let cancelled = false;

    async function loadChatbot() {
      setIsLoading(true);
      try {
        const res = await chatbotApi.detail(id!);
        if (cancelled) return;
        const bot: AIChatbot = res.data;
        setName(bot.name);
        setCustomRules(bot.custom_rules);
        setBlockOffTopic(bot.block_off_topic);
        setWelcomeMessage(bot.welcome_message);
        setSelectedSectionIds(bot.sections?.map((s) => s.id) || []);
        setChatbotId(bot.id);
      } catch {
        if (!cancelled) {
          toast.error('Load failed', 'Could not load chatbot details.');
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    loadChatbot();
    return () => {
      cancelled = true;
    };
  }, [id, toast]);

  // Toggle section selection
  function toggleSection(sectionId: string) {
    setSelectedSectionIds((prev) =>
      prev.includes(sectionId)
        ? prev.filter((sid) => sid !== sectionId)
        : [...prev, sectionId],
    );
  }

  // Save handler
  async function handleSave() {
    if (!name.trim()) {
      toast.error('Validation', 'Please enter a chatbot name.');
      return;
    }

    const payload: AIChatbotCreatePayload = {
      name: name.trim(),
      persona_preset: 'study_buddy',
      custom_rules: customRules.trim(),
      block_off_topic: blockOffTopic,
      welcome_message: welcomeMessage.trim(),
      section_ids: selectedSectionIds,
    };

    setIsSaving(true);
    try {
      if (isEditMode && effectiveChatbotId) {
        await chatbotApi.update(effectiveChatbotId, payload);
        toast.success('Saved', 'Chatbot updated successfully.');
      } else {
        const res = await chatbotApi.create(payload);
        const createdId = res.data.id;
        setChatbotId(createdId);
        toast.success('Created', 'Chatbot created! Now add knowledge sources below.');
        // Switch to edit route so future saves reliably patch this chatbot.
        navigate(`/teacher/chatbots/${createdId}`, { replace: true });
      }
    } catch {
      toast.error('Save failed', 'Could not save chatbot. Please try again.');
    } finally {
      setIsSaving(false);
    }
  }

  // ─── Loading state ───────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="flex justify-center py-16" role="status" aria-label="Loading">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
        <span className="sr-only">Loading...</span>
      </div>
    );
  }

  // Group sections by grade for the picker
  const sectionsByGrade: Record<string, TeacherSection[]> = {};
  for (const sec of availableSections) {
    const key = sec.grade_name;
    if (!sectionsByGrade[key]) sectionsByGrade[key] = [];
    sectionsByGrade[key].push(sec);
  }

  const previewWelcome =
    welcomeMessage.trim() || `Hi! I'm ${name || 'your chatbot'}. How can I help you?`;

  // ─── Render ──────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6 max-w-7xl">
      {/* Back link + title + test button */}
      <div className="flex items-start justify-between">
        <div>
          <button
            type="button"
            onClick={() => navigate('/teacher/chatbots')}
            className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 transition-colors mb-4"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Chatbots
          </button>
          <h1 className="text-2xl font-bold text-gray-900">
            {isEditMode ? 'Edit Chatbot' : 'Create Chatbot'}
          </h1>
        </div>

        {/* Chat preview toggle */}
        {chatbotId && (
          <button
            type="button"
            onClick={() => setShowChatPreview(!showChatPreview)}
            className={cn(
              'inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors',
              showChatPreview
                ? 'bg-indigo-100 text-indigo-700 hover:bg-indigo-200'
                : 'bg-white border border-gray-300 text-gray-700 hover:bg-gray-50',
            )}
          >
            <MessageSquare className="h-4 w-4" />
            {showChatPreview ? 'Hide Preview' : 'Test Chat'}
          </button>
        )}
      </div>

      {/* ─── Main layout ──────────────────────────────────────────────────── */}
      <div className={cn(
        'grid gap-6',
        showChatPreview ? 'grid-cols-1 xl:grid-cols-[1fr_380px]' : 'grid-cols-1',
      )}>
        {/* Left side: config panels */}
        <div className="space-y-6">
          {/* ─── Top: Name + Sections ───────────────────────────────────────── */}
          <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm space-y-4">
            {/* Name */}
            <div>
              <label htmlFor="chatbot-name" className="block text-sm font-medium text-gray-700 mb-1">
                Chatbot Name
              </label>
              <input
                id="chatbot-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Physics Study Buddy, History Quiz Master"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-indigo-500 focus:border-indigo-500"
              />
            </div>

            {/* Section Picker */}
            {availableSections.length > 0 && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Visible to Sections
                </label>
                <p className="text-xs text-gray-400 mb-2">
                  Choose which class sections can see and use this chatbot. Course content from these sections will be auto-ingested.
                </p>
                <div className="space-y-3">
                  {Object.entries(sectionsByGrade).map(([gradeName, sections]) => (
                    <div key={gradeName}>
                      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5">
                        {gradeName}
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {sections.map((sec) => {
                          const isSelected = selectedSectionIds.includes(sec.id);
                          return (
                            <button
                              key={sec.id}
                              type="button"
                              onClick={() => toggleSection(sec.id)}
                              className={cn(
                                'inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-medium',
                                'border transition-all duration-150',
                                isSelected
                                  ? 'bg-indigo-50 border-indigo-300 text-indigo-700 shadow-sm'
                                  : 'bg-white border-gray-200 text-gray-600 hover:border-gray-300 hover:bg-gray-50',
                              )}
                            >
                              {sec.grade_short_code}-{sec.name}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
                {selectedSectionIds.length === 0 && (
                  <p className="mt-2 text-xs text-amber-600">
                    No sections selected — students won't see this chatbot until you assign sections.
                  </p>
                )}
              </div>
            )}

            {/* Welcome Message */}
            <div>
              <label
                htmlFor="welcome-message"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                Welcome Message <span className="font-normal text-gray-400">(optional)</span>
              </label>
              <textarea
                id="welcome-message"
                value={welcomeMessage}
                onChange={(e) => setWelcomeMessage(e.target.value)}
                rows={2}
                placeholder="The first message students see when they open the chat..."
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-indigo-500 focus:border-indigo-500"
              />
            </div>
          </div>

          {/* ─── Two Columns: Knowledge (left) + Persona (right) ──────────── */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Left: Knowledge Sources */}
            <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
              <h2 className="text-lg font-semibold text-gray-900 mb-1">Sources</h2>
              <p className="text-xs text-gray-400 mb-4">
                Course content from assigned sections is auto-ingested. Upload additional files, paste text, or add URLs.
              </p>
              {chatbotId ? (
                <KnowledgeUploader chatbotId={chatbotId} />
              ) : (
                <div className="rounded-lg border-2 border-dashed border-gray-200 p-8 text-center">
                  <p className="text-sm text-gray-400">
                    Save the chatbot first to start adding sources.
                  </p>
                </div>
              )}
            </div>

            {/* Right: Persona + Guardrails */}
            <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Rules & Guardrails</h2>
              <GuardrailConfig
                customRules={customRules}
                onCustomRulesChange={setCustomRules}
                blockOffTopic={blockOffTopic}
                onBlockOffTopicChange={setBlockOffTopic}
              />
            </div>
          </div>

          {/* ─── Actions ────────────────────────────────────────────────────── */}
          <div className="flex items-center gap-3 pb-8">
            <button
              type="button"
              onClick={handleSave}
              disabled={isSaving}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
            >
              {isSaving ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              {isSaving ? 'Saving...' : 'Save Chatbot'}
            </button>
            <button
              type="button"
              onClick={() => navigate('/teacher/chatbots')}
              className="px-4 py-2.5 rounded-lg border border-gray-300 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>

        {/* ─── Right: Chat Preview Panel ────────────────────────────────── */}
        {showChatPreview && chatbotId && (
          <div className="hidden xl:flex flex-col h-[calc(100vh-8rem)] sticky top-4">
            <div className="flex-1 rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden flex flex-col">
              {/* Preview header */}
              <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-gray-50">
                <div className="flex items-center gap-2">
                  <MessageSquare className="h-4 w-4 text-indigo-500" />
                  <h3 className="text-sm font-semibold text-gray-700">Chat Preview</h3>
                </div>
                <button
                  type="button"
                  onClick={() => setShowChatPreview(false)}
                  className="p-1 rounded text-gray-400 hover:text-gray-600 hover:bg-gray-100"
                  aria-label="Close preview"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <p className="px-4 py-2 text-[11px] text-gray-400 bg-amber-50 border-b border-amber-100">
                Preview mode — test your chatbot as a student would see it. Messages are temporary.
              </p>
              <div className="flex-1 min-h-0">
                <ChatbotChat
                  chatbotId={chatbotId}
                  welcomeMessage={previewWelcome}
                  mode="preview"
                />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ─── Mobile Chat Preview (slide-up panel) ───────────────────────── */}
      {showChatPreview && chatbotId && (
        <div className="xl:hidden fixed inset-0 z-50 bg-black/30" onClick={() => setShowChatPreview(false)}>
          <div
            className="absolute bottom-0 left-0 right-0 h-[85vh] bg-white rounded-t-2xl shadow-2xl flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Mobile preview header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
              <div className="flex items-center gap-2">
                <MessageSquare className="h-4 w-4 text-indigo-500" />
                <h3 className="text-sm font-semibold text-gray-700">Chat Preview</h3>
              </div>
              <button
                type="button"
                onClick={() => setShowChatPreview(false)}
                className="p-1 rounded text-gray-400 hover:text-gray-600 hover:bg-gray-100"
                aria-label="Close preview"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <p className="px-4 py-2 text-[11px] text-gray-400 bg-amber-50 border-b border-amber-100">
              Preview mode — test your chatbot as a student would see it.
            </p>
            <div className="flex-1 min-h-0">
              <ChatbotChat
                chatbotId={chatbotId}
                welcomeMessage={previewWelcome}
                mode="preview"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
