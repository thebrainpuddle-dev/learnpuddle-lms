import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeMouseHandler,
  Panel,
  Handle,
  Position,
  MarkerType,
  BackgroundVariant,
} from '@xyflow/react';
import dagre from '@dagrejs/dagre';
import { Maximize2, Minimize2, Info, GitBranch } from 'lucide-react';
import '@xyflow/react/dist/style.css';
import type { MindMapData, MindMapNode as MindMapNodeType } from '../../types/studySummary';
import { cn } from '../../lib/utils';

// ─── Node dimension map ──────────────────────────────────────────────────────

const NODE_DIMENSIONS: Record<string, { width: number; height: number }> = {
  core: { width: 160, height: 60 },
  concept: { width: 140, height: 50 },
  process: { width: 140, height: 50 },
  detail: { width: 120, height: 44 },
};

// ─── Node style map ─────────────────────────────────────────────────────────

const NODE_STYLES: Record<string, string> = {
  core: 'bg-indigo-600 text-white rounded-xl shadow-lg border-0',
  concept: 'bg-white border-2 border-indigo-500 text-indigo-700 rounded-lg shadow-sm',
  process: 'bg-purple-50 border border-purple-500 text-purple-700 rounded-lg shadow-sm',
  detail: 'bg-gray-50 border border-gray-300 text-gray-600 rounded-md shadow-sm',
};

const NODE_TYPE_LABELS: Record<string, string> = {
  core: 'Core Concept',
  concept: 'Concept',
  process: 'Process',
  detail: 'Detail',
};

// ─── Dagre layout helper ────────────────────────────────────────────────────

function getLayoutedElements(
  rawNodes: Node[],
  rawEdges: Edge[],
): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'TB', nodesep: 80, ranksep: 100 });

  rawNodes.forEach((node) => {
    const dim = NODE_DIMENSIONS[(node.data as Record<string, unknown>).nodeType as string] || NODE_DIMENSIONS.detail;
    g.setNode(node.id, { width: dim.width, height: dim.height });
  });

  rawEdges.forEach((edge) => {
    g.setEdge(edge.source, edge.target);
  });

  dagre.layout(g);

  const layoutedNodes = rawNodes.map((node) => {
    const pos = g.node(node.id);
    const dim = NODE_DIMENSIONS[(node.data as Record<string, unknown>).nodeType as string] || NODE_DIMENSIONS.detail;
    return {
      ...node,
      position: {
        x: pos.x - dim.width / 2,
        y: pos.y - dim.height / 2,
      },
    };
  });

  return { nodes: layoutedNodes, edges: rawEdges };
}

// ─── Custom node component ──────────────────────────────────────────────────

function MindMapCustomNode({ data }: { data: Record<string, unknown> }) {
  const nodeType = (data.nodeType as string) || 'detail';
  const label = (data.label as string) || '';
  const styleClass = NODE_STYLES[nodeType] || NODE_STYLES.detail;
  const dim = NODE_DIMENSIONS[nodeType] || NODE_DIMENSIONS.detail;

  return (
    <div
      className={cn(
        'flex items-center justify-center px-3 py-2 text-center cursor-pointer transition-all duration-200 hover:scale-105 hover:shadow-md',
        styleClass,
      )}
      style={{ width: dim.width, height: dim.height }}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!w-2 !h-2 !bg-transparent !border-0"
      />
      <span
        className={cn(
          'font-medium leading-tight line-clamp-2',
          nodeType === 'core' ? 'text-sm' : 'text-xs',
        )}
      >
        {label}
      </span>
      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-2 !h-2 !bg-transparent !border-0"
      />
    </div>
  );
}

const nodeTypes = {
  mindMapNode: MindMapCustomNode,
};

// ─── Props ──────────────────────────────────────────────────────────────────

interface MindMapTabProps {
  data: MindMapData;
}

// ─── Component ──────────────────────────────────────────────────────────────

