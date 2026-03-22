import { useState, useRef, useEffect } from "react";

export default function ChatPanel({ apiBase, onHighlight }) {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: "Hi! I can answer questions about the SAP O2C dataset — sales orders, deliveries, billing documents, payments, and more. Try one of the suggestions below or ask your own question.",
      cypher: null,
      data: null,
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [history, setHistory] = useState([]);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    fetch(`${apiBase}/api/suggestions`)
      .then((r) => r.json())
      .then((d) => setSuggestions(d.suggestions || []));
  }, [apiBase]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async (text) => {
    const msg = text || input.trim();
    if (!msg || loading) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: msg }]);
    setLoading(true);

    try {
      const res = await fetch(`${apiBase}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg, history }),
      });
      const data = await res.json();

      const assistantMsg = {
        role: "assistant",
        content: data.answer,
        cypher: data.cypher,
        data: data.data,
        totalRecords: data.total_records,
      };

      setMessages((prev) => [...prev, assistantMsg]);
      setHistory((prev) => [...prev, { user: msg, assistant: data.answer }]);

      if (data.node_ids?.length > 0) {
        onHighlight(data.node_ids);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Connection error. Is the backend running?" },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div style={styles.panel}>
      {/* Header */}
      <div style={styles.header}>
        <span style={styles.headerIcon}>💬</span>
        <span style={styles.headerTitle}>Ask the Graph</span>
      </div>

      {/* Messages */}
      <div style={styles.messages}>
        {messages.map((msg, i) => (
          <MessageBubble key={i} msg={msg} />
        ))}

        {loading && (
          <div style={styles.thinkingRow}>
            <div style={styles.dots}>
              <span /><span /><span />
            </div>
            <span style={{ color: "#8b949e", fontSize: 12 }}>Querying graph...</span>
          </div>
        )}

        {/* Suggestions (only shown when conversation is empty) */}
        {messages.length === 1 && !loading && (
          <div style={styles.suggestions}>
            {suggestions.slice(0, 5).map((s, i) => (
              <button key={i} style={styles.suggBtn} onClick={() => send(s)}>
                {s}
              </button>
            ))}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div style={styles.inputRow}>
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Ask about orders, deliveries, billing..."
          style={styles.textarea}
          rows={2}
          disabled={loading}
        />
        <button
          onClick={() => send()}
          disabled={loading || !input.trim()}
          style={{
            ...styles.sendBtn,
            opacity: loading || !input.trim() ? 0.4 : 1,
          }}
        >
          ↑
        </button>
      </div>
    </div>
  );
}

function MessageBubble({ msg }) {
  const [showCypher, setShowCypher] = useState(false);
  const [showData, setShowData] = useState(false);
  const isUser = msg.role === "user";

  return (
    <div style={{ ...styles.bubble, ...(isUser ? styles.userBubble : styles.aiBubble) }}>
      {!isUser && (
        <div style={styles.aiBadge}>AI</div>
      )}
      <div style={styles.bubbleText}>{msg.content}</div>

      {/* Cypher toggle */}
      {msg.cypher && (
        <div style={styles.metaSection}>
          <button
            style={styles.metaBtn}
            onClick={() => setShowCypher((v) => !v)}
          >
            {showCypher ? "▾" : "▸"} Cypher Query
          </button>
          {showCypher && (
            <pre style={styles.codeBlock}>{msg.cypher}</pre>
          )}

          {msg.data && msg.data.length > 0 && (
            <>
              <button
                style={styles.metaBtn}
                onClick={() => setShowData((v) => !v)}
              >
                {showData ? "▾" : "▸"} Raw Data ({msg.totalRecords} records)
              </button>
              {showData && (
                <div style={styles.dataTable}>
                  <DataTable data={msg.data.slice(0, 10)} />
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function DataTable({ data }) {
  if (!data || data.length === 0) return null;
  const cols = Object.keys(data[0]);
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={styles.table}>
        <thead>
          <tr>
            {cols.map((c) => (
              <th key={c} style={styles.th}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr key={i}>
              {cols.map((c) => (
                <td key={c} style={styles.td}>
                  {row[c] !== null && row[c] !== undefined ? String(row[c]) : "—"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Styles ───────────────────────────────────

const styles = {
  panel: {
    display: "flex", flexDirection: "column",
    height: "100%", overflow: "hidden",
  },
  header: {
    display: "flex", alignItems: "center", gap: 8,
    padding: "12px 16px", borderBottom: "1px solid #30363d",
    flexShrink: 0,
  },
  headerIcon: { fontSize: 16 },
  headerTitle: { fontSize: 14, fontWeight: 600, color: "#e6edf3" },
  messages: {
    flex: 1, overflowY: "auto", padding: "12px 14px",
    display: "flex", flexDirection: "column", gap: 12,
  },
  bubble: {
    borderRadius: 10, padding: "10px 12px",
    maxWidth: "100%", fontSize: 13, lineHeight: 1.6,
  },
  userBubble: {
    background: "#1f6feb22", border: "1px solid #1f6feb55",
    color: "#e6edf3", alignSelf: "flex-end",
    borderBottomRightRadius: 3,
  },
  aiBubble: {
    background: "#161b22", border: "1px solid #30363d",
    color: "#c9d1d9", alignSelf: "flex-start",
    borderBottomLeftRadius: 3,
  },
  aiBadge: {
    display: "inline-block", fontSize: 9, fontWeight: 700,
    background: "#1f6feb", color: "#fff", borderRadius: 4,
    padding: "1px 5px", marginBottom: 6, letterSpacing: 0.5,
  },
  bubbleText: { whiteSpace: "pre-wrap" },
  metaSection: { marginTop: 8, borderTop: "1px solid #30363d", paddingTop: 8 },
  metaBtn: {
    background: "none", border: "none", color: "#58a6ff",
    cursor: "pointer", fontSize: 11, padding: "2px 0",
    marginRight: 12, display: "inline-block",
  },
  codeBlock: {
    background: "#0d1117", border: "1px solid #30363d",
    borderRadius: 6, padding: "8px 10px", fontSize: 10,
    color: "#79c0ff", overflowX: "auto", marginTop: 6,
    whiteSpace: "pre-wrap", wordBreak: "break-all",
  },
  dataTable: { marginTop: 6, overflowX: "auto" },
  table: {
    borderCollapse: "collapse", width: "100%",
    fontSize: 10, color: "#c9d1d9",
  },
  th: {
    background: "#0d1117", padding: "4px 8px",
    textAlign: "left", color: "#8b949e",
    borderBottom: "1px solid #30363d",
    whiteSpace: "nowrap",
  },
  td: {
    padding: "3px 8px", borderBottom: "1px solid #21262d",
    maxWidth: 120, overflow: "hidden",
    textOverflow: "ellipsis", whiteSpace: "nowrap",
  },
  thinkingRow: {
    display: "flex", alignItems: "center", gap: 8,
    padding: "6px 0",
  },
  dots: {
    display: "flex", gap: 4,
    "& span": {
      width: 6, height: 6, borderRadius: "50%",
      background: "#58a6ff", animation: "bounce 1.2s infinite",
    },
  },
  suggestions: {
    display: "flex", flexDirection: "column", gap: 6, marginTop: 4,
  },
  suggBtn: {
    background: "#0d1117", border: "1px solid #30363d",
    borderRadius: 8, padding: "8px 12px",
    color: "#8b949e", cursor: "pointer", fontSize: 12,
    textAlign: "left", transition: "border-color 0.15s",
  },
  inputRow: {
    display: "flex", gap: 8, padding: "10px 12px",
    borderTop: "1px solid #30363d", flexShrink: 0, alignItems: "flex-end",
  },
  textarea: {
    flex: 1, background: "#0d1117", border: "1px solid #30363d",
    borderRadius: 8, padding: "8px 12px",
    color: "#e6edf3", fontSize: 13, resize: "none",
    fontFamily: "inherit", lineHeight: 1.5,
    outline: "none",
  },
  sendBtn: {
    width: 36, height: 36,
    background: "#1f6feb", border: "none",
    borderRadius: 8, color: "#fff",
    cursor: "pointer", fontSize: 18, fontWeight: 700,
    flexShrink: 0,
  },
};
