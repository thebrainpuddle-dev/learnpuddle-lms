// src/lib/export/useExportPptx.ts
//
// React hook for client-side PowerPoint export using pptxgenjs.
// Reads slides and agents from maicStageStore and produces a .pptx download.

import { useState, useCallback } from 'react';
import PptxGenJS from 'pptxgenjs';
import { useMAICStageStore } from '../../stores/maicStageStore';
import type { MAICSlideElement } from '../../types/maic';

interface UseExportPptxReturn {
  exportPptx: (classroomTitle?: string) => Promise<void>;
  isExporting: boolean;
  progress: number;
  error: string | null;
}

// Widescreen 16:9 dimensions in inches
const SLIDE_WIDTH = 13.33;
const SLIDE_HEIGHT = 7.5;

/**
 * Convert a percentage-based position (0-100) to inches for the widescreen layout.
 */
function pctToInchesX(pct: number): number {
  return (pct / 100) * SLIDE_WIDTH;
}

function pctToInchesY(pct: number): number {
  return (pct / 100) * SLIDE_HEIGHT;
}

/**
 * Map element style properties to pptxgenjs text options.
 */
function buildTextOptions(el: MAICSlideElement): PptxGenJS.TextPropsOptions {
  const opts: PptxGenJS.TextPropsOptions = {
    x: pctToInchesX(el.x),
    y: pctToInchesY(el.y),
    w: pctToInchesX(el.width),
    h: pctToInchesY(el.height),
  };

  const style = el.style ?? {};

  if (style.fontSize) opts.fontSize = Number(style.fontSize);
  if (style.color) opts.color = String(style.color).replace('#', '');
  if (style.bold) opts.bold = Boolean(style.bold);
  if (style.italic) opts.italic = Boolean(style.italic);
  if (style.align) opts.align = String(style.align) as PptxGenJS.HAlign;
  if (style.fontFace) opts.fontFace = String(style.fontFace);

  return opts;
}

/**
 * Map a shape name string to the nearest PptxGenJS shape type.
 */
function mapShapeType(content: string): PptxGenJS.ShapeType {
  const PptxShapes = PptxGenJS.ShapeType;
  const name = content.toLowerCase().trim();

  const shapeMap: Record<string, PptxGenJS.ShapeType> = {
    rect: PptxShapes.rect,
    rectangle: PptxShapes.rect,
    roundrect: PptxShapes.roundRect,
    ellipse: PptxShapes.ellipse,
    oval: PptxShapes.ellipse,
    circle: PptxShapes.ellipse,
    triangle: PptxShapes.triangle,
    diamond: PptxShapes.diamond,
    trapezoid: PptxShapes.trapezoid,
    parallelogram: PptxShapes.parallelogram,
    pentagon: PptxShapes.pentagon,
    hexagon: PptxShapes.hexagon,
    octagon: PptxShapes.octagon,
    star: PptxShapes.star5,
    star4: PptxShapes.star4,
    star5: PptxShapes.star5,
    star6: PptxShapes.star6,
    line: PptxShapes.line,
    arrow: PptxShapes.rightArrow,
    rightarrow: PptxShapes.rightArrow,
    leftarrow: PptxShapes.leftArrow,
    cloud: PptxShapes.cloud,
    heart: PptxShapes.heart,
  };

  return shapeMap[name] ?? PptxShapes.rect;
}

/**
 * Map a chart type string to PptxGenJS chart type enum.
 */
function mapChartType(content: string): PptxGenJS.CHART_NAME {
  const name = content.toLowerCase().trim();
  const chartMap: Record<string, PptxGenJS.CHART_NAME> = {
    bar: PptxGenJS.ChartType.bar,
    line: PptxGenJS.ChartType.line,
    pie: PptxGenJS.ChartType.pie,
    doughnut: PptxGenJS.ChartType.doughnut,
    area: PptxGenJS.ChartType.area,
    scatter: PptxGenJS.ChartType.scatter,
    radar: PptxGenJS.ChartType.radar,
  };
  return chartMap[name] ?? PptxGenJS.ChartType.bar;
}

