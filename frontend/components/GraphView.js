"use client";

import { useMemo } from "react";
import ReactFlow, { Background, Controls, MarkerType } from "reactflow";
import "reactflow/dist/style.css";

function layoutNodes(nodes) {
  const radius = 260;
  const center = { x: 420, y: 320 };
  return nodes.map(function (node, i) {
    const angle = (i / nodes.length) * 2 * Math.PI;
    return {
      id: node.id,
      data: { label: node.label },
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
    };
  });
}

function layoutEdges(edges) {
  return edges.map(function (edge, i) {
    return {
      id: "e" + i,
      source: edge.source,
      target: edge.target,
      label: edge.relationship,
      labelStyle: { fill: "#8e8c97", fontSize: 10 },
      style: { stroke: "#c9a24b", strokeWidth: 1.5 },
      markerEnd: { type: MarkerType.ArrowClosed, color: "#c9a24b" },
    };
  });
}

export default function GraphView({ graph, onNodeClick }) {
  const nodes = useMemo(function () {
    return layoutNodes(graph.nodes);
  }, [graph.nodes]);

  const edges = useMemo(function () {
    return layoutEdges(graph.edges);
  }, [graph.edges]);

  return (
    <div className="absolute inset-0">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodeClick={function (_, node) {
          onNodeClick(node.id);
        }}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#1c1c22" gap={20} />
        <Controls />
      </ReactFlow>
    </div>
  );
}