import React, { useState, useCallback, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
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

import './App.css';

// Define custom node types
const nodeTypes = { tableNode: TableNode };

// --- Landing Page Component ---
function LandingPage() {
  return (
    <div>
      <h1>Welcome to the MySQL Visual UI</h1>
      <p>Select an option:</p>
      <nav>
        <ul>
          <li><Link to="/canvas">Schema Design Canvas</Link></li>
          <li><Link to="/select">Data Selection</Link></li>
          <li><Link to="/crud">CRUD Operations</Link></li>
          <li><Link to="/transactions">Transactions</Link></li>
          <li><Link to="/normalization">Normalization</Link></li>
        </ul>
      </nav>
    </div>
  );
}

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

  useEffect(() => {
    let isMounted = true;
    const loadInitialData = async () => {
        setLoadingSchema(true); setLoadingTables(true);
        setSchemaError(null); setPaletteError(null);
        try {
            const schemaResponse = await axios.get('http://localhost:5000/api/current_schema');
            const currentSchema = schemaResponse.data;
            console.log("[DEBUG] Fetched current schema:", currentSchema);
            if (!isMounted) return;

            const initialNodes = []; const initialEdges = [];
            const tablePositions = {}; let tableIndex = 0;
            const nodeSpacingX = 300; const nodeSpacingY = 200; const nodesPerRow = 3;

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

            console.log("[DEBUG] Processing relationships:", currentSchema.relationships);
            console.log("[DEBUG] Table name to node ID map:", tablePositions);
            for (const fk of currentSchema.relationships) {
                const sourceNodeId = tablePositions[fk.source];
                const targetNodeId = tablePositions[fk.target];
                console.log(`[DEBUG] FK: ${fk.id}, Source Table: ${fk.source} -> Node ID: ${sourceNodeId}, Target Table: ${fk.target} -> Node ID: ${targetNodeId}`);
                if (sourceNodeId && targetNodeId) {
                    initialEdges.push({ id: fk.id, source: sourceNodeId, target: targetNodeId, markerEnd: { type: MarkerType.ArrowClosed } });
                } else { console.warn(`[DEBUG] Could not find node ID for source (${fk.source}) or target (${fk.target}) for FK ${fk.id}`); }
            }
            console.log("[DEBUG] Generated initialEdges:", initialEdges);

            setNodes(initialNodes); setEdges(initialEdges); setLoadingSchema(false);
            setExistingTables(Object.keys(currentSchema.tables)); setLoadingTables(false);
        } catch (err) {
            console.error("Error loading initial schema:", err);
            if (isMounted) {
                const errorMsg = err.response?.data?.error || err.message || "Failed to load initial schema";
                setSchemaError(errorMsg); setPaletteError(errorMsg);
                setLoadingSchema(false); setLoadingTables(false);
            }
        }
    };
    loadInitialData();
    return () => { isMounted = false; };
  }, []);

  const addNode = useCallback(() => {
    const newId = `new-${schemaNodeIdCounter++}`;
    const newNode = {
      id: newId, position: { x: Math.random() * 400 + 20, y: Math.random() * 400 + 20 },
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
            id: newId, position: { x: Math.random() * 200 + 50, y: Math.random() * 200 + 50 },
            data: { label: tableDetails.table_name, attributes: tableDetails.attributes },
            type: 'tableNode',
        };
        setNodes((nds) => nds.concat(newNode));
    } catch (error) {
        const errorMsg = `Failed to load details for ${tableName}: ${error.response?.data?.error || error.message}`;
        setPaletteError(errorMsg); alert(errorMsg);
    }
  }, [nodes, setNodes]);

  const sendSchema = useCallback(async () => {
    const schemaData = {
      tables: nodes.map(node => ({ id: node.id, name: node.data.label, attributes: node.data.attributes || [] })),
      relationships: edges.map(edge => ({ id: edge.id, sourceTableId: edge.source, targetTableId: edge.target }))
    };
    console.log("Sending schema data:", schemaData);
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

  return (
    <div>
      <h2>Schema Design Canvas</h2>
      <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 200px)' }}>
        <div style={{ flexGrow: 1, border: '1px solid #ccc', marginBottom: '10px', position: 'relative' }}>
          {loadingSchema && <div style={{ padding: '20px' }}>Loading schema...</div>}
          {schemaError && <div style={{ padding: '20px', color: 'red' }}>Error loading schema: {schemaError}</div>}
          {!loadingSchema && !schemaError && (
            <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect} fitView defaultEdgeOptions={{ markerEnd: { type: MarkerType.ArrowClosed } }}>
              <Controls /> <Background /> <MiniMap />
            </ReactFlow>
          )}
        </div>
        <div style={{ flexShrink: 0, marginBottom: '10px' }}>
           <button onClick={addNode} style={{ marginRight: '5px' }}>Add New Table Node</button>
           <button onClick={sendSchema}>Apply Schema Changes to DB</button>
        </div>
        <div style={{ flexShrink: 0, borderTop: '1px solid #eee', paddingTop: '10px' }}>
          <h4>Existing Tables (Click to Add to Canvas):</h4>
          {loadingTables && <p>Loading existing tables...</p>}
          {paletteError && <p style={{ color: 'red' }}>Error loading palette: {paletteError}</p>}
          {!loadingTables && !paletteError && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px' }}>
              {existingTables.length > 0 ? (
                existingTables.map(tableName => (
                  <button key={tableName} onClick={() => addNodeFromExisting(tableName)} style={{ padding: '3px 6px', fontSize: '0.9em', cursor: 'pointer', border: '1px solid #ccc', background: '#f0f0f0' }}>
                    {tableName}
                  </button>
                ))
              ) : ( <p>No existing tables found in database.</p> )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
// --- End Schema Canvas Component ---

// --- Data Selection Component ---
function DataSelection() {
  const [allTables, setAllTables] = useState([]); // List of all available tables
  const [selectedTables, setSelectedTables] = useState({}); // { tableName: { attributes: [], selectedColumns: Set() } }
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [queryResults, setQueryResults] = useState(null); // To store results later
  const [queryError, setQueryError] = useState(null); // To store query errors
  const [isQuerying, setIsQuerying] = useState(false); // Loading state for query

  // Fetch all available tables on component mount
  useEffect(() => {
    const fetchTables = async () => {
      setLoading(true); setError(null);
      try {
        const response = await axios.get('http://localhost:5000/api/tables');
        setAllTables(response.data.tables || []);
      } catch (err) {
        setError(err.response?.data?.error || err.message || "Failed to fetch tables");
      } finally { setLoading(false); }
    };
    fetchTables();
  }, []);

  // Fetch table details when a table is selected
  const fetchTableDetails = useCallback(async (tableName) => {
    if (selectedTables[tableName]?.attributes) return; // Already fetched

    try {
      const response = await axios.get(`http://localhost:5000/api/table_details/${tableName}`);
      const details = response.data;
      if (details && details.attributes) {
        setSelectedTables(prev => ({
          ...prev,
          [tableName]: {
            attributes: details.attributes,
            // Initialize selectedColumns: select all initially
            selectedColumns: new Set(details.attributes.map(attr => attr.name))
          }
        }));
      }
    } catch (err) {
      console.error(`Error fetching details for ${tableName}:`, err);
      // Handle error display if needed
    }
  }, [selectedTables]); // Dependency on selectedTables to avoid redundant calls

  // Handle selecting/deselecting a table
  const toggleTableSelection = useCallback((tableName) => {
    setSelectedTables(prevSelected => {
      const newSelected = { ...prevSelected };
      if (newSelected[tableName]) {
        delete newSelected[tableName]; // Deselect
      } else {
        newSelected[tableName] = { attributes: null, selectedColumns: new Set() }; // Select (details fetched later)
        fetchTableDetails(tableName); // Trigger detail fetch
      }
      return newSelected;
    });
  }, [fetchTableDetails]); // Dependency on fetchTableDetails

  // Handle selecting/deselecting a column for a specific table
  const toggleColumnSelection = (tableName, columnName) => {
    setSelectedTables(prevSelected => {
        if (!prevSelected[tableName]) return prevSelected; // Should not happen

        const currentTable = prevSelected[tableName];
        const newSelectedColumns = new Set(currentTable.selectedColumns);

        if (newSelectedColumns.has(columnName)) {
            newSelectedColumns.delete(columnName);
        } else {
            newSelectedColumns.add(columnName);
        }

        return {
            ...prevSelected,
            [tableName]: {
                ...currentTable,
                selectedColumns: newSelectedColumns
            }
        };
    });
  };

  // TODO: Add state and handlers for joins, aggregates, group by

  // TODO: Implement runQuery function
  const runQuery = useCallback(async () => {
      // 1. Construct query definition object based on state
      //    (selectedTables, selectedColumns, joins, aggregates, groupBy)
      // 2. Send to backend /api/execute_select (needs to be created)
      // 3. Handle response (setQueryResults or setQueryError)
      console.log("Run Query Clicked - Placeholder");
      console.log("Current Selection State:", selectedTables);
      // Example structure to send:
      // const queryDef = {
      //    select: { table1: ['colA', 'colB'], table2: ['colC'] },
      //    from: ['table1', 'table2'],
      //    joins: [ { type: 'INNER', left: 'table1', right: 'table2', on: 'table1.id = table2.t1_id' } ], // Example
      //    where: "table1.colA > 10", // Example
      //    groupBy: ['table1.colB'], // Example
      //    aggregates: [ { func: 'COUNT', column: '*', alias: 'count_all' } ] // Example
      // }
      setIsQuerying(true); setQueryError(null); setQueryResults(null);
      // Replace with actual API call
      await new Promise(resolve => setTimeout(resolve, 1000)); // Simulate network delay
      setQueryError("Query execution not implemented yet.");
      setIsQuerying(false);

  }, [selectedTables /* Add other state dependencies: joins, aggregates etc. */]);

  const selectedTableNames = Object.keys(selectedTables);

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 100px)' }}> {/* Adjust height */}
      {/* Sidebar */}
      <div style={{ width: '300px', borderRight: '1px solid #ccc', padding: '10px', overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
        <h3>Tables</h3>
        {loading && <p>Loading tables...</p>}
        {error && <p style={{ color: 'red' }}>Error: {error}</p>}
        {!loading && !error && (
          <ul style={{ listStyle: 'none', padding: 0, marginBottom: '15px' }}>
            {allTables.length > 0 ? (
              allTables.map(tableName => (
                <li key={tableName} style={{ marginBottom: '5px' }}>
                  <label title={`Click to ${selectedTables[tableName] ? 'deselect' : 'select'} ${tableName}`}>
                    <input
                      type="checkbox"
                      checked={!!selectedTables[tableName]} // Check if key exists
                      onChange={() => toggleTableSelection(tableName)}
                      style={{ marginRight: '5px' }}
                    />
                    {tableName}
                  </label>
                </li>
              ))
            ) : ( <p>No tables found.</p> )}
          </ul>
        )}

        {/* Joins Section */}
        {selectedTableNames.length >= 2 && (
          <div style={{ borderTop: '1px solid #eee', paddingTop: '10px', marginBottom: '15px' }}>
            <h4>Joins</h4>
            <p>(Join UI Placeholder)</p>
            {/* TODO: UI for defining joins */}
          </div>
        )}

        {/* Columns / Filters Section */}
        {selectedTableNames.length >= 1 && (
          <div style={{ borderTop: '1px solid #eee', paddingTop: '10px', marginBottom: '15px' }}>
            <h4>Columns / Filters</h4>
            {selectedTableNames.map(tableName => (
              <div key={tableName} style={{ marginBottom: '10px' }}>
                <strong>{tableName}:</strong>
                {selectedTables[tableName]?.attributes ? (
                  <ul style={{ listStyle: 'none', paddingLeft: '15px', marginTop: '5px' }}>
                    {selectedTables[tableName].attributes.map(attr => (
                      <li key={`${tableName}-${attr.name}`}>
                        <label>
                          <input
                            type="checkbox"
                            checked={selectedTables[tableName].selectedColumns.has(attr.name)}
                            onChange={() => toggleColumnSelection(tableName, attr.name)}
                            style={{ marginRight: '5px' }}
                          />
                          {attr.name} <span style={{fontSize: '0.8em', color: '#666'}}>({attr.type})</span>
                        </label>
                      </li>
                    ))}
                  </ul>
                ) : ( <p style={{fontSize: '0.9em', color: '#888'}}>Loading columns...</p> )}
              </div>
            ))}
             <p>(Filter UI Placeholder)</p>
             {/* TODO: UI for defining WHERE clauses */}
          </div>
        )}

         {/* Aggregates Section */}
         {selectedTableNames.length >= 1 && (
          <div style={{ borderTop: '1px solid #eee', paddingTop: '10px', marginBottom: '15px' }}>
            <h4>Aggregates</h4>
            <p>(Aggregate UI Placeholder)</p>
            {/* TODO: UI for selecting aggregates */}
          </div>
        )}

         {/* Group By Section */}
         {/* TODO: Add condition based on aggregates being selected */}
         {selectedTableNames.length >= 1 && (
          <div style={{ borderTop: '1px solid #eee', paddingTop: '10px', marginBottom: '15px' }}>
            <h4>Group By</h4>
            <p>(Group By UI Placeholder)</p>
             {/* TODO: UI for selecting group by columns */}
          </div>
        )}

        {/* Query Button */}
        <div style={{ marginTop: 'auto', borderTop: '1px solid #eee', paddingTop: '15px' }}> {/* Pushes button to bottom */}
           <button onClick={runQuery} style={{ width: '100%' }} disabled={selectedTableNames.length === 0 || isQuerying}>
             {isQuerying ? 'Running...' : 'Run Query'}
           </button>
        </div>
      </div>

      {/* Main Content Area */}
      <div style={{ flexGrow: 1, padding: '10px', overflowY: 'auto' }}>
        <h2>Query Results</h2>
        {isQuerying && <p>Executing query...</p>}
        {queryError && <p style={{ color: 'red' }}>Query Error: {queryError}</p>}
        {queryResults ? (
            <div>(Display Results Table Here)</div> // TODO: Implement results table
        ) : (
            !isQuerying && <p>Define your query using the sidebar and click "Run Query".</p>
        )}
      </div>
    </div>
  );
}
// --- End Data Selection Component ---

function CrudOperations() { return <h2>CRUD Operations (Placeholder)</h2>; }
function Transactions() { return <h2>Transactions (Placeholder)</h2>; }
function Normalization() { return <h2>Normalization Analyzer (Placeholder)</h2>; }

// --- Main App Component ---
function App() {
  return (
    <Router>
      <div className="App">
        <nav>
          <ul>
            <li><Link to="/">Home</Link></li>
            <li><Link to="/canvas">Canvas</Link></li>
            <li><Link to="/select">Select</Link></li>
            <li><Link to="/crud">CRUD</Link></li>
            {/* Add other links */}
          </ul>
        </nav>
        <hr />
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/canvas" element={<SchemaCanvas />} />
          <Route path="/select" element={<DataSelection />} />
          <Route path="/crud" element={<CrudOperations />} />
          <Route path="/transactions" element={<Transactions />} />
          <Route path="/normalization" element={<Normalization />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App;