export function MindMapTab({ data }: MindMapTabProps) {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  // Build React Flow nodes/edges from data
  const { initialNodes, initialEdges } = useMemo(() => {
    if (!data.nodes?.length) {
      return { initialNodes: [], initialEdges: [] };
    }

    const rfNodes: Node[] = data.nodes.map((n) => ({
      id: n.id,
      type: 'mindMapNode',
      data: {
        label: n.label,
        nodeType: n.type,
        description: n.description,
      },
      position: { x: 0, y: 0 },
    }));

    const rfEdges: Edge[] = data.edges.map((e, idx) => ({
      id: `edge-${idx}`,
      source: e.source,
      target: e.target,
      label: e.label || undefined,
      animated: false,
      style: { stroke: '#818cf8', strokeWidth: 2.5 },
      labelStyle: { fill: '#4338ca', fontSize: 10, fontWeight: 600 },
      labelBgStyle: { fill: '#eef2ff', fillOpacity: 0.95 },
      labelBgPadding: [6, 3] as [number, number],
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: '#818cf8',
        width: 18,
        height: 18,
      },
    }));

    const layouted = getLayoutedElements(rfNodes, rfEdges);
    return { initialNodes: layouted.nodes, initialEdges: layouted.edges };
  }, [data]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Sync when data changes
  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [initialNodes, initialEdges, setNodes, setEdges]);

  const onNodeClick: NodeMouseHandler = useCallback((_event, node) => {
    setSelectedNodeId((prev) => (prev === node.id ? null : node.id));
  }, []);

  // Selected node info
  const selectedNodeData = useMemo(() => {
    if (!selectedNodeId) return null;
    const node = data.nodes.find((n) => n.id === selectedNodeId);
    if (!node) return null;

    const connectedEdges = data.edges.filter(
      (e) => e.source === selectedNodeId || e.target === selectedNodeId,
    );
    const connectedLabels = connectedEdges.map((e) => {
      const otherId = e.source === selectedNodeId ? e.target : e.source;
      const otherNode = data.nodes.find((n) => n.id === otherId);
      return {
        label: otherNode?.label || otherId,
        edgeLabel: e.label,
        direction: e.source === selectedNodeId ? 'outgoing' : 'incoming',
      };
    });

    return { ...node, connections: connectedLabels };
  }, [selectedNodeId, data]);

  // Empty state
  if (!data.nodes?.length) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <div className="h-12 w-12 rounded-xl bg-gray-100 flex items-center justify-center mb-3">
          <GitBranch className="h-6 w-6 text-gray-400" />
        </div>
        <p className="text-sm font-medium text-gray-500 mb-1">No mind map available</p>
        <p className="text-xs text-gray-400">
          Mind map data was not generated for this content
        </p>
      </div>
    );
  }

  const flowContent = (
    <div className={cn('w-full', isFullscreen ? 'h-full' : 'h-[450px]')}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.3}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="#e5e7eb" />
        <Controls showInteractive={false} />
        <MiniMap
          nodeColor={(node) => {
            const nt = (node.data as Record<string, unknown>).nodeType as string;
            if (nt === 'core') return '#4f46e5';
            if (nt === 'concept') return '#6366f1';
            if (nt === 'process') return '#a855f7';
            return '#d1d5db';
          }}
          maskColor="rgba(255,255,255,0.7)"
          style={{ bottom: 12, right: 12, borderRadius: 8 }}
        />
        <Panel position="top-right">
          <button
            onClick={() => setIsFullscreen((f) => !f)}
            className="p-2 bg-white rounded-lg border border-gray-200 shadow-sm hover:bg-gray-50 transition-colors"
            title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
          >
            {isFullscreen ? (
              <Minimize2 className="h-4 w-4 text-gray-600" />
            ) : (
              <Maximize2 className="h-4 w-4 text-gray-600" />
            )}
          </button>
        </Panel>
        <Panel position="bottom-left">
          <div className="bg-white/95 backdrop-blur-sm rounded-lg border border-gray-200 shadow-sm px-3 py-2 text-[10px] space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded bg-indigo-600 flex-shrink-0" />
              <span className="text-gray-600 font-medium">Core Concept</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded border-2 border-indigo-500 bg-white flex-shrink-0" />
              <span className="text-gray-600 font-medium">Concept</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded border border-purple-500 bg-purple-50 flex-shrink-0" />
              <span className="text-gray-600 font-medium">Process</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded border border-gray-300 bg-gray-50 flex-shrink-0" />
              <span className="text-gray-600 font-medium">Detail</span>
            </div>
          </div>
        </Panel>
      </ReactFlow>
    </div>
  );

  const infoPanel = selectedNodeData && (
    <div className="border-t border-gray-100 px-4 py-3 bg-gray-50/50">
      <div className="flex items-start gap-3">
        <div className="p-1.5 bg-indigo-100 rounded-md flex-shrink-0 mt-0.5">
          <Info className="h-3.5 w-3.5 text-indigo-600" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h4 className="text-sm font-semibold text-gray-900">
              {selectedNodeData.label}
            </h4>
            <span
              className={cn(
                'text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded',
                selectedNodeData.type === 'core' && 'bg-indigo-100 text-indigo-700',
                selectedNodeData.type === 'concept' && 'bg-indigo-50 text-indigo-600',
                selectedNodeData.type === 'process' && 'bg-purple-50 text-purple-600',
                selectedNodeData.type === 'detail' && 'bg-gray-100 text-gray-500',
              )}
            >
              {NODE_TYPE_LABELS[selectedNodeData.type] || selectedNodeData.type}
            </span>
          </div>
          {selectedNodeData.description && (
            <p className="text-xs text-gray-600 leading-relaxed mb-2">
              {selectedNodeData.description}
            </p>
          )}
          {selectedNodeData.connections.length > 0 && (
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400 mb-1">
                Connected Concepts
              </p>
              <div className="flex flex-wrap gap-1.5">
                {selectedNodeData.connections.map((conn, i) => (
                  <span
                    key={i}
                    className="inline-flex items-center gap-1 text-[11px] text-gray-500 bg-white border border-gray-200 rounded px-2 py-0.5"
                  >
                    <span className={cn(
                      'text-[9px]',
                      conn.direction === 'outgoing' ? 'text-indigo-400' : 'text-gray-400',
                    )}>
                      {conn.direction === 'outgoing' ? '\u2192' : '\u2190'}
                    </span>
                    {conn.label}
                    {conn.edgeLabel && (
                      <span className="text-gray-400">({conn.edgeLabel})</span>
                    )}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
        <button
          onClick={() => setSelectedNodeId(null)}
          className="text-gray-400 hover:text-gray-600 p-0.5 flex-shrink-0"
        >
          <span className="sr-only">Close</span>
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>
  );

  // Fullscreen mode
  if (isFullscreen) {
    return (
      <div className="fixed inset-0 z-50 bg-white flex flex-col">
        {flowContent}
        {infoPanel}
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-gray-200 overflow-hidden">
      {flowContent}
      {infoPanel}
    </div>
  );
}
