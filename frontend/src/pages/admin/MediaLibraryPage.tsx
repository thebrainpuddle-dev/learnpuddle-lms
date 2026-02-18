// src/pages/admin/MediaLibraryPage.tsx

import React, { useState, useRef, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, Input, useToast, HlsVideoPlayer } from '../../components/common';
import {
  adminMediaService,
  type MediaAsset,
} from '../../services/adminMediaService';
import {
  MagnifyingGlassIcon,
  ArrowUpTrayIcon,
  PlayCircleIcon,
  DocumentTextIcon,
  LinkIcon,
  TrashIcon,
  PencilIcon,
  EyeIcon,
  XMarkIcon,
  FolderIcon,
  CheckIcon,
  FilmIcon,
  GlobeAltIcon,
  DocumentIcon,
} from '@heroicons/react/24/outline';
import { format } from 'date-fns';
import { usePageTitle } from '../../hooks/usePageTitle';

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

function getMediaIcon(type: string) {
  switch (type) {
    case 'VIDEO':
      return <PlayCircleIcon className="h-10 w-10 text-blue-500" />;
    case 'DOCUMENT':
      return <DocumentTextIcon className="h-10 w-10 text-orange-500" />;
    case 'LINK':
      return <LinkIcon className="h-10 w-10 text-purple-500" />;
    default:
      return <FolderIcon className="h-10 w-10 text-gray-400" />;
  }
}

