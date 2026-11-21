import { useEffect, useReducer, useRef, useState } from "react";
import { ask } from "../api";
import type { ApiError, AskResponse } from "../types";
import { AnswerCard } from "./AnswerCard";
import { ErrorBox } from "./ErrorBox";

// ---------- state: every transition of a chat turn lives in this reducer ----------

type Turn =
  | { id: number; question: string; state: "pending" }
  | { id: number; question: string; state: "done"; response: AskResponse }
  | { id: number; question: string; state: "error"; error: ApiError };

type Action =
  | { type: "submit"; id: number; question: string }
  | { type: "retry"; id: number }
  | { type: "succeed"; id: number; response: AskResponse }
  | { type: "fail"; id: number; error: ApiError };

function reducer(turns: Turn[], action: Action): Turn[] {
  switch (action.type) {
    case "submit":
      return [...turns, { id: action.id, question: action.question, state: "pending" }];
    case "retry":
      return turns.map((t) => (t.id === action.id ? { id: t.id, question: t.question, state: "pending" } : t));
    case "succeed":
      return turns.map((t) => (t.id === action.id ? { id: t.id, question: t.question, state: "done", response: action.response } : t));
    case "fail":
      return turns.map((t) => (t.id === action.id ? { id: t.id, question: t.question, state: "error", error: action.error } : t));
  }
}

const EXAMPLES = [
  "What are our top 5 vendors by total spend in 2025?",
  "What is our total spend with vendors based in Spain?",
  "Who is allowed to approve an invoice of EUR 60,000?",
  "Which invoices are missing an approver?",
];

export function Chat() {
  const [turns, dispatch] = useReducer(reducer, []);
  const [draft, setDraft] = useState("");
  const nextId = useRef(1);
  const bottom = useRef<HTMLDivElement>(null);
  const busy = turns.some((t) => t.state === "pending"); // one question at a time

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [turns]);

  async function run(id: number, question: string) {
    const res = await ask(question);
    dispatch(res.ok ? { type: "succeed", id, response: res.data } : { type: "fail", id, error: res.error });
  }

  function submit(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    const id = nextId.current++;
    dispatch({ type: "submit", id, question: q });
    setDraft("");
    void run(id, q);
  }

  function retry(turn: Turn) {
    dispatch({ type: "retry", id: turn.id });
    void run(turn.id, turn.question);
  }

  return (
    <section className="chat">
      <div className="turns">
        {turns.length === 0 && (
          <div className="empty">
            <p>Ask about 2025 invoices or the procurement policy. Every answer shows the policy clauses and data rows it is based on.</p>
            <div className="examples">
              {EXAMPLES.map((q) => <button key={q} onClick={() => submit(q)}>{q}</button>)}
            </div>
          </div>
        )}
        {turns.map((t) => (
          <div key={t.id} className="turn">
            <div className="bubble user">{t.question}</div>
            {t.state === "pending" && <div className="bubble bot thinking" aria-busy="true">Checking the data and the policy…</div>}
            {t.state === "error" && <ErrorBox error={t.error} onRetry={busy ? undefined : () => retry(t)} />}
            {t.state === "done" && <AnswerCard r={t.response} />}
          </div>
        ))}
        <div ref={bottom} />
      </div>

      <form className="composer" onSubmit={(e) => { e.preventDefault(); submit(draft); }}>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={busy ? "Waiting for the answer…" : "Ask a question…"}
          maxLength={1000}
          disabled={busy}
          aria-label="Question"
        />
        <button type="submit" disabled={busy || !draft.trim()}>Ask</button>
      </form>
    </section>
  );
}
