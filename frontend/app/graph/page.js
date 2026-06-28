"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useResearch } from "../../context/ResearchContext";
import GraphView from "../../components/GraphView";
import PaperPanel from "../../components/PaperPanel";

export default function GraphPage() {
  const research = useResearch();
  const router = useRouter();
  const [selected, setSelected] = useState(null);

  useEffect(
    function () {
      if (!research.data) router.push("/search");
    },
    [research.data, router]
  );

  if (!research.data) return null;

  function handleNodeClick(arxivId) {
    const found = research.data.papers.find(function (p) {
      return p.arxiv_id === arxivId;
    });
    setSelected(found || null);
  }

  return (
    <main className="h-[calc(100vh-4rem)] flex">
      <div className="flex-1 relative">
        <GraphView graph={research.data.graph} onNodeClick={handleNodeClick} />
      </div>
      {selected && (
        <PaperPanel
          paper={selected}
          onClose={function () {
            setSelected(null);
          }}
        />
      )}
    </main>
  );
}