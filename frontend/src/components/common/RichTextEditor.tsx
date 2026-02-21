import React from 'react';
import { EditorContent, useEditor, type JSONContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Underline from '@tiptap/extension-underline';
import Link from '@tiptap/extension-link';
import Image from '@tiptap/extension-image';
import Subscript from '@tiptap/extension-subscript';
import Superscript from '@tiptap/extension-superscript';
import { TextStyle } from '@tiptap/extension-text-style';
import Placeholder from '@tiptap/extension-placeholder';
import { Extension } from '@tiptap/core';
import { Markdown } from '@tiptap/markdown';
import CodeBlockLowlight from '@tiptap/extension-code-block-lowlight';
import { createLowlight } from 'lowlight';
import {
  PhotoIcon,
  LinkIcon,
  ListBulletIcon,
  CodeBracketIcon,
  ArrowUturnLeftIcon,
  ArrowUturnRightIcon,
} from '@heroicons/react/24/outline';

const lowlight = createLowlight();

type EditorMode = 'WYSIWYG' | 'MARKDOWN';

interface UploadResult {
  src: string;
  imageId?: string;
}

interface RichTextEditorProps {
  value: string;
  onChange: (html: string) => void;
  mode: EditorMode;
  onModeChange: (mode: EditorMode) => void;
  onImageUpload?: (file: File) => Promise<UploadResult>;
  placeholder?: string;
  minHeightClassName?: string;
  disabled?: boolean;
  onModeWarning?: (message: string) => void;
}

const FONT_SIZES = ['12px', '14px', '16px', '18px', '24px', '32px'];

const FontSize = Extension.create({
  name: 'fontSize',
  addOptions() {
    return {
      types: ['textStyle'],
    };
  },
  addGlobalAttributes() {
    return [
      {
        types: this.options.types,
        attributes: {
          fontSize: {
            default: null,
            parseHTML: (element: HTMLElement) => element.style.fontSize || null,
            renderHTML: (attributes: Record<string, string>) => {
              if (!attributes.fontSize) {
                return {};
              }
              return { style: `font-size: ${attributes.fontSize}` };
            },
          },
        },
      },
    ];
  },
  addCommands() {
    return {
      setFontSize:
        (fontSize: string) =>
        ({ chain }: { chain: () => any }) =>
          chain().setMark('textStyle', { fontSize }).run(),
      unsetFontSize:
        () =>
        ({ chain }: { chain: () => any }) =>
          chain().setMark('textStyle', { fontSize: null }).removeEmptyTextStyle().run(),
    } as any;
  },
});

const Indent = Extension.create({
  name: 'indent',
  addOptions() {
    return {
      types: ['paragraph', 'heading'],
      minLevel: 0,
      maxLevel: 8,
    };
  },
  addGlobalAttributes() {
    return [
      {
        types: this.options.types,
        attributes: {
          indent: {
            default: 0,
            parseHTML: (element: HTMLElement) => {
              const marginLeft = element.style.marginLeft || '0';
              const parsed = parseInt(marginLeft.replace('em', ''), 10);
              return Number.isFinite(parsed) ? Math.max(0, parsed) : 0;
            },
            renderHTML: (attributes: Record<string, number>) => {
              const level = Number(attributes.indent || 0);
              if (!level) return {};
              return { style: `margin-left: ${level}em` };
            },
          },
        },
      },
    ];
  },
  addCommands() {
    const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

    const updateCurrentNodeIndent = (editor: any, delta: number, minLevel: number, maxLevel: number) => {
      const attrs = editor.getAttributes('paragraph');
      const paragraphIndent = Number(attrs.indent || 0);
      const headingAttrs = editor.getAttributes('heading');
      const headingIndent = Number(headingAttrs.indent || 0);
      const current = editor.isActive('heading') ? headingIndent : paragraphIndent;
      const next = clamp(current + delta, minLevel, maxLevel);
      if (editor.isActive('heading')) {
        return editor.chain().focus().updateAttributes('heading', { indent: next }).run();
      }
      return editor.chain().focus().updateAttributes('paragraph', { indent: next }).run();
    };

    return {
      increaseIndent:
        () =>
        ({ editor }: { editor: any }) =>
          updateCurrentNodeIndent(editor, 1, this.options.minLevel, this.options.maxLevel),
      decreaseIndent:
        () =>
        ({ editor }: { editor: any }) =>
          updateCurrentNodeIndent(editor, -1, this.options.minLevel, this.options.maxLevel),
    } as any;
  },
});

const RichImage = Image.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      imageId: {
        default: null,
        parseHTML: (element: HTMLElement) => element.getAttribute('data-image-id'),
        renderHTML: (attributes: Record<string, string>) => {
          if (!attributes.imageId) {
            return {};
          }
          return {
            'data-image-id': attributes.imageId,
          };
        },
      },
    };
  },
});

