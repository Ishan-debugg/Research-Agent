"use client";

import { useMemo, useState } from "react";
import ReactFlow, { Background, Controls, MarkerType } from "reactflow";
import "reactflow/dist/style.css";

/* ── Improvement: Truncate long node labels ── */
function truncateLabel(text, maxWords) {
  var words = text.split(" ");
  if (words.length <= (maxWords || 5)) return text;
  return words.slice(0, maxWords || 5).join(" ") + "…";
}

function layoutNodes(nodes) {
  var radius = 260;
  var center = { x: 420, y: 320 };
  return nodes.map(function (node, i) {
    var angle = (i / nodes.length) * 2 * Math.PI;
    return {
      id: node.id,
      data: {
        label: truncateLabel(node.label, 5),
        fullLabel: node.label,
      },
      position: {
        x: center.x + radius * Math.cos(angle),
        y: center.y + radius * Math.sin(angle),
      },
      style: {
        background: "var(--surface)",
        color: "var(--text)",
        border: "1px solid var(--border)",
        borderRadius: 8,
        padding: 10,
        fontSize: 12,
        width: 180,
      },
      title: node.label, // native browser tooltip for full title
    };
  });
}

function layoutEdges(edges, hoveredNodeId) {
  return edges.map(function (edge, i) {
    var connected =
      hoveredNodeId &&
      (edge.source === hoveredNodeId || edge.target === hoveredNodeId);
    var dimmed = hoveredNodeId && !connected;

    return {
      id: "e" + i,
      source: edge.source,
      target: edge.target,
      label: edge.relationship,
      labelStyle: {
        fill: dimmed ? "#444" : "#8e8c97",
        fontSize: 10,
        opacity: dimmed ? 0.3 : 1,
      },
      style: {
        stroke: connected ? "#c9a24b" : dimmed ? "#333" : "#c9a24b",
        strokeWidth: connected ? 2.5 : 1.5,
        opacity: dimmed ? 0.2 : 1,
        transition: "opacity 0.2s, stroke-width 0.2s",
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: connected ? "#c9a24b" : dimmed ? "#444" : "#c9a24b",
      },
    };
  });
}

export default function GraphView({ graph, onNodeClick }) {
  /* ── Improvement: Edge highlight on node hover ── */
  const [hoveredNodeId, setHoveredNodeId] = useState(null);

  const nodes = useMemo(function () {
    return layoutNodes(graph.nodes);
  }, [graph.nodes]);

  const edges = useMemo(function () {
    return layoutEdges(graph.edges, hoveredNodeId);
  }, [graph.edges, hoveredNodeId]);

  return (
    <div className="absolute inset-0">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodeClick={function (_, node) {
          onNodeClick(node.id);
        }}
        onNodeMouseEnter={function (_, node) {
          setHoveredNodeId(node.id);
        }}
        onNodeMouseLeave={function () {
          setHoveredNodeId(null);
        }}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background variant="dots" color="#c9a24b" gap={22} size={1.2} style={{ opacity: 0.35 }} />
        <Controls />
      </ReactFlow>
    </div>
  );
}