export const MediaLibraryPage: React.FC = () => {
  usePageTitle('Media Library');
  const toast = useToast();
  const qc = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [activeTab, setActiveTab] = useState<MediaTab>('ALL');
  const [search, setSearch] = useState('');
  const [previewAsset, setPreviewAsset] = useState<MediaAsset | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');

  // Upload form state
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadType, setUploadType] = useState<'DOCUMENT' | 'VIDEO' | 'LINK'>('DOCUMENT');
  const [uploadTitle, setUploadTitle] = useState('');
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadUrl, setUploadUrl] = useState('');

  // Queries
  const { data: statsData } = useQuery({
    queryKey: ['mediaStats'],
    queryFn: () => adminMediaService.getStats(),
  });

  const queryParams = useMemo(() => {
    const p: Record<string, string> = {};
    if (activeTab !== 'ALL') p.media_type = activeTab;
    if (search) p.search = search;
    return p;
  }, [activeTab, search]);

  const { data: mediaData, isLoading } = useQuery({
    queryKey: ['mediaAssets', queryParams],
    queryFn: () => adminMediaService.listMedia(queryParams),
  });

  const assets = mediaData?.results ?? [];

  // Mutations
  const uploadMut = useMutation({
    mutationFn: () =>
      adminMediaService.uploadMedia({
        title: uploadTitle,
        media_type: uploadType,
        file: uploadFile || undefined,
        file_url: uploadType === 'LINK' ? uploadUrl : undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['mediaAssets'] });
      qc.invalidateQueries({ queryKey: ['mediaStats'] });
      toast.success('Uploaded', 'Media asset added to library.');
      resetUploadForm();
    },
    onError: () => toast.error('Upload failed', 'Please check the file and try again.'),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => adminMediaService.deleteMedia(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['mediaAssets'] });
      qc.invalidateQueries({ queryKey: ['mediaStats'] });
      toast.success('Deleted', 'Media asset removed.');
    },
  });

  const updateMut = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) =>
      adminMediaService.updateMedia(id, { title }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['mediaAssets'] });
      setEditingId(null);
      toast.success('Updated', 'Title saved.');
    },
  });

  const resetUploadForm = () => {
    setUploadOpen(false);
    setUploadTitle('');
    setUploadFile(null);
    setUploadUrl('');
  };

  const handleUpload = () => {
    if (uploadType === 'LINK') {
      if (!uploadUrl.trim()) return;
    } else {
      if (!uploadFile) return;
    }
    uploadMut.mutate();
  };

  const backendOrigin = (process.env.REACT_APP_API_URL || 'http://localhost:8000/api').replace(/\/api\/?$/, '');
  const resolveUrl = (u: string) => {
    if (!u) return '';
    if (u.startsWith('http')) return u;
    return `${backendOrigin}${u.startsWith('/') ? '' : '/'}${u}`;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Media Library</h1>
          <p className="mt-1 text-sm text-gray-500">
            Upload and manage media assets. Pull them into any course.
            {statsData && (
              <span className="ml-2 text-gray-400">
                ({statsData.total ?? 0} assets)
              </span>
            )}
          </p>
        </div>
        <Button variant="primary" onClick={() => setUploadOpen(true)}>
          <ArrowUpTrayIcon className="h-4 w-4 mr-2" />
          Upload
        </Button>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 bg-gray-100 p-1 rounded-lg w-fit">
        {TABS.map((tab) => {
            const count =
              tab.key === 'ALL'
                ? statsData?.total ?? 0
                : (statsData?.[tab.key as keyof typeof statsData] ?? 0);
          return (
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
              {count > 0 && (
                <span className="text-xs bg-gray-200 text-gray-600 rounded-full px-1.5 py-0.5 ml-1">
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Search */}
      <div className="max-w-md">
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by title or filename..."
          leftIcon={<MagnifyingGlassIcon className="h-5 w-5" />}
        />
      </div>

      {/* Grid */}
      {isLoading ? (
        <div className="text-center py-16 text-gray-500">Loading...</div>
      ) : assets.length === 0 ? (
        <div className="text-center py-16">
          <FolderIcon className="h-16 w-16 mx-auto text-gray-300 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-1">No media assets</h3>
          <p className="text-gray-500 mb-4">Upload documents, videos, or links to get started.</p>
          <Button variant="primary" onClick={() => setUploadOpen(true)}>
            <ArrowUpTrayIcon className="h-4 w-4 mr-2" />
            Upload your first asset
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {assets.map((asset) => (
            <div
              key={asset.id}
              className="bg-white rounded-xl border border-gray-200 overflow-hidden hover:shadow-md transition-shadow group"
            >
              {/* Thumbnail / Icon area */}
              <div className="h-36 bg-gray-100 flex items-center justify-center relative">
                {asset.thumbnail_url ? (
                  <img
                    src={resolveUrl(asset.thumbnail_url)}
                    alt={asset.title}
                    className="w-full h-full object-cover"
                  />
                ) : asset.media_type === 'VIDEO' ? (
                  <div className="w-full h-full bg-gradient-to-br from-slate-700 to-slate-900 flex items-center justify-center">
                    <div className="flex flex-col items-center gap-1.5">
                      <PlayCircleIcon className="h-12 w-12 text-white/80" />
                      <span className="text-[10px] text-white/50 font-medium tracking-wide uppercase">{asset.file_name?.split('.').pop() || 'video'}</span>
                    </div>
                  </div>
                ) : asset.media_type === 'DOCUMENT' ? (
                  <div className="w-full h-full bg-gradient-to-br from-orange-50 to-amber-100 flex items-center justify-center">
                    <div className="flex flex-col items-center gap-1.5">
                      <DocumentTextIcon className="h-12 w-12 text-orange-500" />
                      <span className="text-[10px] text-orange-400 font-semibold uppercase tracking-wide">{asset.file_name?.split('.').pop() || 'doc'}</span>
                    </div>
                  </div>
                ) : asset.media_type === 'LINK' ? (
                  <div className="w-full h-full bg-gradient-to-br from-purple-50 to-violet-100 flex items-center justify-center">
                    <div className="flex flex-col items-center gap-1.5">
                      <LinkIcon className="h-12 w-12 text-purple-500" />
                      <span className="text-[10px] text-purple-400 font-semibold uppercase tracking-wide">link</span>
                    </div>
                  </div>
                ) : (
                  getMediaIcon(asset.media_type)
                )}
                {/* Overlay actions */}
                <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors flex items-center justify-center gap-2 opacity-0 group-hover:opacity-100">
                  <button
                    onClick={() => setPreviewAsset(asset)}
                    className="p-2 bg-white rounded-full shadow hover:bg-gray-100"
                    title="Preview"
                  >
                    <EyeIcon className="h-4 w-4 text-gray-700" />
                  </button>
                  <button
                    onClick={() => {
                      if (window.confirm(`Delete "${asset.title}"?`))
                        deleteMut.mutate(asset.id);
                    }}
                    className="p-2 bg-white rounded-full shadow hover:bg-red-50"
                    title="Delete"
                  >
                    <TrashIcon className="h-4 w-4 text-red-600" />
                  </button>
                </div>
                {/* Type badge */}
                <span className="absolute top-2 left-2 text-[10px] font-semibold uppercase bg-white/90 text-gray-600 rounded px-1.5 py-0.5">
                  {asset.media_type}
                </span>
              </div>

              {/* Info */}
              <div className="p-3 space-y-1">
                {editingId === asset.id ? (
                  <div className="flex items-center gap-1">
                    <input
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      className="flex-1 text-sm px-2 py-1 border border-gray-300 rounded"
                      autoFocus
                      onKeyDown={(e) => {
                        if (e.key === 'Enter')
                          updateMut.mutate({ id: asset.id, title: editTitle });
                        if (e.key === 'Escape') setEditingId(null);
                      }}
                    />
                    <button
                      onClick={() => updateMut.mutate({ id: asset.id, title: editTitle })}
                      className="p-1 text-emerald-600 hover:bg-emerald-50 rounded"
                    >
                      <CheckIcon className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => setEditingId(null)}
                      className="p-1 text-gray-400 hover:bg-gray-100 rounded"
                    >
                      <XMarkIcon className="h-4 w-4" />
                    </button>
                  </div>
                ) : (
                  <div className="flex items-start justify-between gap-1">
                    <h4 className="text-sm font-medium text-gray-900 truncate flex-1">
                      {asset.title}
                    </h4>
                    <button
                      onClick={() => {
                        setEditingId(asset.id);
                        setEditTitle(asset.title);
                      }}
                      className="p-0.5 text-gray-400 hover:text-gray-600 flex-shrink-0"
                    >
                      <PencilIcon className="h-3.5 w-3.5" />
                    </button>
                  </div>
                )}
                <div className="flex items-center justify-between text-xs text-gray-500">
                  <span>{formatFileSize(asset.file_size)}</span>
                  <span>{format(new Date(asset.created_at), 'MMM d, yyyy')}</span>
                </div>
                {asset.file_name && (
                  <p className="text-xs text-gray-400 truncate">{asset.file_name}</p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Upload Modal */}
      {uploadOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div
            className="bg-white rounded-xl p-6 max-w-lg w-full mx-4 space-y-5"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-gray-900">Upload Media</h3>
              <button
                onClick={resetUploadForm}
                className="text-gray-400 hover:text-gray-600"
              >
                <XMarkIcon className="h-6 w-6" />
              </button>
            </div>

            {/* Type selector */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Media Type
              </label>
              <div className="flex gap-2">
                {(['DOCUMENT', 'VIDEO', 'LINK'] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => {
                      setUploadType(t);
                      setUploadFile(null);
                      setUploadUrl('');
                    }}
                    className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium border transition-colors ${
                      uploadType === t
                        ? 'border-primary-500 bg-primary-50 text-primary-700'
                        : 'border-gray-200 text-gray-600 hover:border-gray-300'
                    }`}
                  >
                    {t === 'DOCUMENT' ? 'Document' : t === 'VIDEO' ? 'Video' : 'Link'}
                  </button>
                ))}
              </div>
            </div>

            {/* Title */}
            <Input
              label="Title"
              value={uploadTitle}
              onChange={(e) => setUploadTitle(e.target.value)}
              placeholder="Give this asset a name"
            />

            {/* File or URL input */}
            {uploadType === 'LINK' ? (
              <Input
                label="URL"
                value={uploadUrl}
                onChange={(e) => setUploadUrl(e.target.value)}
                placeholder="https://..."
              />
            ) : (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  File
                </label>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={
                    uploadType === 'VIDEO'
                      ? 'video/*'
                      : '.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.txt,.md,.csv'
                  }
                  onChange={(e) => {
                    const f = e.target.files?.[0] || null;
                    setUploadFile(f);
                    if (f && !uploadTitle) setUploadTitle(f.name.replace(/\.[^.]+$/, ''));
                  }}
                  className="hidden"
                />
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="flex items-center justify-center border-2 border-dashed border-gray-300 rounded-lg p-6 cursor-pointer hover:border-primary-400 transition-colors"
                >
                  {uploadFile ? (
                    <div className="text-center">
                      <p className="text-sm font-medium text-gray-900">{uploadFile.name}</p>
                      <p className="text-xs text-gray-500 mt-1">
                        {formatFileSize(uploadFile.size)}
                      </p>
                    </div>
                  ) : (
                    <div className="text-center">
                      <ArrowUpTrayIcon className="h-8 w-8 text-gray-400 mx-auto mb-2" />
                      <p className="text-sm text-gray-500">
                        Click to choose a {uploadType === 'VIDEO' ? 'video' : 'document'}
                      </p>
                    </div>
                  )}
                </div>
              </div>
            )}

            <div className="flex justify-end gap-3 pt-2">
              <Button variant="outline" onClick={resetUploadForm}>
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleUpload}
                loading={uploadMut.isPending}
                disabled={
                  uploadType === 'LINK'
                    ? !uploadUrl.trim()
                    : !uploadFile
                }
              >
                Upload
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Preview Modal */}
      {previewAsset && (() => {
        const a = previewAsset;
        return (
          <div
            className="fixed inset-0 bg-black/60 flex items-center justify-center z-50"
            onClick={() => setPreviewAsset(null)}
          >
            <div
              className="bg-white rounded-xl max-w-3xl w-full mx-4 max-h-[85vh] overflow-hidden flex flex-col"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Header */}
              <div className="flex items-center justify-between p-4 border-b border-gray-200">
                <div className="flex items-center gap-2 min-w-0">
                  {a.media_type === 'VIDEO' && <PlayCircleIcon className="h-5 w-5 text-blue-500 flex-shrink-0" />}
                  {a.media_type === 'DOCUMENT' && <DocumentTextIcon className="h-5 w-5 text-orange-500 flex-shrink-0" />}
                  {a.media_type === 'LINK' && <LinkIcon className="h-5 w-5 text-purple-500 flex-shrink-0" />}
                  <h3 className="text-lg font-semibold text-gray-900 truncate">{a.title}</h3>
                  <span className="text-xs text-gray-500 uppercase flex-shrink-0">{a.media_type}</span>
                </div>
                <button
                  onClick={() => setPreviewAsset(null)}
                  className="p-1 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100"
                >
                  <XMarkIcon className="h-5 w-5" />
                </button>
              </div>

              {/* Body */}
              <div className="p-6 overflow-y-auto flex-1">
                {a.media_type === 'VIDEO' ? (
                  a.file_url ? (
                    <HlsVideoPlayer
                      src={resolveUrl(a.file_url)}
                      className="w-full rounded-lg bg-black aspect-video"
                    />
                  ) : (
                    <p className="text-gray-400 text-center py-8">No video file</p>
                  )
                ) : a.media_type === 'DOCUMENT' ? (
                  a.file_url ? (
                    <div className="flex flex-col items-center justify-center py-12">
                      <div className="w-20 h-24 bg-gradient-to-br from-orange-50 to-amber-100 rounded-lg flex items-center justify-center mb-4 shadow-sm border border-orange-200">
                        <DocumentTextIcon className="h-10 w-10 text-orange-500" />
                      </div>
                      <p className="font-semibold text-gray-900 text-lg">{a.title}</p>
                      <p className="text-sm text-gray-500 mt-1">{a.file_name}</p>
                      {a.file_size && (
                        <p className="text-xs text-gray-400 mt-0.5">{formatFileSize(a.file_size)}</p>
                      )}
                      <div className="flex items-center gap-3 mt-5">
                        <a
                          href={resolveUrl(a.file_url)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700 transition-colors"
                        >
                          <EyeIcon className="h-4 w-4" />
                          Open in new tab
                        </a>
                        <a
                          href={resolveUrl(a.file_url)}
                          download={a.file_name || a.title}
                          className="inline-flex items-center gap-2 px-4 py-2 border border-gray-300 text-gray-700 text-sm font-medium rounded-lg hover:bg-gray-50 transition-colors"
                        >
                          <ArrowUpTrayIcon className="h-4 w-4 rotate-180" />
                          Download
                        </a>
                      </div>
                    </div>
                  ) : (
                    <p className="text-gray-400 text-center py-8">No file uploaded</p>
                  )
                ) : a.media_type === 'LINK' ? (
                  a.file_url ? (
                    <div className="space-y-4">
                      <div className="p-4 bg-purple-50 rounded-lg">
                        <div className="flex items-center gap-2 mb-2">
                          <LinkIcon className="h-5 w-5 text-purple-500" />
                          <span className="font-medium text-gray-900">{a.title}</span>
                        </div>
                        <a
                          href={a.file_url.startsWith('http') ? a.file_url : `https://${a.file_url}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sm text-primary-600 hover:underline break-all"
                        >
                          {a.file_url}
                        </a>
                      </div>
                    </div>
                  ) : (
                    <p className="text-gray-400 text-center py-8">No URL</p>
                  )
                ) : null}
              </div>

              {/* Footer */}
              <div className="p-4 border-t border-gray-200 flex items-center justify-between">
                <div className="text-xs text-gray-500 space-x-3">
                  {a.file_size && <span>{formatFileSize(a.file_size)}</span>}
                  {a.uploaded_by_name && <span>by {a.uploaded_by_name}</span>}
                  <span>{format(new Date(a.created_at), 'MMM d, yyyy')}</span>
                </div>
                <Button variant="outline" onClick={() => setPreviewAsset(null)}>
                  Close
                </Button>
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
};
