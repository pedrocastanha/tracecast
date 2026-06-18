import { useMemo, useState } from "react";
import ReactFlow, {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  Position,
  MarkerType,
  Node,
  Edge,
  NodeProps,
} from "reactflow";
import dagre from "dagre";
import "reactflow/dist/style.css";

interface GraphNode {
  id: string;
  parent_span_id: string | null;
  name: string;
  type: string;
  status: string;
  model: string | null;
  primary_model: string | null;
  tokens_in: number;
  tokens_out: number;
  total_tokens: number;
  cost_usd: number;
  latency_ms: number | null;
  error: string | null;
}

interface GraphEdge {
  from: string;
  to: string;
  conditional?: boolean;
}

interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

const TYPE_COLOR: Record<string, string> = {
  llm: "#c8f751",   // signal lime
  tool: "#fbbf24",  // amber
  agent: "#a78bfa", // violet
};
const NODE_W = 216;
const NODE_H = 60;

function colorFor(n: { type: string; status: string }) {
  if (n.status === "error") return "#fb7185";
  return TYPE_COLOR[n.type] ?? "#5eead4";
}

function fmtMs(ms: number | null) {
  if (ms == null) return null;
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

// ── Custom node: type dot + name, then a dim metrics line ───────────────────
type NodeData = { name: string; type: string; status: string; color: string; meta: string; selected: boolean };

function SpanNode({ data }: NodeProps<NodeData>) {
  return (
    <div
      style={{
        width: NODE_W,
        boxSizing: "border-box",
        background: "var(--surface)",
        border: `1px solid ${data.selected ? data.color : "var(--border-strong)"}`,
        borderLeft: `3px solid ${data.color}`,
        borderRadius: 9,
        padding: "9px 12px",
        boxShadow: data.selected ? `0 0 0 1px ${data.color}, 0 6px 20px rgba(0,0,0,.45)` : "0 2px 8px rgba(0,0,0,.3)",
        transition: "border-color .12s ease, box-shadow .12s ease",
        cursor: "pointer",
      }}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0, width: 1, height: 1 }} />
      <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 3 }}>
        <span style={{ width: 7, height: 7, borderRadius: "50%", background: data.color, flexShrink: 0, boxShadow: `0 0 6px ${data.color}66` }} />
        <span
          style={{
            fontFamily: "var(--mono)",
            fontSize: 11.5,
            color: "var(--text)",
            fontWeight: 500,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
          title={data.name}
        >
          {data.name}
        </span>
      </div>
      <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text-faint)", letterSpacing: "-0.02em" }}>
        {data.meta || "—"}
      </div>
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0, width: 1, height: 1 }} />
    </div>
  );
}

const NODE_TYPES = { span: SpanNode };

// ── dagre top-down layout using traversal + nesting edges ───────────────────
function layout(nodes: GraphNode[], layoutEdges: Array<[string, string]>): Record<string, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "TB", nodesep: 26, ranksep: 66, marginx: 24, marginy: 24 });
  g.setDefaultEdgeLabel(() => ({}));
  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  const ids = new Set(nodes.map((n) => n.id));
  layoutEdges.forEach(([from, to]) => {
    if (ids.has(from) && ids.has(to) && from !== to) g.setEdge(from, to);
  });
  dagre.layout(g);
  const pos: Record<string, { x: number; y: number }> = {};
  nodes.forEach((n) => {
    const node = g.node(n.id);
    // dagre returns center coords; reactflow wants top-left
    pos[n.id] = node ? { x: node.x - NODE_W / 2, y: node.y - NODE_H / 2 } : { x: 0, y: 0 };
  });
  return pos;
}

// LangChain/LangGraph internal scaffolding filtered in simplified mode.
// llm spans are always hidden (both views) — their info surfaces on the parent via primary_model.
const INTERNAL_CHAIN_NAMES = new Set([
  "LangGraph", "RunnableSequence", "Prompt", "ChatPromptTemplate",
  "call_model", "should_continue", "agent",
  "tools",           // LangGraph tools-router wrapper, not the actual tool call
  "route_by_intent", // router output node, internal LangGraph scaffolding
]);

function simplifyNodes(nodes: GraphNode[]): GraphNode[] {
  return nodes.filter((n) => {
    if (n.type === "tool") return true;
    const shortName = n.name.split(":").pop() ?? n.name;
    return !INTERNAL_CHAIN_NAMES.has(shortName);
  });
}

function simplifyEdges(edges: GraphEdge[], visibleIds: Set<string>): GraphEdge[] {
  return edges.filter((e) => visibleIds.has(e.from) && visibleIds.has(e.to));
}

/** Walk parent_span_id chain upward to find the nearest visible ancestor. */
function nearestVisibleAncestor(
  nodeId: string | null,
  allNodeMap: Map<string, GraphNode>,
  visibleIds: Set<string>,
): string | null {
  if (!nodeId) return null;
  if (visibleIds.has(nodeId)) return nodeId;
  const node = allNodeMap.get(nodeId);
  if (!node || !node.parent_span_id) return null;
  return nearestVisibleAncestor(node.parent_span_id, allNodeMap, visibleIds);
}

