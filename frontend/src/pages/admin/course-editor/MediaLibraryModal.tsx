// course-editor/MediaLibraryModal.tsx
//
// Legacy inline media library picker modal. Shown when libraryOpen === true.

import React from 'react';
import {
  PlayCircleIcon,
  DocumentTextIcon,
  LinkIcon,
  XMarkIcon,
  FolderIcon,
  MagnifyingGlassIcon,
} from '@heroicons/react/24/outline';
import type { CourseEditorState } from './useCourseEditor';
import type { Content } from './types';

interface MediaLibraryModalProps {
  state: CourseEditorState;
}

export const MediaLibraryModal: React.FC<MediaLibraryModalProps> = ({ state }) => {
  const {
    libraryOpen,
    setLibraryOpen,
    librarySearch,
    setLibrarySearch,
    libraryFilter,
    setLibraryFilter,
    libraryAssets,
    fetchLibraryAssets,
    setNewContentData,
    setContentFile,
    setShowNewTextPreview,
    toast,
  } = state;

  if (!libraryOpen) return null;

  const closeLibrary = () => { setLibraryOpen(false); setLibrarySearch(''); setLibraryFilter('ALL'); };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={closeLibrary}>
      <div className="bg-white rounded-xl max-w-2xl w-full mx-4 max-h-[80vh] overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between p-4 border-b border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900">Choose from Media Library</h3>
          <button onClick={closeLibrary} className="p-1 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100">
            <XMarkIcon className="h-5 w-5" />
          </button>
        </div>

        <div className="p-4 border-b border-gray-200 space-y-3">
          <div className="flex items-center gap-2">
            {(['ALL', 'VIDEO', 'DOCUMENT', 'LINK'] as const).map((filter) => (
              <button
                key={filter}
                type="button"
                onClick={() => { setLibraryFilter(filter); void fetchLibraryAssets(librarySearch, filter); }}
                className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${libraryFilter === filter ? 'bg-primary-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
              >
                {filter}
              </button>
            ))}
          </div>
          <div className="relative">
            <label htmlFor="library-search" className="sr-only">Search media library</label>
            <MagnifyingGlassIcon className="h-5 w-5 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              id="library-search"
              name="library_search"
              type="text"
              value={librarySearch}
              onChange={async (e) => { const v = e.target.value; setLibrarySearch(v); await fetchLibraryAssets(v, libraryFilter); }}
              placeholder="Search media..."
              className="w-full pl-10 pr-3 py-2 border border-gray-300 rounded-lg text-sm"
            />
          </div>
        </div>

        <div className="overflow-y-auto flex-1 p-4">
          {libraryAssets.length === 0 ? (
            <div className="text-center py-12 text-gray-500">
              <FolderIcon className="h-12 w-12 mx-auto text-gray-300 mb-3" />
              <p className="text-sm">No assets found. Upload some in the Media Library first.</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {libraryAssets.map((asset) => (
                <button
                  key={asset.id}
                  onClick={() => {
                    setNewContentData((prev) => ({
                      ...prev,
                      content_type: asset.media_type as Content['content_type'],
                      title: prev.title || asset.title,
                      file_url: asset.file_url,
                    }));
                    setContentFile(null);
                    setShowNewTextPreview(false);
                    closeLibrary();
                    toast.success('Selected', `"${asset.title}" selected from library.`);
                  }}
                  className="flex flex-col items-center p-3 border border-gray-200 rounded-lg hover:border-primary-500 hover:bg-primary-50 transition-colors text-left"
                >
                  <div className="h-16 w-full flex items-center justify-center bg-gray-50 rounded mb-2">
                    {asset.media_type === 'VIDEO' && <PlayCircleIcon className="h-8 w-8 text-blue-500" />}
                    {asset.media_type === 'DOCUMENT' && <DocumentTextIcon className="h-8 w-8 text-orange-500" />}
                    {asset.media_type === 'LINK' && <LinkIcon className="h-8 w-8 text-purple-500" />}
                  </div>
                  <p className="text-xs font-medium text-gray-900 truncate w-full text-center">{asset.title}</p>
                  {asset.file_name && (
                    <p className="text-[10px] text-gray-400 truncate w-full text-center">{asset.file_name}</p>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
