// src/pages/teacher/ChatbotListPage.tsx
//
// Teacher chatbot library — flat grid with section filter dropdown,
// search, clone support. Cards show section badge tags.

import React, { useEffect, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bot, Plus, Search, Filter } from 'lucide-react';
import { usePageTitle } from '../../hooks/usePageTitle';
import { useToast } from '../../components/common';
import { chatbotApi } from '../../services/openmaicService';
import { useChatbotStore } from '../../stores/chatbotStore';
import { ChatbotCard } from '../../components/maic/ChatbotCard';
import type { AIChatbot } from '../../types/chatbot';

// ─── Main Component ──────────────────────────────────────────────────────────

export function ChatbotListPage() {
  usePageTitle('AI Chatbots');
  const navigate = useNavigate();
  const toast = useToast();

  const [search, setSearch] = useState('');
  const [sectionFilter, setSectionFilter] = useState('');

  const { chatbots, isLoading, error, setChatbots, setLoading, setError, removeChatbot, addChatbot } =
    useChatbotStore();

  // Fetch chatbots on mount
  useEffect(() => {
    let cancelled = false;

    async function fetch() {
      setLoading(true);
      setError(null);
      try {
        const res = await chatbotApi.list();
        if (!cancelled) {
          setChatbots(res.data);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load chatbots');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetch();
    return () => {
      cancelled = true;
    };
  }, [setChatbots, setLoading, setError]);

  // Build unique section labels for filter
  const sectionOptions = useMemo(() => {
    const seen = new Map<string, string>();
    for (const bot of chatbots) {
      for (const sec of bot.sections || []) {
        if (!seen.has(sec.id)) {
          seen.set(sec.id, `${sec.grade_short_code}-${sec.name}`);
        }
      }
    }
    return Array.from(seen.entries())
      .map(([id, label]) => ({ id, label }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [chatbots]);

  // Filter by search + section
  const filtered = useMemo(() => {
    let result = chatbots;
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      result = result.filter((c) => c.name.toLowerCase().includes(q));
    }
    if (sectionFilter) {
      result = result.filter((c) =>
        c.sections?.some((s) => s.id === sectionFilter),
      );
    }
    return result;
  }, [chatbots, search, sectionFilter]);

  // Delete handler
  async function handleDelete(id: string) {
    if (!window.confirm('Are you sure you want to delete this chatbot?')) return;
    try {
      await chatbotApi.delete(id);
      removeChatbot(id);
    } catch (err: unknown) {
      toast.error('Delete failed', err instanceof Error ? err.message : 'Could not delete chatbot.');
    }
  }

  // Clone handler
  async function handleClone(id: string) {
    try {
      const res = await chatbotApi.clone(id);
      addChatbot(res.data);
      toast.success('Cloned', 'Chatbot cloned successfully. Knowledge sources were not copied.');
    } catch (err: unknown) {
      toast.error('Clone failed', err instanceof Error ? err.message : 'Could not clone chatbot.');
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">AI Chatbots</h1>
          <p className="mt-1 text-sm text-gray-500">
            Create and manage AI-powered chatbots for your students
          </p>
        </div>
        <button
          onClick={() => navigate('/teacher/chatbots/new')}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors shadow-sm"
        >
          <Plus className="h-4 w-4" />
          New Chatbot
        </button>
      </div>

      {/* Search + Section Filter */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1 max-w-sm">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <Search className="h-4 w-4 text-gray-400" />
          </div>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search chatbots..."
            className="w-full pl-9 pr-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-indigo-500 focus:border-indigo-500"
          />
        </div>

        {sectionOptions.length > 0 && (
          <div className="relative">
            <Filter className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400 pointer-events-none" />
            <select
              value={sectionFilter}
              onChange={(e) => setSectionFilter(e.target.value)}
              className="pl-9 pr-8 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:ring-indigo-500 focus:border-indigo-500 appearance-none"
            >
              <option value="">All Sections</option>
              {sectionOptions.map((opt) => (
                <option key={opt.id} value={opt.id}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Grid */}
      {isLoading ? (
        <div className="flex justify-center py-16" role="status" aria-label="Loading">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
          <span className="sr-only">Loading...</span>
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16">
          <Bot className="mx-auto h-12 w-12 text-gray-300" />
          <h3 className="mt-4 text-lg font-medium text-gray-900">
            {search.trim() || sectionFilter ? 'No chatbots match your filters' : 'No chatbots yet'}
          </h3>
          <p className="mt-2 text-sm text-gray-500">
            {search.trim() || sectionFilter
              ? 'Try a different search term or section filter.'
              : 'Create your first AI Chatbot to get started.'}
          </p>
          {!search.trim() && !sectionFilter && (
            <button
              onClick={() => navigate('/teacher/chatbots/new')}
              className="mt-6 inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors"
            >
              <Plus className="h-4 w-4" />
              Create Chatbot
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((chatbot) => (
            <ChatbotCard
              key={chatbot.id}
              chatbot={chatbot}
              onDelete={handleDelete}
              onClone={handleClone}
            />
          ))}
        </div>
      )}
    </div>
  );
}
