// src/components/versioning/JsonDiffView.tsx
//
// Lightweight recursive JSON diff viewer. Compares two unknown JSON values
// and highlights added (green), removed (red), and changed (amber) keys.
//
// Design constraints:
//  - No third-party diff library.
//  - Handles nested objects and arrays.
//  - Order-insensitive when rendering object keys (keys are sorted).
//  - Reusable for TASK-051 template preview.

import React from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type DiffKind = 'added' | 'removed' | 'changed' | 'unchanged' | 'nested';

interface DiffNode {
  key: string;
  kind: DiffKind;
  /** Value shown on the left (old) side — undefined when purely added. */
  oldValue?: unknown;
  /** Value shown on the right (new) side — undefined when purely removed. */
  newValue?: unknown;
  /** Recursively computed children for objects / arrays. */
  children?: DiffNode[];
}

// ---------------------------------------------------------------------------
// Diff computation
// ---------------------------------------------------------------------------

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function diffValues(key: string, oldVal: unknown, newVal: unknown): DiffNode {
  if (isPlainObject(oldVal) && isPlainObject(newVal)) {
    const children = diffObjects(oldVal, newVal);
    const hasChanges = children.some((c) => c.kind !== 'unchanged');
    return { key, kind: hasChanges ? 'nested' : 'unchanged', children };
  }

  if (Array.isArray(oldVal) && Array.isArray(newVal)) {
    // Diff arrays element-by-element by index.
    const len = Math.max(oldVal.length, newVal.length);
    const children: DiffNode[] = [];
    for (let i = 0; i < len; i++) {
      if (i >= oldVal.length) {
        children.push({ key: String(i), kind: 'added', newValue: newVal[i] });
      } else if (i >= newVal.length) {
        children.push({ key: String(i), kind: 'removed', oldValue: oldVal[i] });
      } else {
        children.push(diffValues(String(i), oldVal[i], newVal[i]));
      }
    }
    const hasChanges = children.some((c) => c.kind !== 'unchanged');
    return { key, kind: hasChanges ? 'nested' : 'unchanged', children };
  }

  if (oldVal === newVal) {
    return { key, kind: 'unchanged', oldValue: oldVal, newValue: newVal };
  }

  return { key, kind: 'changed', oldValue: oldVal, newValue: newVal };
}

function diffObjects(
  oldObj: Record<string, unknown>,
  newObj: Record<string, unknown>,
): DiffNode[] {
  const allKeys = Array.from(new Set([...Object.keys(oldObj), ...Object.keys(newObj)])).sort();
  return allKeys.map((k) => {
    if (!(k in oldObj)) {
      return { key: k, kind: 'added' as DiffKind, newValue: newObj[k] };
    }
    if (!(k in newObj)) {
      return { key: k, kind: 'removed' as DiffKind, oldValue: oldObj[k] };
    }
    return diffValues(k, oldObj[k], newObj[k]);
  });
}

function computeDiff(oldVal: unknown, newVal: unknown): DiffNode[] {
  // When there is no prior snapshot (first revision / undefined old), show
  // every key in newVal as "added".
  if ((oldVal === undefined || oldVal === null) && isPlainObject(newVal)) {
    return diffObjects({}, newVal);
  }
  if (isPlainObject(oldVal) && isPlainObject(newVal)) {
    return diffObjects(oldVal, newVal);
  }
  // Scalar or array at root — wrap in a single node.
  const node = diffValues('(root)', oldVal, newVal);
  return [node];
}

// ---------------------------------------------------------------------------
// Rendering helpers
// ---------------------------------------------------------------------------

function formatPrimitive(v: unknown): string {
  if (v === null) return 'null';
  if (v === undefined) return 'undefined';
  if (typeof v === 'string') return `"${v}"`;
  return String(v);
}

function renderValue(v: unknown): React.ReactNode {
  if (Array.isArray(v)) {
    return <span className="text-gray-500">[{v.length} items]</span>;
  }
  if (isPlainObject(v)) {
    return <span className="text-gray-500">{'{'}{Object.keys(v).length} keys{'}'}</span>;
  }
  return <span>{formatPrimitive(v)}</span>;
}

