import { useState, useEffect } from "react";
import GraphView from "./GraphView";
import ChatPanel from "./ChatPanel";
import StatsBar from "./StatsBar";

const API = import.meta.env.VITE_API_URL || "https://graph-based-data-modeling-and-query.onrender.com";

export default function App() {
  const [graphData, setGraphData] = useState({ nodes: [], edges: [] });
  const [stats, setStats] = useState(null);
  const [highlightIds, setHighlightIds] = useState([]);
  const [selectedNode, setSelectedNode] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch(`${API}/api/graph`).then((r) => r.json()),
      fetch(`${API}/api/stats`).then((r) => r.json()),
    ]).then(([graph, statsData]) => {
      setGraphData(graph);
      setStats(statsData);
      setLoading(false);
    });
  }, []);

  const handleNodeExpand = async (nodeType, nodeId) => {
    const res = await fetch(`${API}/api/expand/${nodeType}/${nodeId}`);
    const data = await res.json();

    setGraphData((prev) => {
      const existingNodeIds = new Set(prev.nodes.map((n) => n.data.id));
      const existingEdgeIds = new Set(prev.edges.map((e) => e.data.id));
      const newNodes = data.nodes.filter((n) => !existingNodeIds.has(n.data.id));
      const newEdges = data.edges.filter((e) => !existingEdgeIds.has(e.data.id));
      return {
        nodes: [...prev.nodes, ...newNodes],
        edges: [...prev.edges, ...newEdges],
      };
    });
  };

  const handleChatHighlight = (nodeIds) => {
    setHighlightIds(nodeIds);
  };

  return (
    <div style={styles.app}>
      {/* Header */}
      <div style={styles.header}>
        <div style={styles.headerLeft}>
          <span style={styles.logo}>⬡</span>
          <span style={styles.title}>SAP O2C Graph Explorer</span>
        </div>
        {stats && <StatsBar stats={stats} />}
      </div>

      {/* Main layout */}
      <div style={styles.body}>
        {/* Graph Panel */}
        <div style={styles.graphPanel}>
          {loading ? (
            <div style={styles.loadingBox}>
              <div style={styles.spinner} />
              <p style={{ color: "#888", marginTop: 16 }}>Loading graph...</p>
            </div>
          ) : (
            <GraphView
              nodes={graphData.nodes}
              edges={graphData.edges}
              highlightIds={highlightIds}
              onNodeClick={(node) => {
                setSelectedNode(node);
                handleNodeExpand(node.data.type, node.data.props[getPrimaryKey(node.data.type)]);
              }}
            />
          )}

          {/* Node detail panel */}
          {selectedNode && (
            <NodeDetail node={selectedNode} onClose={() => setSelectedNode(null)} />
          )}
        </div>

        {/* Chat Panel */}
        <div style={styles.chatPanel}>
          <ChatPanel apiBase={API} onHighlight={handleChatHighlight} />
        </div>
      </div>
    </div>
  );
}

function getPrimaryKey(type) {
  const map = {
    SalesOrder: "salesOrder", OutboundDelivery: "deliveryDocument",
    BillingDocument: "billingDocument", BusinessPartner: "businessPartner",
    Product: "product", Plant: "plant", SalesOrderItem: "itemId",
    OutboundDeliveryItem: "itemId", BillingDocumentItem: "itemId",
    JournalEntry: "journalId", Payment: "paymentId", Address: "addressId",
  };
  return map[type] || "id";
}

function NodeDetail({ node, onClose }) {
  const props = node.data.props || {};
  return (
    <div style={styles.nodeDetail}>
      <div style={styles.nodeDetailHeader}>
        <span style={{ ...styles.nodeTypeBadge, background: node.data.color }}>
          {node.data.type}
        </span>
        <button onClick={onClose} style={styles.closeBtn}>✕</button>
      </div>
      <div style={styles.nodeProps}>
        {Object.entries(props)
          .filter(([, v]) => v !== null && v !== "" && v !== undefined)
          .map(([k, v]) => (
            <div key={k} style={styles.propRow}>
              <span style={styles.propKey}>{camelToLabel(k)}</span>
              <span style={styles.propVal}>{String(v)}</span>
            </div>
          ))}
      </div>
    </div>
  );
}

function camelToLabel(str) {
  return str.replace(/([A-Z])/g, " $1").replace(/^./, (s) => s.toUpperCase());
}

// ─── Styles ───────────────────────────────────

const styles = {
  app: {
    display: "flex", flexDirection: "column",
    height: "100vh", background: "#0f1117", color: "#e0e0e0",
    fontFamily: "'Inter', sans-serif", overflow: "hidden",
  },
  header: {
    display: "flex", alignItems: "center", justifyContent: "space-between",
    padding: "0 20px", height: 52, background: "#161b22",
    borderBottom: "1px solid #30363d", flexShrink: 0,
  },
  headerLeft: { display: "flex", alignItems: "center", gap: 10 },
  logo: { fontSize: 22, color: "#58a6ff" },
  title: { fontSize: 16, fontWeight: 600, color: "#e6edf3", letterSpacing: 0.3 },
  body: { display: "flex", flex: 1, overflow: "hidden" },
  graphPanel: {
    flex: 1, position: "relative", overflow: "hidden",
    background: "#0d1117",
  },
  chatPanel: {
    width: 380, borderLeft: "1px solid #30363d",
    display: "flex", flexDirection: "column", overflow: "hidden",
    background: "#161b22",
  },
  loadingBox: {
    display: "flex", flexDirection: "column",
    alignItems: "center", justifyContent: "center",
    height: "100%",
  },
  spinner: {
    width: 36, height: 36,
    border: "3px solid #30363d", borderTop: "3px solid #58a6ff",
    borderRadius: "50%", animation: "spin 0.8s linear infinite",
  },
  nodeDetail: {
    position: "absolute", bottom: 20, left: 20,
    width: 300, maxHeight: 340,
    background: "#161b22", border: "1px solid #30363d",
    borderRadius: 10, overflow: "hidden",
    boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
  },
  nodeDetailHeader: {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    padding: "10px 14px", borderBottom: "1px solid #30363d",
  },
  nodeTypeBadge: {
    padding: "3px 10px", borderRadius: 20,
    fontSize: 12, fontWeight: 600, color: "#fff",
  },
  closeBtn: {
    background: "none", border: "none", color: "#888",
    cursor: "pointer", fontSize: 14, padding: "2px 6px",
  },
  nodeProps: { padding: "8px 0", overflowY: "auto", maxHeight: 280 },
  propRow: {
    display: "flex", justifyContent: "space-between",
    padding: "4px 14px", gap: 8,
  },
  propKey: { color: "#8b949e", fontSize: 11, flexShrink: 0, minWidth: 100 },
  propVal: {
    color: "#e6edf3", fontSize: 11,
    textAlign: "right", wordBreak: "break-all",
  },
};
