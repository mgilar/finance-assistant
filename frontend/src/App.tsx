import { useEffect, useState } from "react";
import { getHealth } from "./api";
import { Chat } from "./components/Chat";
import { SummaryPanel } from "./components/SummaryPanel";
import type { HealthResponse } from "./types";

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    getHealth().then((res) => setHealth(res.ok ? res.data : null));
  }, []);

  return (
    <div className="app">
      <header className="topbar">
        <h1>Finance Spend Assistant</h1>
        {health && <span className="muted">{health.mode === "llm" ? `AI: ${health.model}` : ""}</span>}
      </header>
      {health?.mode === "stub" && (
        <div className="stub-banner" role="status">
          STUB MODE: no ANTHROPIC_API_KEY configured. Answers come from a keyword router over the
          real data tools, not from an LLM; only a few question shapes are understood.
        </div>
      )}
      <main className="layout">
        <SummaryPanel />
        <Chat />
      </main>
    </div>
  );
}