export function TraceGraph({ data, onSelect }: { data: GraphData; onSelect: (id: string) => void }) {
  const [selected, setSelected] = useState<string | null>(null);
  const [simplified, setSimplified] = useState(false);

  const { nodes, edges } = useMemo(() => {
    const allNodeMap = new Map(data.nodes.map((n) => [n.id, n]));
    // llm spans always hidden — info shown via primary_model on parent card
    const nonLlmNodes = data.nodes.filter((n) => n.type !== "llm");
    const activeNodes = simplified ? simplifyNodes(nonLlmNodes) : nonLlmNodes;
    const visibleIds  = new Set(activeNodes.map((n) => n.id));
    const activeEdges = simplified ? simplifyEdges(data.edges, visibleIds) : data.edges;

    // Traversal flow comes from data.edges; nesting from parent_span_id.
    const traversalKeys = new Set(activeEdges.map((e) => `${e.from}->${e.to}`));

    // In simplified mode, bridge tool/agent nodes to their nearest visible ancestor
    // so tool spans that lost their direct parent (chain:tools) still connect properly.
    const parentEdges: Array<[string, string]> = [];
    for (const n of activeNodes) {
      if (!n.parent_span_id) continue;
      const from = simplified
        ? nearestVisibleAncestor(n.parent_span_id, allNodeMap, visibleIds)
        : (visibleIds.has(n.parent_span_id) ? n.parent_span_id : null);
      if (from && from !== n.id && !traversalKeys.has(`${from}->${n.id}`)) {
        parentEdges.push([from, n.id]);
      }
    }

    const layoutEdges: Array<[string, string]> = [
      ...activeEdges.map((e) => [e.from, e.to] as [string, string]),
      ...parentEdges,
    ];
    const pos = layout(activeNodes, layoutEdges);

    const rfNodes: Node[] = activeNodes.map((n) => {
      const color = colorFor(n);
      const metaParts = [
        n.primary_model ? `via ${n.primary_model}` : null,
        n.total_tokens ? `${n.total_tokens.toLocaleString()} tok` : null,
        n.cost_usd ? `$${n.cost_usd.toFixed(4)}` : null,
        fmtMs(n.latency_ms),
      ].filter(Boolean);
      return {
        id: n.id,
        type: "span",
        position: pos[n.id] ?? { x: 0, y: 0 },
        data: { name: n.name, type: n.type, status: n.status, color, meta: metaParts.join("  ·  "), selected: selected === n.id },
        draggable: true,
      };
    });

    // Traversal edges: solid lime arrows (animated when conditional).
    const flowEdges: Edge[] = activeEdges.map((e, i) => ({
      id: `t${i}`,
      source: e.from,
      target: e.to,
      type: "smoothstep",
      animated: !!e.conditional,
      markerEnd: { type: MarkerType.ArrowClosed, color: "#c8f751", width: 18, height: 18 },
      style: { stroke: "#c8f751", strokeWidth: 2, strokeDasharray: e.conditional ? "6 4" : undefined },
    }));

    // Nesting edges (parent → child not already a flow edge): dashed + faint.
    const nestEdges: Edge[] = parentEdges.map(([from, to], i) => ({
      id: `n${i}`,
      source: from,
      target: to,
      type: "smoothstep",
      markerEnd: { type: MarkerType.Arrow, color: "#565d70", width: 14, height: 14 },
      style: { stroke: "#565d70", strokeWidth: 1.2, strokeDasharray: "2 4", opacity: 0.7 },
    }));

    return { nodes: rfNodes, edges: [...nestEdges, ...flowEdges] };
  }, [data, selected, simplified]);

  return (
    <div style={{ height: 560, border: "1px solid var(--border)", borderRadius: "var(--radius)", background: "var(--bg-2)", overflow: "hidden" }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        fitView
        fitViewOptions={{ padding: 0.18 }}
        minZoom={0.2}
        onNodeClick={(_, node) => {
          setSelected(node.id);
          onSelect(node.id);
        }}
        onPaneClick={() => setSelected(null)}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#222734" />
        <Controls showInteractive={false} style={{ borderRadius: 8, overflow: "hidden", border: "1px solid var(--border)" }} />
        {/* Simplified toggle */}
        <button
          onClick={() => setSimplified((v) => !v)}
          style={{
            position: "absolute", left: 12, top: 12, zIndex: 5,
            padding: "5px 12px", borderRadius: 20,
            border: `1px solid ${simplified ? "var(--accent)" : "var(--border)"}`,
            background: simplified ? "rgba(200,247,81,.12)" : "rgba(19,22,30,.85)",
            color: simplified ? "var(--accent)" : "var(--text-muted)",
            fontFamily: "var(--mono)", fontSize: 10.5, cursor: "pointer",
            backdropFilter: "blur(4px)", transition: "all .15s ease",
          }}
        >
          {simplified ? "simplified" : "full"} view
        </button>

        {/* Legend */}
        <div style={{ position: "absolute", right: 12, top: 12, zIndex: 5, display: "flex", gap: 14, padding: "8px 12px", background: "rgba(19,22,30,.85)", border: "1px solid var(--border)", borderRadius: 8, fontFamily: "var(--mono)", fontSize: 10.5, color: "var(--text-muted)", backdropFilter: "blur(4px)" }}>
          {[["llm", "#c8f751"], ["tool", "#fbbf24"], ["agent", "#a78bfa"], ["error", "#fb7185"]].map(([label, c]) => (
            <span key={label} style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <span style={{ width: 7, height: 7, borderRadius: "50%", background: c }} />
              {label}
            </span>
          ))}
        </div>
      </ReactFlow>
    </div>
  );
}
