// src/lib/export/useExportClassroom.ts
//
// React hook for bundling the entire classroom into a downloadable ZIP file.
// Includes slides, scenes, agents, chat history, notes, and a manifest.

import { useState, useCallback } from 'react';
import JSZip from 'jszip';
import { useMAICStageStore } from '../../stores/maicStageStore';

interface UseExportClassroomReturn {
  exportZip: (classroomTitle?: string) => Promise<void>;
  isExporting: boolean;
  progress: number;
  error: string | null;
}

/** Regex to detect data URLs */
const DATA_URL_RE = /^data:(image\/\w+);base64,/;

/**
 * Extract extension from a data URL MIME type (e.g. "image/png" -> "png").
 */
function extensionFromMime(mime: string): string {
  const sub = mime.split('/')[1] ?? 'png';
  const extMap: Record<string, string> = {
    jpeg: 'jpg',
    svg_xml: 'svg',
    'svg+xml': 'svg',
  };
  return extMap[sub] ?? sub;
}

/**
 * Convert a base64 data URL to a Uint8Array suitable for JSZip.
 */
function dataUrlToUint8Array(dataUrl: string): Uint8Array {
  const base64 = dataUrl.replace(DATA_URL_RE, '');
  const raw = atob(base64);
  const arr = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) {
    arr[i] = raw.charCodeAt(i);
  }
  return arr;
}

export function useExportClassroom(): UseExportClassroomReturn {
  const [isExporting, setIsExporting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const exportZip = useCallback(async (classroomTitle?: string) => {
    const { slides, scenes, agents, chatMessages, notes } = useMAICStageStore.getState();

    if (slides.length === 0 && scenes.length === 0) {
      setError('No classroom data to export.');
      return;
    }

    setIsExporting(true);
    setProgress(0);
    setError(null);

    try {
      const zip = new JSZip();
      const root = zip.folder('classroom')!;
      const title = classroomTitle || 'AI Classroom';

      // Total items for progress tracking
      const totalItems = slides.length + scenes.length + 4; // +4 for manifest, agents, chat, notes
      let processedItems = 0;

      const updateProgress = () => {
        processedItems++;
        setProgress(Math.round((processedItems / totalItems) * 100));
      };

      // ── manifest.json ──────────────────────────────────────────────────────
      const manifest = {
        version: '1.0',
        title,
        createdAt: new Date().toISOString(),
        slideCount: slides.length,
        sceneCount: scenes.length,
        agentCount: agents.length,
        generator: 'LearnPuddle AI Classroom',
      };
      root.file('manifest.json', JSON.stringify(manifest, null, 2));
      updateProgress();

      // ── agents.json ────────────────────────────────────────────────────────
      root.file('agents.json', JSON.stringify(agents, null, 2));
      updateProgress();

      // ── chat-history.json ──────────────────────────────────────────────────
      root.file('chat-history.json', JSON.stringify(chatMessages, null, 2));
      updateProgress();

      // ── notes.json ─────────────────────────────────────────────────────────
      root.file('notes.json', JSON.stringify(notes, null, 2));
      updateProgress();

      // ── slides/ ────────────────────────────────────────────────────────────
      const slidesFolder = root.folder('slides')!;
      const imagesFolder = slidesFolder.folder('images')!;
      let imageCounter = 0;

      for (let i = 0; i < slides.length; i++) {
        const slide = slides[i];

        // Deep-clone to avoid mutating store data
        const slideExport = JSON.parse(JSON.stringify(slide));

        // Extract inline data-URL images into separate files
        for (const el of slideExport.elements) {
          const imgSrc = el.src || (el.type === 'image' ? el.content : null);
          if (imgSrc && DATA_URL_RE.test(imgSrc)) {
            const match = imgSrc.match(DATA_URL_RE);
            if (match) {
              imageCounter++;
              const ext = extensionFromMime(match[1]);
              const imgFileName = `img-${String(i + 1).padStart(3, '0')}-${imageCounter}.${ext}`;
              imagesFolder.file(imgFileName, dataUrlToUint8Array(imgSrc));

              // Replace the data URL with a relative reference
              const refPath = `images/${imgFileName}`;
              if (el.src) el.src = refPath;
              if (el.type === 'image' && el.content === imgSrc) el.content = refPath;
            }
          }
        }

        const slideFileName = `slide-${String(i + 1).padStart(3, '0')}.json`;
        slidesFolder.file(slideFileName, JSON.stringify(slideExport, null, 2));
        updateProgress();

        // Yield to main thread periodically
        if (i % 10 === 0) {
          await new Promise((resolve) => setTimeout(resolve, 0));
        }
      }

      // ── scenes/ ────────────────────────────────────────────────────────────
      const scenesFolder = root.folder('scenes')!;

      for (let i = 0; i < scenes.length; i++) {
        const scene = scenes[i];
        const sceneFileName = `scene-${String(i + 1).padStart(3, '0')}.json`;
        scenesFolder.file(sceneFileName, JSON.stringify(scene, null, 2));
        updateProgress();

        if (i % 10 === 0) {
          await new Promise((resolve) => setTimeout(resolve, 0));
        }
      }

      // ── README.txt ─────────────────────────────────────────────────────────
      const readme = [
        `LearnPuddle AI Classroom Export`,
        `================================`,
        ``,
        `Title: ${title}`,
        `Exported: ${new Date().toLocaleString()}`,
        `Slides: ${slides.length}`,
        `Scenes: ${scenes.length}`,
        `Agents: ${agents.length}`,
        ``,
        `Directory Structure:`,
        `  manifest.json      - Export metadata`,
        `  agents.json        - AI agent profiles`,
        `  chat-history.json  - Chat messages`,
        `  notes.json         - Student notes`,
        `  slides/            - Individual slide data`,
        `    slide-NNN.json   - Slide content and elements`,
        `    images/          - Extracted slide images`,
        `  scenes/            - Scene data with actions`,
        `    scene-NNN.json   - Scene content`,
        ``,
        `This export was generated by the LearnPuddle AI Classroom player.`,
        `To re-import, use the classroom import feature in the MAIC player.`,
      ].join('\n');
      root.file('README.txt', readme);

      // ── Generate ZIP and download ──────────────────────────────────────────
      const blob = await zip.generateAsync(
        { type: 'blob', compression: 'DEFLATE', compressionOptions: { level: 6 } },
        (meta) => {
          // JSZip progress callback gives percent as 0-100
          setProgress(Math.round(meta.percent));
        },
      );

      const fileName = `${title.replace(/[^a-zA-Z0-9 ]/g, '').trim() || 'classroom'}-classroom.zip`;
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = fileName;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      setProgress(100);
    } catch (err) {
      console.error('Classroom ZIP export failed:', err);
      setError(err instanceof Error ? err.message : 'Export failed');
    } finally {
      setIsExporting(false);
    }
  }, []);

  return { exportZip, isExporting, progress, error };
}
