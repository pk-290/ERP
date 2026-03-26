import React, { useEffect, useRef, useState, useCallback } from 'react';
import cytoscape from 'cytoscape';
import axios from 'axios';
import { RefreshCw, ZoomIn, ZoomOut, Maximize2 } from 'lucide-react';

// O2C tier order — top to bottom in the pipeline
const TIER_LABELS = ['Customer', 'SalesOrder', 'Delivery', 'BillingDocument', 'JournalEntry'];
const TIER_Y     = { 0: 80, 1: 260, 2: 440, 3: 620, 4: 800 };
const TYPE_COLORS = {
  Customer:        '#4b32c3',
  SalesOrder:      '#009688',
  Delivery:        '#3f51b5',
  BillingDocument: '#e91e63',
  JournalEntry:    '#607d8b',
};
const TYPE_SIZES = {
  Customer: 52, SalesOrder: 40, Delivery: 34, BillingDocument: 28, JournalEntry: 24,
};

const CYTO_STYLE = [
  {
    selector: 'node',
    style: {
      'background-color': '#7c4dff',
      'label': 'data(label)',
      'color': '#ffffff',
      'font-family': 'Inter, sans-serif',
      'font-size': '9px',
      'text-valign': 'center',
      'text-halign': 'center',
      'text-wrap': 'ellipsis',
      'text-max-width': '60px',
      'width': '36px',
      'height': '36px',
      'border-width': '2px',
      'border-color': 'rgba(255,255,255,0.4)',
    },
  },
  ...TIER_LABELS.map(type => ({
    selector: `node[type="${type}"]`,
    style: {
      'background-color': TYPE_COLORS[type],
      'width': `${TYPE_SIZES[type]}px`,
      'height': `${TYPE_SIZES[type]}px`,
    },
  })),
  {
    selector: 'edge',
    style: {
      'width': 1.5,
      'line-color': '#c0c0c0',
      'target-arrow-color': '#c0c0c0',
      'target-arrow-shape': 'triangle',
      'curve-style': 'bezier',
      'font-size': '7px',
      'color': '#999',
      'text-rotation': 'autorotate',
      'text-margin-y': '-8px',
      'opacity': 0.7,
    },
  },
  {
    selector: 'edge[label="CANCELS"]',
    style: {
      'line-color': '#e91e63',
      'target-arrow-color': '#e91e63',
      'line-style': 'dashed',
    },
  },
  {
    selector: 'node:selected',
    style: {
      'border-width': '3px',
      'border-color': '#ffffff',
      'overlay-color': '#ffffff',
      'overlay-padding': '4px',
      'overlay-opacity': 0.1,
    },
  },
];

/** Assign horizontal preset positions by tier so nodes form clean pipeline bands */
function computeTierPositions(elements) {
  const CANVAS_W = 4000;

  const tierGroups = {};
  elements.forEach(el => {
    if (el.group === 'nodes') {
      const tier = el.data.tier ?? 2;
      (tierGroups[tier] = tierGroups[tier] || []).push(el.data.id);
    }
  });

  const positions = {};
  Object.entries(tierGroups).forEach(([tier, ids]) => {
    const y = TIER_Y[parseInt(tier)] ?? 500;
    ids.forEach((id, i) => {
      const count = ids.length;
      const x = count === 1 ? 0 : (i / (count - 1) - 0.5) * CANVAS_W;
      positions[id] = { x, y };
    });
  });

  return elements.map(el =>
    el.group === 'nodes' && positions[el.data.id]
      ? { ...el, position: positions[el.data.id] }
      : el
  );
}

