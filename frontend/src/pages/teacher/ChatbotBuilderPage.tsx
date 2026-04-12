// src/pages/teacher/ChatbotBuilderPage.tsx
//
// Create / Edit form for AI chatbots. Detects edit mode via :id param.
// Includes persona preset selection, custom rules, guardrails, and
// knowledge upload sections.

import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Save, Loader2 } from 'lucide-react';
import { usePageTitle } from '../../hooks/usePageTitle';
import { useToast } from '../../components/common';
import { chatbotApi } from '../../services/openmaicService';
import { GuardrailConfig } from '../../components/maic/GuardrailConfig';
import { KnowledgeUploader } from '../../components/maic/KnowledgeUploader';
import type {
  AIChatbot,
  AIChatbotCreatePayload,
  PersonaPreset,
} from '../../types/chatbot';

// ─── Main Component ──────────────────────────────────────────────────────────

export function ChatbotBuilderPage() {
  const { id } = useParams<{ id: string }>();
  const isEditMode = Boolean(id);
  usePageTitle(isEditMode ? 'Edit Chatbot' : 'New Chatbot');

  const navigate = useNavigate();
  const toast = useToast();

  // Form state
  const [name, setName] = useState('');
  const [personaPreset, setPersonaPreset] = useState<PersonaPreset>('tutor');
  const [personaDescription, setPersonaDescription] = useState('');
  const [customRules, setCustomRules] = useState('');
  const [blockOffTopic, setBlockOffTopic] = useState(true);
  const [welcomeMessage, setWelcomeMessage] = useState('');

  // UI state
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

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
        setPersonaPreset(bot.persona_preset);
        setPersonaDescription(bot.persona_description);
        setCustomRules(bot.custom_rules);
        setBlockOffTopic(bot.block_off_topic);
        setWelcomeMessage(bot.welcome_message);
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

  // Save handler
  async function handleSave() {
    if (!name.trim()) {
      toast.error('Validation', 'Please enter a chatbot name.');
      return;
    }

    const payload: AIChatbotCreatePayload = {
      name: name.trim(),
      persona_preset: personaPreset,
      persona_description: personaDescription.trim(),
      custom_rules: customRules.trim(),
      block_off_topic: blockOffTopic,
      welcome_message: welcomeMessage.trim(),
    };

    setIsSaving(true);
    try {
      if (isEditMode && id) {
        await chatbotApi.update(id, payload);
        toast.success('Saved', 'Chatbot updated successfully.');
      } else {
        await chatbotApi.create(payload);
        toast.success('Created', 'Chatbot created successfully.');
      }
      navigate('/teacher/chatbots');
    } catch {
      toast.error('Save failed', 'Could not save chatbot. Please try again.');
    } finally {
      setIsSaving(false);
    }
  }

  // ─── Loading state ───────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="flex justify-center py-16">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
      </div>
    );
  }

  // ─── Render ──────────────────────────────────────────────────────────────

  return (
    <div className="space-y-8 max-w-3xl">
      {/* Back link + title */}
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
        <p className="mt-1 text-sm text-gray-500">
          {isEditMode
            ? 'Update your chatbot configuration and knowledge sources.'
            : 'Set up a new AI chatbot for your students.'}
        </p>
      </div>

      {/* ─── Form ──────────────────────────────────────────────────────────── */}
      <div className="space-y-6 bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
        {/* Name */}
        <div>
          <label htmlFor="chatbot-name" className="block text-sm font-medium text-gray-700 mb-1">
            Name
          </label>
          <input
            id="chatbot-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. History Tutor, Lab Assistant"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-indigo-500 focus:border-indigo-500"
          />
        </div>

        {/* Persona Description */}
        <div>
          <label
            htmlFor="persona-description"
            className="block text-sm font-medium text-gray-700 mb-1"
          >
            Persona Description
          </label>
          <textarea
            id="persona-description"
            value={personaDescription}
            onChange={(e) => setPersonaDescription(e.target.value)}
            rows={3}
            placeholder="Describe how the chatbot should behave and communicate..."
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-indigo-500 focus:border-indigo-500"
          />
        </div>

        {/* Welcome Message */}
        <div>
          <label
            htmlFor="welcome-message"
            className="block text-sm font-medium text-gray-700 mb-1"
          >
            Welcome Message
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

      {/* ─── Guardrail Config ───────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Guardrails</h2>
        <GuardrailConfig
          preset={personaPreset}
          onPresetChange={setPersonaPreset}
          customRules={customRules}
          onCustomRulesChange={setCustomRules}
          blockOffTopic={blockOffTopic}
          onBlockOffTopicChange={setBlockOffTopic}
        />
      </div>

      {/* ─── Knowledge Uploader ─────────────────────────────────────────── */}
      {isEditMode && id && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Knowledge Sources</h2>
          <KnowledgeUploader chatbotId={id} />
        </div>
      )}

      {/* ─── Actions ────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3">
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
  );
}
