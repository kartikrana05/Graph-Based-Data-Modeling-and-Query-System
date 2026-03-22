export default function StatsBar({ stats }) {
  if (!stats) return null;

  const totalNodes = stats.nodes.reduce((sum, n) => sum + n.count, 0);
  const totalRels = stats.relationships.reduce((sum, r) => sum + r.count, 0);

  return (
    <div style={styles.bar}>
      <Stat label="Nodes" value={totalNodes.toLocaleString()} color="#58a6ff" />
      <Stat label="Relationships" value={totalRels.toLocaleString()} color="#3fb950" />
      <Stat label="Entity Types" value={stats.nodes.length} color="#d2a8ff" />
    </div>
  );
}

function Stat({ label, value, color }) {
  return (
    <div style={styles.stat}>
      <span style={{ ...styles.value, color }}>{value}</span>
      <span style={styles.label}>{label}</span>
    </div>
  );
}

const styles = {
  bar: {
    display: "flex", gap: 20, alignItems: "center",
  },
  stat: {
    display: "flex", flexDirection: "column", alignItems: "center",
  },
  value: { fontSize: 15, fontWeight: 700, lineHeight: 1 },
  label: { fontSize: 10, color: "#484f58", marginTop: 2 },
};
