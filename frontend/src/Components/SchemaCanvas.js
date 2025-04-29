import React, { useState, useCallback, useEffect } from 'react';
import axios from 'axios';

import {
  ReactFlow,
  Controls,
  Background,
  applyNodeChanges,
  applyEdgeChanges,
  addEdge,
  MiniMap,
  MarkerType,
} from '@xyflow/react';
import TableNode from './TableNode';
import '@xyflow/react/dist/style.css';

import '../Styles/App.css';

// Define custom node types
const nodeTypes = { tableNode: TableNode };

// --- Schema Canvas Component ---
let schemaNodeIdCounter = 1;

function SchemaCanvas() {
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [existingTables, setExistingTables] = useState([]);
  const [loadingSchema, setLoadingSchema] = useState(true);
  const [loadingTables, setLoadingTables] = useState(false);
  const [paletteError, setPaletteError] = useState(null);
  const [schemaError, setSchemaError] = useState(null);

  const onNodesChange = useCallback((changes) => setNodes((nds) => applyNodeChanges(changes, nds)), [setNodes]);
  const onEdgesChange = useCallback((changes) => setEdges((eds) => applyEdgeChanges(changes, eds)), [setEdges]);
  const onConnect = useCallback((connection) => setEdges((eds) => addEdge({ ...connection, markerEnd: { type: MarkerType.ArrowClosed } }, eds)), [setEdges]);

  // --- useEffect for loading initial data (remains the same) ---
  useEffect(() => {
    let isMounted = true;
    const loadInitialData = async () => {
        setLoadingSchema(true); setLoadingTables(true);
        setSchemaError(null); setPaletteError(null);
        try {
            const schemaResponse = await axios.get('http://localhost:5000/api/current_schema');
            const currentSchema = schemaResponse.data;
            // console.log("[DEBUG] Fetched current schema:", currentSchema);
            if (!isMounted) return;

            const initialNodes = []; const initialEdges = [];
            const tablePositions = {}; let tableIndex = 0;
            const nodeSpacingX = 350; const nodeSpacingY = 250; const nodesPerRow = 3;

            for (const tableName in currentSchema.tables) {
                const tableData = currentSchema.tables[tableName];
                const posX = (tableIndex % nodesPerRow) * nodeSpacingX + 50;
                const posY = Math.floor(tableIndex / nodesPerRow) * nodeSpacingY + 50;
                const nodeId = `db-${tableName}`;
                initialNodes.push({
                    id: nodeId, position: { x: posX, y: posY },
                    data: { label: tableData.name, attributes: tableData.attributes },
                    type: 'tableNode',
                });
                tablePositions[tableName] = nodeId; tableIndex++;
            }
            schemaNodeIdCounter = initialNodes.length + 1;

            // console.log("[DEBUG] Processing relationships:", currentSchema.relationships);
            // console.log("[DEBUG] Table name to node ID map:", tablePositions);
            for (const fk of currentSchema.relationships) {
                const sourceNodeId = tablePositions[fk.source];
                const targetNodeId = tablePositions[fk.target];
                // console.log(`[DEBUG] FK: ${fk.id}, Source Table: ${fk.source} -> Node ID: ${sourceNodeId}, Target Table: ${fk.target} -> Node ID: ${targetNodeId}`);
                if (sourceNodeId && targetNodeId) {
                    initialEdges.push({ id: fk.id, source: sourceNodeId, target: targetNodeId, markerEnd: { type: MarkerType.ArrowClosed } });
                } else { console.warn(`[DEBUG] Could not find node ID for source (${fk.source}) or target (${fk.target}) for FK ${fk.id}`); }
            }
            // console.log("[DEBUG] Generated initialEdges:", initialEdges);

            setNodes(initialNodes); setEdges(initialEdges); setLoadingSchema(false);
            setExistingTables(Object.keys(currentSchema.tables)); setLoadingTables(false);
        } catch (err) {
            console.error("Error loading initial schema:", err);
            if (isMounted) {
                const errorMsg = err.response?.data?.error || err.message || "Failed to load initial schema";
                setSchemaError(<div className="error-message">{errorMsg}</div>);
                setPaletteError(<div className="error-message">{errorMsg}</div>);
                setLoadingSchema(false); setLoadingTables(false);
            }
        }
    };
    loadInitialData();
    return () => { isMounted = false; };
  }, []);

  // --- Callbacks addNode, addNodeFromExisting, sendSchema (remain the same) ---
  const addNode = useCallback(() => {
    const newId = `new-${schemaNodeIdCounter++}`;
    const newNode = {
      id: newId, position: { x: Math.random() * 100 + 20, y: Math.random() * 100 + 20 }, // Adjust position for canvas
      data: { label: `NewTable_${newId.split('-')[1]}`, attributes: [{ name: 'id', type: 'INT', isPK: true, isNotNull: true, isUnique: true }] },
      type: 'tableNode',
    };
    setNodes((nds) => nds.concat(newNode));
  }, [setNodes]);

  const addNodeFromExisting = useCallback(async (tableName) => {
    setPaletteError(null);
    try {
        const response = await axios.get(`http://localhost:5000/api/table_details/${tableName}`);
        const tableDetails = response.data;
        if (!tableDetails || !tableDetails.attributes) throw new Error("Invalid data received.");
        if (nodes.find(n => n.data.label === tableDetails.table_name)) {
            alert(`Table "${tableDetails.table_name}" is already on the canvas.`); return;
        }
        const newId = `existing-${schemaNodeIdCounter++}`;
        const newNode = {
            id: newId, position: { x: Math.random() * 100 + 50, y: Math.random() * 100 + 50 }, // Adjust position for canvas
            data: { label: tableDetails.table_name, attributes: tableDetails.attributes },
            type: 'tableNode',
        };
        setNodes((nds) => nds.concat(newNode));
    } catch (error) {
        const errorMsg = `Failed to load details for ${tableName}: ${error.response?.data?.error || error.message}`;
        setPaletteError(<div className="error-message">{errorMsg}</div>);
        alert(errorMsg);
    }
  }, [nodes, setNodes]);

  const sendSchema = useCallback(async () => {
    const schemaData = {
      tables: nodes.map(node => ({ id: node.id, name: node.data.label, attributes: node.data.attributes || [] })),
      relationships: edges.map(edge => ({ id: edge.id, sourceTableId: edge.source, targetTableId: edge.target }))
    };
    // console.log("Sending schema data:", schemaData);
    try {
      const response = await axios.post('http://localhost:5000/api/schema', schemaData);
      alert(`Schema data sent! Backend says: ${response.data.message}`);
      if (response.status === 200 || response.status === 207) {
         const tablesResponse = await axios.get('http://localhost:5000/api/tables');
         setExistingTables(tablesResponse.data.tables || []);
      }
    } catch (error) {
      alert(`Error sending schema data: ${error.response?.data?.error || error.message}`);
    }
  }, [nodes, edges, setExistingTables]);


  // --- Restructured Return Statement ---
  return (
    // Use the component-layout structure
    <div className="component-layout">
        {/* Sidebar */}
        <div className="sidebar">
            {/* Section for Control Buttons */}
            <div className="sidebar-section">
                <h3>Controls</h3>
                <button onClick={addNode} style={{ width: '100%', marginBottom: '10px' }}>
                    Add New Table Node
                </button>
                <button onClick={sendSchema} style={{ width: '100%' }}>
                    Apply Schema Changes to DB
                </button>
            </div>

             {/* Section for Existing Tables Palette */}
            <div className="sidebar-section existing-tables-palette" style={{ flexGrow: 1, overflowY: 'auto' }}> {/* Allow palette to grow and scroll */}
                <h4>Existing Tables (Click to Add)</h4>
                {loadingTables && <p>Loading existing tables...</p>}
                {paletteError && <div>{paletteError}</div>}
                {!loadingTables && !paletteError && (
                    <div className="existing-tables-list">
                        {existingTables.length > 0 ? (
                        existingTables.map(tableName => (
                            <button
                                key={tableName}
                                onClick={() => addNodeFromExisting(tableName)}
                                className="existing-table-button"
                                >
                            {tableName}
                            </button>
                        ))
                        ) : (
                        <p className="no-existing-tables-message">
                            No existing tables found.
                        </p>
                        )}
                    </div>
                )}
            </div>
        </div> {/* End Sidebar */}

        {/* Main Content Area - Canvas */}
        <div className="main-content" style={{ padding: 0, border: 'none' }}> {/* Remove padding/border if canvas handles it */}
            {/* Set height for the React Flow container */}
            <div style={{ height: '100%', width: '100%', position: 'relative' }}>
                {loadingSchema && <div style={{ padding: '20px' }}>Loading schema...</div>}
                {schemaError && <div style={{ padding: '20px' }}>{schemaError}</div>}
                {!loadingSchema && !schemaError && (
                    <ReactFlow
                        nodes={nodes}
                        edges={edges}
                        nodeTypes={nodeTypes}
                        onNodesChange={onNodesChange}
                        onEdgesChange={onEdgesChange}
                        onConnect={onConnect}
                        fitView
                        defaultEdgeOptions={{ markerEnd: { type: MarkerType.ArrowClosed } }}
                        style={{ background: 'var(--bg-primary)' }}
                        >
                        <Controls />
                        <Background 
                            variant="dots"
                            gap={20}
                            size={1}
                            color="var(--border-color)"
                            style={{ backgroundColor: 'var(--bg-primary)' }}
                        />
                        <MiniMap />
                    </ReactFlow>
                )}
            </div>
        </div> {/* End Main Content */}
    </div> // End component-layout
  );
}

export default SchemaCanvas;
// --- End Schema Canvas Component ---