/**
 * Parse chart data from an element's content or style.
 * Expects JSON-encoded data in el.content with shape:
 * { labels: string[], series: { name: string, values: number[] }[] }
 */
function parseChartData(
  el: MAICSlideElement,
): { chartType: PptxGenJS.CHART_NAME; data: PptxGenJS.OptsChartData[] } | null {
  try {
    const parsed = JSON.parse(el.content);
    const chartType = mapChartType(parsed.chartType ?? parsed.type ?? 'bar');

    const data: PptxGenJS.OptsChartData[] = (parsed.series ?? []).map(
      (s: { name?: string; values?: number[] }) => ({
        name: s.name ?? 'Series',
        labels: parsed.labels ?? [],
        values: s.values ?? [],
      }),
    );

    if (data.length === 0) return null;
    return { chartType, data };
  } catch {
    return null;
  }
}

/**
 * Parse table data from an element's content.
 * Expects JSON-encoded data in el.content with shape:
 * { headers?: string[], rows: string[][] }
 */
function parseTableData(el: MAICSlideElement): PptxGenJS.TableRow[] | null {
  try {
    const parsed = JSON.parse(el.content);
    const rows: PptxGenJS.TableRow[] = [];

    if (parsed.headers && Array.isArray(parsed.headers)) {
      rows.push(
        parsed.headers.map((h: string) => ({
          text: h,
          options: { bold: true, fill: { color: 'E2E8F0' } },
        })),
      );
    }

    if (parsed.rows && Array.isArray(parsed.rows)) {
      for (const row of parsed.rows) {
        rows.push(
          (row as string[]).map((cell) => ({
            text: String(cell),
          })),
        );
      }
    }

    return rows.length > 0 ? rows : null;
  } catch {
    return null;
  }
}

