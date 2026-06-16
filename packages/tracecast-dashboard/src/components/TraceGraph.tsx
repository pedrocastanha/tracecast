import { useMemo, useState } from "react";
import ReactFlow, { Background, Controls, MarkerType, Node, Edge } from "reactflow";
import "reactflow/dist/style.css";

interface GraphNode {
  id: string;
  parent_span_id: string | null;
  name: string;
  type: string;
  status: string;
  model: string | null;
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
  llm: "var(--accent)",
  tool: "var(--yellow)",
  agent: "var(--green)",
};

function layout(nodes: GraphNode[]): Record<string, { x: number; y: number }> {
  const depth: Record<string, number> = {};
  const compute = (id: string, byId: Record<string, GraphNode>, seen: Set<string>): number => {
    if (id in depth) return depth[id];
    if (seen.has(id)) return 0;
    seen.add(id);
    const node = byId[id];
    const d = node && node.parent_span_id ? compute(node.parent_span_id, byId, seen) + 1 : 0;
    depth[id] = d;
    return d;
  };
  const byId: Record<string, GraphNode> = {};
  nodes.forEach((n) => (byId[n.id] = n));
  nodes.forEach((n) => compute(n.id, byId, new Set()));

  const perLevel: Record<number, number> = {};
  const pos: Record<string, { x: number; y: number }> = {};
  nodes.forEach((n) => {
    const d = depth[n.id] ?? 0;
    const idx = perLevel[d] ?? 0;
    perLevel[d] = idx + 1;
    pos[n.id] = { x: idx * 240, y: d * 130 };
  });
  return pos;
}

export function TraceGraph({ data, onSelect }: { data: GraphData; onSelect: (id: string) => void }) {
  const [selected, setSelected] = useState<string | null>(null);

  const { nodes, edges } = useMemo(() => {
    const pos = layout(data.nodes);
    const rfNodes: Node[] = data.nodes.map((n) => ({
      id: n.id,
      position: pos[n.id] ?? { x: 0, y: 0 },
      data: {
        label: `${n.name}${n.total_tokens ? ` · ${n.total_tokens}tok` : ""}${
          n.latency_ms != null ? ` · ${n.latency_ms}ms` : ""
        }`,
      },
      style: {
        border: `2px solid ${n.status === "error" ? "var(--red)" : TYPE_COLOR[n.type] ?? "var(--accent)"}`,
        borderRadius: 8,
        padding: 8,
        background: "var(--surface)",
        color: "var(--text)",
        fontSize: 12,
        width: 200,
        outline: selected === n.id ? "2px solid var(--accent)" : "none",
      },
    }));
    const rfEdges: Edge[] = data.edges.map((e, i) => ({
      id: `e${i}`,
      source: e.from,
      target: e.to,
      animated: !!e.conditional,
      markerEnd: { type: MarkerType.ArrowClosed },
      style: { stroke: "var(--border)" },
    }));
    return { nodes: rfNodes, edges: rfEdges };
  }, [data, selected]);

  return (
    <div style={{ height: 480, border: "1px solid var(--border)", borderRadius: 8 }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        onNodeClick={(_, node) => {
          setSelected(node.id);
          onSelect(node.id);
        }}
        proOptions={{ hideAttribution: true }}
      >
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}
