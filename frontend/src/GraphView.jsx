import { useEffect, useRef } from "react";
import cytoscape from "cytoscape";

export default function GraphView({ nodes, edges, highlightIds, onNodeClick }) {
  const containerRef = useRef(null);
  const cyRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current) return;

    cyRef.current = cytoscape({
      container: containerRef.current,
      elements: [...nodes, ...edges],
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            "shape": "data(shape)",
            "label": "data(label)",
            "color": "#e6edf3",
            "font-size": 9,
            "text-valign": "bottom",
            "text-halign": "center",
            "text-margin-y": 4,
            "text-wrap": "wrap",
            "text-max-width": 80,
            "width": 36,
            "height": 36,
            "border-width": 2,
            "border-color": "#30363d",
            "transition-property": "border-color, border-width, opacity",
            "transition-duration": "0.2s",
          },
        },
        {
          selector: "node:selected",
          style: {
            "border-color": "#58a6ff",
            "border-width": 3,
            "width": 44,
            "height": 44,
          },
        },
        {
          selector: "node.highlighted",
          style: {
            "border-color": "#f0b429",
            "border-width": 3,
            "width": 44,
            "height": 44,
          },
        },
        {
          selector: "node.dimmed",
          style: { "opacity": 0.25 },
        },
        {
          selector: "edge",
          style: {
            "width": 1.5,
            "line-color": "#30363d",
            "target-arrow-color": "#58a6ff",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            "label": "data(label)",
            "font-size": 8,
            "color": "#8b949e",
            "text-rotation": "autorotate",
            "text-margin-y": -6,
            "transition-property": "opacity",
            "transition-duration": "0.2s",
          },
        },
        {
          selector: "edge.dimmed",
          style: { "opacity": 0.1 },
        },
      ],
      layout: {
        name: "cose",
        animate: true,
        animationDuration: 600,
        nodeRepulsion: 8000,
        idealEdgeLength: 100,
        gravity: 0.25,
        numIter: 1000,
        fit: true,
        padding: 40,
      },
      wheelSensitivity: 0.3,
      minZoom: 0.1,
      maxZoom: 4,
    });

    // Click handler
    cyRef.current.on("tap", "node", (e) => {
      const node = e.target;
      onNodeClick({ data: node.data() });

      // Highlight neighborhood
      const neighborhood = node.neighborhood().add(node);
      cyRef.current.elements().addClass("dimmed");
      neighborhood.removeClass("dimmed");
    });

    // Click on background — reset
    cyRef.current.on("tap", (e) => {
      if (e.target === cyRef.current) {
        cyRef.current.elements().removeClass("dimmed").removeClass("highlighted");
      }
    });

    return () => {
      if (cyRef.current) cyRef.current.destroy();
    };
  }, []);   // run once


  // Add new nodes/edges when graph data updates
  useEffect(() => {
    if (!cyRef.current) return;
    const cy = cyRef.current;

    const existingIds = new Set(cy.elements().map((el) => el.id()));
    const newElements = [
      ...nodes.filter((n) => !existingIds.has(n.data.id)),
      ...edges.filter((e) => !existingIds.has(e.data.id)),
    ];

    if (newElements.length > 0) {
      cy.add(newElements);
      cy.layout({
        name: "cose",
        animate: true,
        animationDuration: 400,
        fit: false,
        randomize: false,
      }).run();
    }
  }, [nodes, edges]);


  // Highlight nodes from chat responses
  useEffect(() => {
    if (!cyRef.current) return;
    const cy = cyRef.current;

    cy.elements().removeClass("highlighted");

    if (highlightIds && highlightIds.length > 0) {
      highlightIds.forEach((id) => {
        cy.nodes().forEach((n) => {
          const props = n.data("props") || {};
          if (
            props.salesOrder === id ||
            props.billingDocument === id ||
            props.deliveryDocument === id ||
            props.businessPartner === id ||
            props.product === id ||
            props.plant === id
          ) {
            n.addClass("highlighted");
          }
        });
      });

      // Pan to highlighted nodes
      const highlighted = cy.nodes(".highlighted");
      if (highlighted.length > 0) {
        cy.animate({ fit: { eles: highlighted, padding: 80 } }, { duration: 500 });
      }
    }
  }, [highlightIds]);


  return (
    <div style={{ width: "100%", height: "100%", position: "relative" }}>
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />

      {/* Legend */}
      <Legend />

      {/* Controls */}
      <div style={controlStyle}>
        <button style={btnStyle} onClick={() => cyRef.current?.fit(undefined, 40)} title="Fit all">
          ⊡
        </button>
        <button style={btnStyle} onClick={() => cyRef.current?.zoom(cyRef.current.zoom() * 1.3)} title="Zoom in">
          +
        </button>
        <button style={btnStyle} onClick={() => cyRef.current?.zoom(cyRef.current.zoom() * 0.7)} title="Zoom out">
          −
        </button>
      </div>

      <p style={hintStyle}>Click a node to expand its neighbors · Scroll to zoom · Drag to pan</p>
    </div>
  );
}

const NODE_COLORS = {
  BusinessPartner: "#9B59B6",
  SalesOrder: "#2E86AB",
  OutboundDelivery: "#27AE60",
  BillingDocument: "#E67E22",
  JournalEntry: "#E74C3C",
  Payment: "#C0392B",
  Product: "#F39C12",
  Plant: "#1ABC9C",
};

function Legend() {
  return (
    <div style={legendStyle}>
      {Object.entries(NODE_COLORS).map(([label, color]) => (
        <div key={label} style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div style={{ width: 10, height: 10, borderRadius: "50%", background: color }} />
          <span style={{ fontSize: 10, color: "#8b949e" }}>{label}</span>
        </div>
      ))}
    </div>
  );
}

const legendStyle = {
  position: "absolute", top: 12, left: 12,
  background: "rgba(22,27,34,0.9)", border: "1px solid #30363d",
  borderRadius: 8, padding: "10px 14px",
  display: "flex", flexDirection: "column", gap: 5,
};

const controlStyle = {
  position: "absolute", top: 12, right: 12,
  display: "flex", flexDirection: "column", gap: 6,
};

const btnStyle = {
  width: 32, height: 32,
  background: "#161b22", border: "1px solid #30363d",
  borderRadius: 6, color: "#e6edf3", cursor: "pointer",
  fontSize: 16, lineHeight: 1, display: "flex",
  alignItems: "center", justifyContent: "center",
};

const hintStyle = {
  position: "absolute", bottom: 12, right: 12,
  fontSize: 10, color: "#484f58", margin: 0,
};
