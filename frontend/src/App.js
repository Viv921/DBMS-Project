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
const initialNodes = [
  {
    id: '1',
    position: { x: 50, y: 50 },
    data: {
      label: 'users',
      attributes: [
        { name: 'id', type: 'INT', isPK: true, isNotNull: true, isUnique: true },
        { name: 'username', type: 'VARCHAR(255)', isPK: false, isNotNull: true, isUnique: true },
      ]
    },
    type: 'tableNode'
  },
];
let nodeIdCounter = 2; // Use a different name to avoid conflict with node 'id' prop

function SchemaCanvas() {
  const [nodes, setNodes] = useState(initialNodes);
  const [edges, setEdges] = useState([]);
  const [existingTables, setExistingTables] = useState([]);
  const [loadingTables, setLoadingTables] = useState(false);
  const [paletteError, setPaletteError] = useState(null);

  // Handlers for node/edge changes and connections
  const onNodesChange = useCallback(
    (changes) => setNodes((nds) => applyNodeChanges(changes, nds)),
    [setNodes]
  );
  const onEdgesChange = useCallback(
    (changes) => setEdges((eds) => applyEdgeChanges(changes, eds)),
    [setEdges]
  );
  const onConnect = useCallback(
    (connection) => setEdges((eds) => addEdge({ ...connection, markerEnd: { type: MarkerType.ArrowClosed } }, eds)),
    [setEdges]
  );

  // Fetch existing tables for the palette
  useEffect(() => {
    const fetchExistingTables = async () => {
      setLoadingTables(true);
      setPaletteError(null);
      try {
        const response = await axios.get('http://localhost:5000/api/tables');
        setExistingTables(response.data.tables || []);
      } catch (err) {
        console.error("Error fetching existing tables for palette:", err);
        setPaletteError(err.response?.data?.error || err.message || "Failed to fetch existing tables");
      } finally {
        setLoadingTables(false);
      }
    };
    fetchExistingTables();
  }, []); // Fetch once on mount

  // Function to add a new blank table node
  const addNode = useCallback(() => {
    const newId = `${nodeIdCounter++}`;
    const newNode = {
      id: newId,
      position: {
        x: Math.random() * 400 + 20, // Add offset
        y: Math.random() * 400 + 20,
      },
      data: {
        label: `NewTable_${newId}`,
        attributes: [{ name: 'id', type: 'INT', isPK: true, isNotNull: true, isUnique: true }]
      },
      type: 'tableNode',
    };
    setNodes((nds) => nds.concat(newNode));
  }, [setNodes]); // Include setNodes dependency

  // Function to add a node based on an existing table structure
  const addNodeFromExisting = useCallback(async (tableName) => {
    setPaletteError(null); // Clear previous errors
    console.log(`Fetching details for table: ${tableName}`);
    try {
        const response = await axios.get(`http://localhost:5000/api/table_details/${tableName}`);
        const tableDetails = response.data;

        if (!tableDetails || !tableDetails.attributes) {
            throw new Error("Invalid data received from table details endpoint.");
        }

        const newId = `${nodeIdCounter++}`;
        const newNode = {
            id: newId,
            position: { // Position slightly offset to avoid exact overlap
                x: Math.random() * 200 + 50,
                y: Math.random() * 200 + 50,
            },
            data: {
                label: tableDetails.table_name, // Use the actual name
                attributes: tableDetails.attributes, // Use attributes from DB
            },
            type: 'tableNode',
        };
        setNodes((nds) => nds.concat(newNode));

    } catch (error) {
        console.error(`Error fetching details for table ${tableName}:`, error);
        const errorMsg = `Failed to load details for ${tableName}: ${error.response?.data?.error || error.message}`;
        setPaletteError(errorMsg);
        alert(errorMsg); // Also show alert
    }
  }, [setNodes]); // Include setNodes dependency


  // Function to send schema data to backend
  const sendSchema = useCallback(async () => {
    const schemaData = {
      tables: nodes.map(node => ({
        id: node.id,
        name: node.data.label,
        attributes: node.data.attributes || [],
        position: node.position
      })),
      relationships: edges.map(edge => ({
        id: edge.id,
        sourceTableId: edge.source,
        targetTableId: edge.target,
      }))
    };
    console.log("Sending schema data:", schemaData);
    try {
      const response = await axios.post('http://localhost:5000/api/schema', schemaData);
      console.log('Backend response:', response.data);
      alert(`Schema data sent! Backend says: ${response.data.message}`);
      // Optionally re-fetch existing tables if schema change was successful
      if (response.status === 200 || response.status === 207) {
         // Trigger re-fetch (could be more sophisticated)
         const tablesResponse = await axios.get('http://localhost:5000/api/tables');
         setExistingTables(tablesResponse.data.tables || []);
      }
    } catch (error) {
      console.error('Error sending schema data:', error);
      alert(`Error sending schema data: ${error.response?.data?.error || error.message}`);
    }
  }, [nodes, edges, setExistingTables]); // Add setExistingTables dependency


  // --- Component Render ---
  return (
    <div>
      <h2>Schema Design Canvas</h2>
      {/* Use flexbox for layout */}
      {/* Adjust height calculation as needed, considering header/footer/margins */}
      <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 200px)' }}>
        {/* Canvas Area */}
        <div style={{ flexGrow: 1, border: '1px solid #ccc', marginBottom: '10px', position: 'relative' }}> {/* Added position relative for MiniMap */}
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            fitView
            defaultEdgeOptions={{ markerEnd: { type: MarkerType.ArrowClosed } }}
          >
            <Controls />
            <Background />
            <MiniMap />
          </ReactFlow>
        </div>

        {/* Control Buttons */}
        <div style={{ flexShrink: 0, marginBottom: '10px' }}> {/* Prevent buttons from shrinking */}
           <button onClick={addNode} style={{ marginRight: '5px' }}>Add New Table Node</button>
           <button onClick={sendSchema}>Send Schema to Backend</button>
        </div>

        {/* Existing Tables Palette */}
        <div style={{ flexShrink: 0, borderTop: '1px solid #eee', paddingTop: '10px' }}>
          <h4>Existing Tables (Click to Add to Canvas):</h4>
          {loadingTables && <p>Loading existing tables...</p>}
          {paletteError && <p style={{ color: 'red' }}>Error loading palette: {paletteError}</p>}
          {!loadingTables && !paletteError && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px' }}>
              {existingTables.length > 0 ? (
                existingTables.map(tableName => (
                  <button
                    key={tableName}
                    onClick={() => addNodeFromExisting(tableName)}
                    style={{ padding: '3px 6px', fontSize: '0.9em', cursor: 'pointer', border: '1px solid #ccc', background: '#f0f0f0' }}
                  >
                    {tableName}
                  </button>
                ))
              ) : (
                <p>No existing tables found in database.</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
// --- End Schema Canvas Component ---

// --- Other Page Components (Placeholders) ---
function DataSelection() {
  const [tables, setTables] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchTables = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await axios.get('http://localhost:5000/api/tables');
        setTables(response.data.tables || []);
      } catch (err) {
        console.error("Error fetching tables:", err);
        setError(err.response?.data?.error || err.message || "Failed to fetch tables");
      } finally {
        setLoading(false);
      }
    };
    fetchTables();
  }, []);

  return (
    <div>
      <h2>Data Selection</h2>
      {loading && <p>Loading tables...</p>}
      {error && <p style={{ color: 'red' }}>Error: {error}</p>}
      {!loading && !error && (
        <div>
          <h3>Available Tables:</h3>
          {tables.length > 0 ? (
            <ul>
              {tables.map(table => (
                <li key={table}>{table}</li>
              ))}
            </ul>
          ) : (
            <p>No tables found in the database.</p>
          )}
        </div>
      )}
    </div>
  );
}

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
            <li><Link to="/canvas">Canvas</Link></li> {/* Shortened link */}
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
