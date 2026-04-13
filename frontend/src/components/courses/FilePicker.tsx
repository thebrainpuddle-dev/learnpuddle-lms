// src/components/courses/FilePicker.tsx
//
// Extracted from MediaLibraryPage.tsx — modal component for selecting
// existing media uploads from within the course editor.
// Keeps: search, filter by type, thumbnail display, selection callback.

import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Input } from '../../components/common/Input';
import {
  adminMediaService,
  type MediaAsset,
} from '../../services/adminMediaService';
import {
  MagnifyingGlassIcon,
  PlayCircleIcon,
  DocumentTextIcon,
  LinkIcon,
  XMarkIcon,
  FolderIcon,
  FilmIcon,
  GlobeAltIcon,
  DocumentIcon,
} from '@heroicons/react/24/outline';
import { format } from 'date-fns';

type MediaTab = 'ALL' | 'DOCUMENT' | 'VIDEO' | 'LINK';

const TABS: { key: MediaTab; label: string; icon: React.ElementType }[] = [
  { key: 'ALL', label: 'All', icon: FolderIcon },
  { key: 'DOCUMENT', label: 'Documents', icon: DocumentIcon },
  { key: 'VIDEO', label: 'Videos', icon: FilmIcon },
  { key: 'LINK', label: 'Links', icon: GlobeAltIcon },
];

function formatFileSize(bytes: number | null): string {
  if (!bytes) return '-';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

interface FilePickerProps {
  /** Whether the modal is open */
  isOpen: boolean;
  /** Close callback */
  onClose: () => void;
  /** Called when a file is selected */
  onSelect: (asset: MediaAsset) => void;
  /** Optional: filter to specific media types */
  allowedTypes?: MediaTab[];
}

export const FilePicker: React.FC<FilePickerProps> = ({
  isOpen,
  onClose,
  onSelect,
  allowedTypes,
}) => {
  const [activeTab, setActiveTab] = useState<MediaTab>('ALL');
  const [search, setSearch] = useState('');

  const queryParams = useMemo(() => {
    const p: Record<string, string> = {};
    if (activeTab !== 'ALL') p.media_type = activeTab;
    if (search) p.search = search;
    return p;
  }, [activeTab, search]);

  const { data: mediaData, isLoading } = useQuery({
    queryKey: ['mediaAssets', queryParams],
    queryFn: () => adminMediaService.listMedia(queryParams),
    enabled: isOpen,
  });

  const assets = mediaData?.results ?? [];

  const filteredTabs = allowedTypes
    ? TABS.filter((t) => t.key === 'ALL' || allowedTypes.includes(t.key))
    : TABS;

  const backendOrigin = (process.env.REACT_APP_API_URL || 'http://localhost:8000/api').replace(/\/api\/?$/, '');
  const resolveUrl = (u: string) => {
    if (!u) return '';
    if (u.startsWith('http')) return u;
    return `${backendOrigin}${u.startsWith('/') ? '' : '/'}${u}`;
  };

  const handleSelect = (asset: MediaAsset) => {
    onSelect(asset);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-0 sm:items-center sm:p-4"
      onClick={onClose}
    >
      <div
        className="flex max-h-[92vh] w-full max-w-4xl flex-col overflow-hidden rounded-t-2xl bg-white sm:rounded-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900">Select a File</h3>
          <button
            onClick={onClose}
            className="p-1 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100"
          >
            <XMarkIcon className="h-5 w-5" />
          </button>
        </div>

        {/* Tabs + Search */}
        <div className="p-4 space-y-3 border-b border-gray-100">
          <div className="flex items-center gap-1 overflow-x-auto rounded-lg bg-gray-100 p-1 w-fit">
            {filteredTabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  activeTab === tab.key
                    ? 'bg-white text-gray-900 shadow-sm'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                <tab.icon className="h-4 w-4" />
                {tab.label}
              </button>
            ))}
          </div>

          <div className="w-full max-w-md">
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by title or filename..."
              leftIcon={<MagnifyingGlassIcon className="h-5 w-5" />}
            />
          </div>
        </div>

        {/* Grid */}
        <div className="flex-1 overflow-y-auto p-4">
          {isLoading ? (
            <div className="text-center py-16 text-gray-500">Loading...</div>
          ) : assets.length === 0 ? (
            <div className="text-center py-16">
              <FolderIcon className="h-16 w-16 mx-auto text-gray-300 mb-4" />
              <h3 className="text-lg font-medium text-gray-900 mb-1">No media assets</h3>
              <p className="text-gray-500">Upload files from the course editor to see them here.</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
              {assets.map((asset) => (
                <button
                  key={asset.id}
                  onClick={() => handleSelect(asset)}
                  className="bg-white rounded-xl border border-gray-200 overflow-hidden hover:shadow-md hover:border-primary-300 transition-all text-left group"
                >
                  {/* Thumbnail */}
                  <div className="h-28 bg-gray-100 flex items-center justify-center relative">
                    {asset.thumbnail_url ? (
                      <img
                        src={resolveUrl(asset.thumbnail_url)}
                        alt={asset.title}
                        className="w-full h-full object-cover"
                      />
                    ) : asset.media_type === 'VIDEO' ? (
                      <div className="w-full h-full bg-gradient-to-br from-slate-700 to-slate-900 flex items-center justify-center">
                        <PlayCircleIcon className="h-10 w-10 text-white/80" />
                      </div>
                    ) : asset.media_type === 'DOCUMENT' ? (
                      <div className="w-full h-full bg-gradient-to-br from-orange-50 to-amber-100 flex items-center justify-center">
                        <DocumentTextIcon className="h-10 w-10 text-orange-500" />
                      </div>
                    ) : asset.media_type === 'LINK' ? (
                      <div className="w-full h-full bg-gradient-to-br from-purple-50 to-violet-100 flex items-center justify-center">
                        <LinkIcon className="h-10 w-10 text-purple-500" />
                      </div>
                    ) : (
                      <FolderIcon className="h-10 w-10 text-gray-400" />
                    )}
                    <span className="absolute top-2 left-2 text-[10px] font-semibold uppercase bg-white/90 text-gray-600 rounded px-1.5 py-0.5">
                      {asset.media_type}
                    </span>
                  </div>

                  {/* Info */}
                  <div className="p-2.5 space-y-0.5">
                    <h4 className="text-xs font-medium text-gray-900 truncate">{asset.title}</h4>
                    <div className="flex items-center justify-between text-[10px] text-gray-500">
                      <span>{formatFileSize(asset.file_size)}</span>
                      <span>{format(new Date(asset.created_at), 'MMM d, yyyy')}</span>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