// ---------------------------------------------------------------------------
// DiffRow — renders one node in the tree
// ---------------------------------------------------------------------------

interface DiffRowProps {
  node: DiffNode;
  depth: number;
}

const DiffRow: React.FC<DiffRowProps> = ({ node, depth }) => {
  const indent = depth * 16;

  if (node.kind === 'unchanged') {
    return (
      <div
        className="flex items-start gap-2 py-0.5 px-2 text-sm text-gray-500"
        style={{ paddingLeft: indent + 8 }}
      >
        <span className="font-mono font-medium text-gray-400 min-w-[120px] shrink-0">
          {node.key}:
        </span>
        <span className="font-mono">{renderValue(node.newValue)}</span>
      </div>
    );
  }

  if (node.kind === 'nested') {
    return (
      <div>
        <div
          className="flex items-center gap-1 py-0.5 px-2 text-sm font-medium text-gray-700"
          style={{ paddingLeft: indent + 8 }}
        >
          <span className="font-mono">{node.key}:</span>
        </div>
        {node.children?.map((child) => (
          <DiffRow key={child.key} node={child} depth={depth + 1} />
        ))}
      </div>
    );
  }

  if (node.kind === 'added') {
    return (
      <div
        className="flex items-start gap-2 py-0.5 px-2 text-sm bg-emerald-50 text-emerald-800"
        style={{ paddingLeft: indent + 8 }}
      >
        <span className="font-mono font-medium min-w-[120px] shrink-0 text-emerald-600">
          + {node.key}:
        </span>
        <span className="font-mono">{renderValue(node.newValue)}</span>
      </div>
    );
  }

  if (node.kind === 'removed') {
    return (
      <div
        className="flex items-start gap-2 py-0.5 px-2 text-sm bg-red-50 text-red-800"
        style={{ paddingLeft: indent + 8 }}
      >
        <span className="font-mono font-medium min-w-[120px] shrink-0 text-red-600">
          - {node.key}:
        </span>
        <span className="font-mono">{renderValue(node.oldValue)}</span>
      </div>
    );
  }

  // kind === 'changed'
  return (
    <div
      className="flex flex-col py-0.5 px-2 text-sm bg-amber-50"
      style={{ paddingLeft: indent + 8 }}
    >
      <div className="flex items-start gap-2">
        <span className="font-mono font-medium min-w-[120px] shrink-0 text-amber-700">
          ~ {node.key}:
        </span>
        <div className="flex flex-col gap-0.5">
          <span className="font-mono text-red-700 line-through">{renderValue(node.oldValue)}</span>
          <span className="font-mono text-emerald-700">{renderValue(node.newValue)}</span>
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Public component
// ---------------------------------------------------------------------------

export interface JsonDiffViewProps {
  /**
   * The "before" snapshot. Pass `undefined` when there is no previous state
   * (first revision — everything will be shown as "added").
   */
  oldValue: unknown;
  /**
   * The "after" snapshot (the selected revision being viewed).
   */
  newValue: unknown;
  /** Optional CSS class for the container. */
  className?: string;
}

export const JsonDiffView: React.FC<JsonDiffViewProps> = ({
  oldValue,
  newValue,
  className = '',
}) => {
  const nodes = computeDiff(oldValue, newValue);
  const hasChanges = nodes.some((n) => n.kind !== 'unchanged');

  return (
    <div
      className={`rounded-lg border border-gray-200 bg-white overflow-auto text-xs font-mono ${className}`}
      aria-label="JSON diff view"
    >
      {/* Legend */}
      <div className="flex items-center gap-4 px-3 py-2 border-b border-gray-100 text-xs text-gray-500 bg-gray-50">
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded-sm bg-emerald-100 border border-emerald-300" />
          Added
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded-sm bg-red-100 border border-red-300" />
          Removed
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded-sm bg-amber-100 border border-amber-300" />
          Changed
        </span>
      </div>

      {!hasChanges ? (
        <div className="px-4 py-6 text-center text-gray-400 text-sm">
          No differences — snapshot matches current state.
        </div>
      ) : (
        <div className="py-1">
          {nodes.map((node) => (
            <DiffRow key={node.key} node={node} depth={0} />
          ))}
        </div>
      )}
    </div>
  );
};