export function useExportPptx(): UseExportPptxReturn {
  const [isExporting, setIsExporting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const exportPptx = useCallback(async (classroomTitle?: string) => {
    const slides = useMAICStageStore.getState().slides;
    const agents = useMAICStageStore.getState().agents;

    if (slides.length === 0) {
      setError('No slides to export.');
      return;
    }

    setIsExporting(true);
    setProgress(0);
    setError(null);

    try {
      const pptx = new PptxGenJS();

      // Presentation metadata
      const title = classroomTitle || 'AI Classroom';
      pptx.title = title;
      pptx.author = 'LearnPuddle AI Classroom';
      pptx.layout = 'LAYOUT_WIDE';

      // Add agent info as a custom property in the subject field
      if (agents.length > 0) {
        pptx.subject = `Agents: ${agents.map((a) => a.name).join(', ')}`;
      }

      for (let i = 0; i < slides.length; i++) {
        const slideData = slides[i];
        const pptxSlide = pptx.addSlide();

        // Background
        if (slideData.background) {
          const bg = slideData.background;
          if (bg.startsWith('#') || /^[0-9a-fA-F]{6}$/.test(bg)) {
            pptxSlide.background = { fill: bg.replace('#', '') };
          } else if (bg.startsWith('http') || bg.startsWith('data:')) {
            pptxSlide.background = { path: bg };
          } else {
            pptxSlide.background = { fill: bg.replace('#', '') };
          }
        }

        // Slide title
        if (slideData.title) {
          pptxSlide.addText(slideData.title, {
            x: 0.5,
            y: 0.2,
            w: SLIDE_WIDTH - 1,
            h: 0.6,
            fontSize: 24,
            bold: true,
            color: '333333',
          });
        }

        // Process elements
        for (const el of slideData.elements) {
          switch (el.type) {
            case 'text': {
              const textOpts = buildTextOptions(el);
              pptxSlide.addText(el.content, textOpts);
              break;
            }

            case 'image': {
              const imgSrc = el.src || el.content;
              if (imgSrc) {
                const imgOpts: PptxGenJS.ImageProps = {
                  x: pctToInchesX(el.x),
                  y: pctToInchesY(el.y),
                  w: pctToInchesX(el.width),
                  h: pctToInchesY(el.height),
                };
                if (imgSrc.startsWith('data:')) {
                  imgOpts.data = imgSrc;
                } else {
                  imgOpts.path = imgSrc;
                }
                try {
                  pptxSlide.addImage(imgOpts);
                } catch {
                  // Skip images that fail to load
                  console.warn(`Skipping image element ${el.id}: failed to embed`);
                }
              }
              break;
            }

            case 'shape': {
              const shapeType = mapShapeType(el.content);
              const style = el.style ?? {};
              pptxSlide.addShape(shapeType, {
                x: pctToInchesX(el.x),
                y: pctToInchesY(el.y),
                w: pctToInchesX(el.width),
                h: pctToInchesY(el.height),
                fill: style.fill
                  ? { color: String(style.fill).replace('#', '') }
                  : undefined,
                line: style.stroke
                  ? {
                      color: String(style.stroke).replace('#', ''),
                      width: Number(style.strokeWidth ?? 1),
                    }
                  : undefined,
              });
              break;
            }

            case 'chart': {
              const chartInfo = parseChartData(el);
              if (chartInfo) {
                pptxSlide.addChart(chartInfo.chartType, chartInfo.data, {
                  x: pctToInchesX(el.x),
                  y: pctToInchesY(el.y),
                  w: pctToInchesX(el.width),
                  h: pctToInchesY(el.height),
                  showLegend: true,
                  showTitle: false,
                });
              }
              break;
            }

            case 'table': {
              const tableRows = parseTableData(el);
              if (tableRows) {
                pptxSlide.addTable(tableRows, {
                  x: pctToInchesX(el.x),
                  y: pctToInchesY(el.y),
                  w: pctToInchesX(el.width),
                  border: { type: 'solid', pt: 0.5, color: 'CCCCCC' },
                  fontSize: 10,
                  autoPage: false,
                });
              }
              break;
            }

            case 'code': {
              pptxSlide.addText(el.content, {
                x: pctToInchesX(el.x),
                y: pctToInchesY(el.y),
                w: pctToInchesX(el.width),
                h: pctToInchesY(el.height),
                fontFace: 'Courier New',
                fontSize: 10,
                color: 'E2E8F0',
                fill: { color: '1E293B' },
                valign: 'top',
                paraSpaceBefore: 4,
                paraSpaceAfter: 4,
              });
              break;
            }

            case 'latex': {
              // LaTeX cannot be natively rendered in PPTX; export as plain text
              pptxSlide.addText(el.content, {
                x: pctToInchesX(el.x),
                y: pctToInchesY(el.y),
                w: pctToInchesX(el.width),
                h: pctToInchesY(el.height),
                fontFace: 'Cambria Math',
                fontSize: 14,
                italic: true,
                color: '333333',
              });
              break;
            }

            case 'video': {
              // Video can't be embedded inline; add a placeholder with link
              const videoSrc = el.src || el.content;
              pptxSlide.addText(`[Video: ${videoSrc}]`, {
                x: pctToInchesX(el.x),
                y: pctToInchesY(el.y),
                w: pctToInchesX(el.width),
                h: pctToInchesY(el.height),
                fontSize: 12,
                color: '6366F1',
                italic: true,
                align: 'center',
                valign: 'middle',
                fill: { color: 'F1F5F9' },
                hyperlink: videoSrc?.startsWith('http')
                  ? { url: videoSrc }
                  : undefined,
              });
              break;
            }

            default:
              break;
          }
        }

        // Speaker notes
        if (slideData.speakerScript) {
          pptxSlide.addNotes(slideData.speakerScript);
        } else if (slideData.notes) {
          pptxSlide.addNotes(slideData.notes);
        }

        // Update progress
        setProgress(Math.round(((i + 1) / slides.length) * 100));

        // Yield to main thread to keep UI responsive
        if (i % 5 === 0) {
          await new Promise((resolve) => setTimeout(resolve, 0));
        }
      }

      // Generate and download
      const fileName = `${title.replace(/[^a-zA-Z0-9 ]/g, '').trim() || 'classroom'}-classroom.pptx`;
      await pptx.writeFile({ fileName });

      setProgress(100);
    } catch (err) {
      console.error('PPTX export failed:', err);
      setError(err instanceof Error ? err.message : 'Export failed');
    } finally {
      setIsExporting(false);
    }
  }, []);

  return { exportPptx, isExporting, progress, error };
}