const Legend = () => (
  <div style={{
    position: 'absolute', bottom: 16, left: 16, zIndex: 100,
    background: 'rgba(255,255,255,0.92)', border: '1px solid #e5e5e5',
    borderRadius: 10, padding: '10px 14px',
    boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
    fontSize: 11, lineHeight: '22px',
  }}>
    <div style={{ fontWeight: 600, marginBottom: 4, fontSize: 10, color: '#6b6b6b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
      O2C Pipeline
    </div>
    {TIER_LABELS.map((type, i) => (
      <div key={type} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{
          width: 12, height: 12, borderRadius: '50%',
          background: TYPE_COLORS[type], flexShrink: 0,
        }} />
        <span style={{ color: '#333' }}>
          <span style={{ color: '#aaa', marginRight: 4 }}>{'→'.repeat(i) || '⬤'}</span>
          {type}
        </span>
      </div>
    ))}
    <div style={{ marginTop: 6, borderTop: '1px solid #eee', paddingTop: 6, color: '#aaa', fontSize: 10 }}>
      Scroll to zoom · Drag to pan
    </div>
  </div>
);

const GraphPanel = () => {
  const containerRef = useRef(null);
  const cyRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isEmpty, setIsEmpty] = useState(false);
  const [stats, setStats] = useState(null);

  const renderGraph = useCallback((elements) => {
    if (cyRef.current) {
      cyRef.current.destroy();
      cyRef.current = null;
    }
    if (!containerRef.current || elements.length === 0) {
      setIsEmpty(elements.length === 0);
      return;
    }
    setIsEmpty(false);

    const positioned = computeTierPositions(elements);

    cyRef.current = cytoscape({
      container: containerRef.current,
      elements: positioned,
      style: CYTO_STYLE,
      layout: { name: 'preset', animate: false },
      minZoom: 0.05,
      maxZoom: 3,
      wheelSensitivity: 0.3,
    });

    // Fit with padding after layout
    cyRef.current.fit(undefined, 40);

    cyRef.current.on('tap', 'node', (evt) => {
      const d = evt.target.data();
      console.log(`[${d.type}] ${d.label}`, d);
    });
  }, []);

  const fetchGraphData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await axios.get('/api/graph');
      const els = response.data?.elements ?? [];
      const nodeCount = els.filter(e => e.group === 'nodes').length;
      const edgeCount = els.filter(e => e.group === 'edges').length;
      setStats({ nodes: nodeCount, edges: edgeCount });
      renderGraph(els);
    } catch (err) {
      console.error('Graph fetch error:', err);
      setError('Failed to connect to the backend. Is the ERP API running?');
    } finally {
      setLoading(false);
    }
  }, [renderGraph]);

  useEffect(() => {
    fetchGraphData();
    return () => { cyRef.current?.destroy(); };
  }, [fetchGraphData]);

  const zoomIn  = () => cyRef.current?.zoom({ level: cyRef.current.zoom() * 1.3, renderedPosition: { x: containerRef.current.clientWidth / 2, y: containerRef.current.clientHeight / 2 } });
  const zoomOut = () => cyRef.current?.zoom({ level: cyRef.current.zoom() / 1.3, renderedPosition: { x: containerRef.current.clientWidth / 2, y: containerRef.current.clientHeight / 2 } });
  const fitAll  = () => cyRef.current?.fit(undefined, 40);

  const hasGraph = !loading && !error && !isEmpty && cyRef.current;

  return (
    <div className="graph-panel">
      {/* Top-left controls */}
      <div style={{ position: 'absolute', top: 16, left: 16, zIndex: 100, display: 'flex', gap: 6 }}>
        <button onClick={fetchGraphData} className="icon-button" title="Refresh">
          <RefreshCw size={16} className={loading ? 'spin' : ''} />
        </button>
        <button onClick={zoomIn}  className="icon-button" title="Zoom in"><ZoomIn  size={16} /></button>
        <button onClick={zoomOut} className="icon-button" title="Zoom out"><ZoomOut size={16} /></button>
        <button onClick={fitAll}  className="icon-button" title="Fit all"><Maximize2 size={16} /></button>
      </div>

      {/* Node/edge count badge */}
      {stats && !loading && !error && (
        <div style={{
          position: 'absolute', top: 16, right: 16, zIndex: 100,
          background: 'rgba(255,255,255,0.92)', border: '1px solid #e5e5e5',
          borderRadius: 8, padding: '4px 10px', fontSize: 11, color: '#6b6b6b',
          boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
        }}>
          {stats.nodes} nodes · {stats.edges} edges
        </div>
      )}

      {/* Cytoscape canvas — always in DOM so the ref is stable */}
      <div
        ref={containerRef}
        style={{
          width: '100%', height: '100%',
          position: 'absolute', top: 0, left: 0,
          visibility: hasGraph ? 'visible' : 'hidden',
        }}
      />

      {loading && !cyRef.current && (
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%', color: '#6b6b6b', fontSize: 13 }}>
          Loading O2C Knowledge Graph…
        </div>
      )}
      {error && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, justifyContent: 'center', alignItems: 'center', height: '100%', color: '#d32f2f', padding: 20, textAlign: 'center' }}>
          <div style={{ fontSize: 14, fontWeight: 500 }}>{error}</div>
          <button onClick={fetchGraphData} className="icon-button" style={{ padding: '8px 16px', color: '#1a1a1a' }}>Retry</button>
        </div>
      )}
      {!loading && !error && isEmpty && (
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%', color: '#6b6b6b' }}>
          No graph data available.
        </div>
      )}

      {hasGraph && <Legend />}

      <style>{`
        .icon-button {
          background: white; border: 1px solid #e5e5e5;
          padding: 7px; border-radius: 8px; cursor: pointer;
          display: flex; align-items: center; justify-content: center;
          transition: all 0.15s; box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }
        .icon-button:hover { background: #f5f5f5; border-color: #d1d1d1; }
        .spin { animation: spin 1s linear infinite; }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
};

export default GraphPanel;
