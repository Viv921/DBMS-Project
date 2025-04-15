import React, { useState, useCallback, useEffect } from 'react'; // Added useEffect
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import axios from 'axios'; // Import axios
import { // Changed from default import to named import
  ReactFlow,
  Controls,
  Background,
  applyNodeChanges,
  applyEdgeChanges,
  addEdge,
  MiniMap, // Optional: Add minimap
  MarkerType, // Import MarkerType for edge arrows
} from '@xyflow/react';
import TableNode from './TableNode'; // Import the custom node
import '@xyflow/react/dist/style.css'; // Import React Flow styles

import './App.css';

// Define custom node types
const nodeTypes = { tableNode: TableNode };

// Placeholder components for pages
function LandingPage() {
  return (
    <div>
      <h1>Welcome to the MySQL Visual UI</h1>
      <p>Select an option:</p>
      <nav>
        <ul>
          <li><Link to="/canvas">Schema Design Canvas</Link></li>
          {/* Add links to other sections later */}
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
// Initial node setup using the custom type and data structure
const initialNodes = [
  {
    id: '1',
    position: { x: 50, y: 50 },
    data: {
      label: 'users',
      attributes: [
        { name: 'id', type: 'INT', isPK: true, isNotNull: true, isUnique: true }, // Example initial node with new fields
        { name: 'username', type: 'VARCHAR(255)', isPK: false, isNotNull: true, isUnique: true }, // Example
      ]
    },
    type: 'tableNode' // Use the custom node type
  },
];
let nodeId = 2; // Counter for unique node IDs

function SchemaCanvas() {
  const [nodes, setNodes] = useState(initialNodes);
  const [edges, setEdges] = useState([]);

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
    // Add directed arrow marker to new edges
    (connection) => setEdges((eds) => addEdge({ ...connection, markerEnd: { type: MarkerType.ArrowClosed } }, eds)),
    [setEdges]
  );

  // Function to add a new node
  const addNode = useCallback(() => {
    const newId = `${nodeId++}`;
    const newNode = {
      id: newId,
      position: {
        x: Math.random() * 400, // Random position
        y: Math.random() * 400,
      },
      data: { // Include default attributes for the custom node
        label: `NewTable_${newId}`,
        attributes: [{ name: 'id', type: 'INT', isPK: true, isNotNull: true, isUnique: true }] // Add defaults for new node
      },
      type: 'tableNode', // Specify the custom node type
    };
    setNodes((nds) => nds.concat(newNode));
  }, []);

  // Function to send schema data to backend
  const sendSchema = useCallback(async () => {
    // In a real app, you'd structure this data more meaningfully
    // Extract detailed data from nodes and edges
    const schemaData = {
      tables: nodes.map(node => ({
        id: node.id, // Keep node id for reference if needed
        name: node.data.label,
        attributes: node.data.attributes || [], // Ensure attributes array exists
        position: node.position // Optional: keep position for layout saving
      })),
      // Map edges to represent foreign keys (source table has FK pointing to target table PK)
      relationships: edges.map(edge => ({
        id: edge.id,
        sourceTableId: edge.source, // ID of the table containing the FK
        targetTableId: edge.target, // ID of the table being referenced (PK)
        // Future: Add specific column mapping if needed
      }))
    };
    console.log("Sending schema data:", schemaData);
    try {
      const response = await axios.post('http://localhost:5000/api/schema', schemaData);
      console.log('Backend response:', response.data);
      alert(`Schema data sent! Backend says: ${response.data.message}`);
    } catch (error) {
      console.error('Error sending schema data:', error);
      alert(`Error sending schema data: ${error.response?.data?.error || error.message}`);
    }
  }, [nodes, edges]); // Depend on nodes and edges

  return (
    <div>
      <h2>Schema Design Canvas</h2>
      <div style={{ height: '500px', border: '1px solid #ccc' }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes} // Pass custom node types
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          fitView // Zoom/pan to fit nodes initially
          // Default edge options can also include markers
          defaultEdgeOptions={{ markerEnd: { type: MarkerType.ArrowClosed } }}
        >
          <Controls />
          <Background />
          <MiniMap /> {/* Optional */}
        </ReactFlow>
      </div>
      <button onClick={addNode} style={{ marginTop: '10px', marginRight: '5px' }}>Add Table Node</button>
      <button onClick={sendSchema} style={{ marginTop: '10px' }}>Send Schema to Backend</button>
    </div>
  );
}
// --- End Schema Canvas Component ---

// --- Data Selection Component ---
function DataSelection() {
  const [tables, setTables] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    // Fetch tables when component mounts
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
  }, []); // Empty dependency array means this runs once on mount

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
                // Future: Add checkboxes or buttons to select tables/columns
              ))}
            </ul>
          ) : (
            <p>No tables found in the database.</p>
          )}
          {/* Placeholder for column selection, joins, conditions */}
        </div>
      )}
    </div>
  );
}
// --- End Data Selection Component ---

function CrudOperations() {
  return <h2>CRUD Operations (Placeholder)</h2>;
}

function Transactions() {
  return <h2>Transactions (Placeholder)</h2>;
}

function Normalization() {
  return <h2>Normalization Analyzer (Placeholder)</h2>;
}


function App() {
  return (
    <Router>
      <div className="App">
        {/* Basic Navigation (can be moved to a layout component later) */}
        <nav>
          <ul>
            <li><Link to="/">Home</Link></li>
            {/* Maybe add a top-level nav later if needed */}
          </ul>
        </nav>
        <hr />

        {/* Define application routes */}
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/canvas" element={<SchemaCanvas />} />
          <Route path="/select" element={<DataSelection />} />
          <Route path="/crud" element={<CrudOperations />} />
          <Route path="/transactions" element={<Transactions />} />
          <Route path="/normalization" element={<Normalization />} />
          {/* Add routes for other sections */}
        </Routes>
      </div>
    </Router>
  );
}

export default App;