function containsAdvancedFormatting(html: string) {
  return /<sub|<sup|font-size|margin-left|<img/i.test(html || '');
}

export const RichTextEditor: React.FC<RichTextEditorProps> = ({
  value,
  onChange,
  mode,
  onModeChange,
  onImageUpload,
  placeholder = 'Start writing...',
  minHeightClassName = 'min-h-[220px]',
  disabled = false,
  onModeWarning,
}) => {
  const fileInputRef = React.useRef<HTMLInputElement | null>(null);
  const [markdownDraft, setMarkdownDraft] = React.useState('');

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        codeBlock: false,
      }),
      CodeBlockLowlight.configure({ lowlight }),
      Underline,
      Link.configure({
        openOnClick: false,
        autolink: true,
      }),
      Subscript,
      Superscript,
      TextStyle,
      FontSize,
      Indent,
      Placeholder.configure({ placeholder }),
      Markdown,
      RichImage,
    ],
    content: value || '',
    editable: !disabled,
    onUpdate: ({ editor: updatedEditor }) => {
      const html = updatedEditor.getHTML();
      onChange(html);
      const storage = (updatedEditor as any).storage?.markdown;
      if (storage?.getMarkdown) {
        setMarkdownDraft(storage.getMarkdown());
      }
    },
  });

  React.useEffect(() => {
    if (!editor) return;
    const current = editor.getHTML();
    if ((value || '') !== current) {
      editor.commands.setContent(value || '', { emitUpdate: false });
    }
  }, [editor, value]);

  React.useEffect(() => {
    if (!editor) return;
    const storage = (editor as any).storage?.markdown;
    if (storage?.getMarkdown) {
      setMarkdownDraft(storage.getMarkdown());
    }
  }, [editor]);

  const setMarkdownContent = React.useCallback(
    (md: string) => {
      if (!editor) return;
      try {
        (editor.commands as any).setContent(md, { contentType: 'markdown', emitUpdate: true });
      } catch {
        // Fallback to plain text paragraph if markdown parser isn't available.
        editor.commands.setContent(
          { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: md }] }] } as JSONContent,
          { emitUpdate: true }
        );
      }
    },
    [editor]
  );

  const handleModeSwitch = (nextMode: EditorMode) => {
    if (!editor || nextMode === mode) return;

    if (nextMode === 'MARKDOWN') {
      const html = editor.getHTML();
      if (containsAdvancedFormatting(html)) {
        onModeWarning?.('Some rich formatting may not be fully represented in Markdown mode.');
      }
      const storage = (editor as any).storage?.markdown;
      if (storage?.getMarkdown) {
        setMarkdownDraft(storage.getMarkdown());
      }
    }

    if (nextMode === 'WYSIWYG' && markdownDraft) {
      setMarkdownContent(markdownDraft);
    }

    onModeChange(nextMode);
  };

  const applyFileUpload = async (file: File) => {
    if (!editor || !onImageUpload) return;
    const uploaded = await onImageUpload(file);
    if (!uploaded?.src) return;
    const chain = editor.chain().focus();
    (chain as any).setImage({ src: uploaded.src, imageId: uploaded.imageId || null });
    chain.run();
  };

  const withFocus = (cb: (chain: any) => any) => {
    if (!editor) return;
    cb(editor.chain().focus()).run();
  };

  return (
    <div className="border border-gray-300 rounded-lg bg-white overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b border-gray-200 px-3 py-2 bg-gray-50">
        <select
          value={mode}
          onChange={(e) => handleModeSwitch(e.target.value as EditorMode)}
          className="text-xs border border-gray-300 rounded-md px-2 py-1"
          disabled={disabled}
        >
          <option value="WYSIWYG">WYSIWYG</option>
          <option value="MARKDOWN">Markdown</option>
        </select>

        {mode === 'WYSIWYG' && (
          <>
            <button type="button" onClick={() => withFocus((c) => c.toggleBold())} className="px-2 py-1 text-sm border rounded hover:bg-gray-100">B</button>
            <button type="button" onClick={() => withFocus((c) => c.toggleItalic())} className="px-2 py-1 text-sm border rounded hover:bg-gray-100 italic">I</button>
            <button type="button" onClick={() => withFocus((c) => c.toggleUnderline())} className="px-2 py-1 text-sm border rounded hover:bg-gray-100 underline">U</button>
            <button type="button" onClick={() => withFocus((c) => c.toggleSubscript())} className="px-2 py-1 text-xs border rounded hover:bg-gray-100">x₂</button>
            <button type="button" onClick={() => withFocus((c) => c.toggleSuperscript())} className="px-2 py-1 text-xs border rounded hover:bg-gray-100">x²</button>

            <select
              onChange={(e) => {
                if (!editor) return;
                if (!e.target.value) {
                  (editor.chain().focus() as any).unsetFontSize().run();
                  return;
                }
                (editor.chain().focus() as any).setFontSize(e.target.value).run();
              }}
              className="text-xs border border-gray-300 rounded-md px-2 py-1"
              defaultValue=""
              disabled={disabled}
            >
              <option value="">Font size</option>
              {FONT_SIZES.map((size) => (
                <option key={size} value={size}>{size}</option>
              ))}
            </select>

            <button type="button" onClick={() => withFocus((c) => c.increaseIndent())} className="p-1.5 border rounded hover:bg-gray-100" title="Indent">
              <ArrowUturnRightIcon className="h-4 w-4" />
            </button>
            <button type="button" onClick={() => withFocus((c) => c.decreaseIndent())} className="p-1.5 border rounded hover:bg-gray-100" title="Outdent">
              <ArrowUturnLeftIcon className="h-4 w-4" />
            </button>
            <button type="button" onClick={() => withFocus((c) => c.toggleBulletList())} className="p-1.5 border rounded hover:bg-gray-100" title="Bullet list">
              <ListBulletIcon className="h-4 w-4" />
            </button>
            <button type="button" onClick={() => withFocus((c) => c.toggleCodeBlock())} className="p-1.5 border rounded hover:bg-gray-100" title="Code block">
              <CodeBracketIcon className="h-4 w-4" />
            </button>

            <button
              type="button"
              onClick={() => {
                if (!editor) return;
                const href = window.prompt('Enter URL');
                if (!href) return;
                editor.chain().focus().extendMarkRange('link').setLink({ href, target: '_blank', rel: 'noopener noreferrer' }).run();
              }}
              className="p-1.5 border rounded hover:bg-gray-100"
              title="Insert link"
            >
              <LinkIcon className="h-4 w-4" />
            </button>

            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="p-1.5 border rounded hover:bg-gray-100"
              title="Upload image"
              disabled={disabled || !onImageUpload}
            >
              <PhotoIcon className="h-4 w-4" />
            </button>

            <button
              type="button"
              onClick={() => {
                if (!editor) return;
                editor.chain().focus().unsetAllMarks().clearNodes().run();
              }}
              className="px-2 py-1 text-xs border rounded hover:bg-gray-100"
            >
              Clear
            </button>
          </>
        )}

        <input
          ref={fileInputRef}
          type="file"
          accept="image/png,image/jpeg,image/jpg,image/gif,image/webp"
          className="hidden"
          onChange={async (e) => {
            const file = e.target.files?.[0];
            if (!file) return;
            await applyFileUpload(file);
            e.target.value = '';
          }}
        />
      </div>

      {mode === 'MARKDOWN' ? (
        <textarea
          value={markdownDraft}
          onChange={(e) => {
            setMarkdownDraft(e.target.value);
            setMarkdownContent(e.target.value);
          }}
          placeholder={placeholder}
          className={`w-full ${minHeightClassName} p-3 font-mono text-sm focus:outline-none`}
          disabled={disabled}
        />
      ) : (
        <EditorContent editor={editor} className={`prose prose-sm max-w-none ${minHeightClassName} p-3`} />
      )}
    </div>
  );
};
