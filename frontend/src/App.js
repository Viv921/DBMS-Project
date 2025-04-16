import React, { useState, useCallback, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import axios from 'axios';
import { v4 as uuidv4 } from 'uuid'; // Import uuid
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

// --- Data Selection Component --- (UPDATED) ---
function DataSelection() {
  const [allTables, setAllTables] = useState([]);
  const [selectedTables, setSelectedTables] = useState({}); // { tableName: { attributes: [], selectedColumns: Set() } }
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [queryResults, setQueryResults] = useState(null);
  const [queryError, setQueryError] = useState(null);
  const [isQuerying, setIsQuerying] = useState(false);

  // --- NEW STATE ---
  const [joins, setJoins] = useState([]); // Array of { id, type, leftTable, leftCol, rightTable, rightCol }
  const [whereClauses, setWhereClauses] = useState([]); // Array of { id, table, column, operator, value }
  const [aggregates, setAggregates] = useState([]); // Array of { id, func, table, column, alias }
  const [groupByColumns, setGroupByColumns] = useState(new Set()); // Set of "tableName.columnName"

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
      // Avoid refetch if details already exist
      if (selectedTables[tableName]?.attributes) {
          console.log(`Details for ${tableName} already loaded.`);
          return;
      }
       // Check if already fetching (simple lock)
       if (selectedTables[tableName] && selectedTables[tableName].attributes === 'fetching') {
          console.log(`Details for ${tableName} are currently being fetched.`);
          return;
       }

      console.log(`Workspaceing details for ${tableName}...`);
      setSelectedTables(prev => ({
          ...prev,
          [tableName]: { attributes: 'fetching', selectedColumns: new Set() } // Mark as fetching
      }));

      try {
          const response = await axios.get(`http://localhost:5000/api/table_details/${tableName}`);
          const details = response.data;
          if (details && details.attributes) {
              console.log(`Successfully fetched details for ${tableName}`);
              setSelectedTables(prev => ({
                  ...prev,
                  [tableName]: {
                      attributes: details.attributes,
                      selectedColumns: new Set(details.attributes.map(attr => attr.name)) // Select all by default
                  }
              }));
          } else {
               throw new Error("Invalid data received for table details.");
          }
      } catch (err) {
          console.error(`Error fetching details for ${tableName}:`, err);
          setError(prev => `${prev ? prev + '; ' : ''}Failed to fetch details for ${tableName}`);
          // Remove the table from selection or mark as error
          setSelectedTables(prev => {
              const newState = {...prev};
              delete newState[tableName]; // Remove on error
              return newState;
          });
      }
  }, [selectedTables]); // Add selectedTables as dependency

  // Handle selecting/deselecting a table
   const toggleTableSelection = useCallback((tableName) => {
      setSelectedTables(prevSelected => {
          const newSelected = { ...prevSelected };
          if (newSelected[tableName]) {
              // Deselect: Remove table and related joins, filters, aggregates, group bys
              console.log(`Deselecting table: ${tableName}`);
              delete newSelected[tableName];
              setJoins(prev => prev.filter(j => j.leftTable !== tableName && j.rightTable !== tableName));
              setWhereClauses(prev => prev.filter(w => w.table !== tableName));
              setAggregates(prev => prev.filter(a => a.table !== tableName));
              setGroupByColumns(prev => {
                  const newSet = new Set(prev);
                  prev.forEach(col => {
                      if (col.startsWith(`${tableName}.`)) {
                          newSet.delete(col);
                      }
                  });
                  return newSet;
              });

          } else {
              // Select: Add placeholder and trigger detail fetch
              console.log(`Selecting table: ${tableName}`);
              newSelected[tableName] = { attributes: null, selectedColumns: new Set() }; // Placeholder
              fetchTableDetails(tableName); // Trigger detail fetch
          }
          return newSelected;
      });
  }, [fetchTableDetails]); // Dependency

  // Handle selecting/deselecting a column
  const toggleColumnSelection = (tableName, columnName) => {
      setSelectedTables(prevSelected => {
          if (!prevSelected[tableName] || !prevSelected[tableName].attributes || prevSelected[tableName].attributes === 'fetching') return prevSelected;

          const currentTable = prevSelected[tableName];
          const newSelectedColumns = new Set(currentTable.selectedColumns);

          if (newSelectedColumns.has(columnName)) {
              newSelectedColumns.delete(columnName);
              // Also remove from Group By if it was there
              setGroupByColumns(prev => {
                   const newSet = new Set(prev);
                   newSet.delete(`${tableName}.${columnName}`);
                   return newSet;
              })
          } else {
              newSelectedColumns.add(columnName);
          }

          return {
              ...prevSelected,
              [tableName]: { ...currentTable, selectedColumns: newSelectedColumns }
          };
      });
  };

  // --- Handler Functions for New State ---

  // Joins
  const addJoin = () => setJoins(prev => [...prev, { id: uuidv4(), type: 'INNER', leftTable: '', leftCol: '', rightTable: '', rightCol: '' }]);
  const updateJoin = (id, field, value) => {
      setJoins(prev => prev.map(j => j.id === id ? { ...j, [field]: value } : j));
      // Reset columns if table changes
      if (field === 'leftTable' || field === 'rightTable') {
           setJoins(prev => prev.map(j => j.id === id ? { ...j, leftCol: '', rightCol: '' } : j));
      }
  };
  const removeJoin = (id) => setJoins(prev => prev.filter(j => j.id !== id));

  // Where Clauses
  const addWhereClause = () => setWhereClauses(prev => [...prev, { id: uuidv4(), table: '', column: '', operator: '=', value: '' }]);
  const updateWhereClause = (id, field, value) => {
       setWhereClauses(prev => prev.map(w => w.id === id ? { ...w, [field]: value } : w));
       // Reset column if table changes
       if (field === 'table') {
           setWhereClauses(prev => prev.map(w => w.id === id ? { ...w, column: '' } : w));
       }
  };
  const removeWhereClause = (id) => setWhereClauses(prev => prev.filter(w => w.id !== id));

  // Aggregates
  const addAggregate = () => setAggregates(prev => [...prev, { id: uuidv4(), func: 'COUNT', table: '', column: '*', alias: '' }]);
  const updateAggregate = (id, field, value) => {
      setAggregates(prev => prev.map(a => a.id === id ? { ...a, [field]: value } : a));
       // Reset column if table changes
       if (field === 'table') {
           setAggregates(prev => prev.map(a => a.id === id ? { ...a, column: '*' } : a));
       }
  };
  const removeAggregate = (id) => {
      setAggregates(prev => prev.filter(a => a.id !== id));
      // If removing last aggregate, clear Group By
      if (aggregates.length === 1) {
          setGroupByColumns(new Set());
      }
  };

  // Group By
  const toggleGroupByColumn = (tableName, columnName) => {
       const qualifiedCol = `${tableName}.${columnName}`;
       setGroupByColumns(prev => {
          const newSet = new Set(prev);
          if (newSet.has(qualifiedCol)) {
              newSet.delete(qualifiedCol);
          } else {
              // Only allow grouping by columns that are selected AND NOT aggregated
              const isAggregated = aggregates.some(agg => agg.table === tableName && agg.column === columnName);
              const isSelected = selectedTables[tableName]?.selectedColumns.has(columnName);
               if (isSelected && !isAggregated) {
                   newSet.add(qualifiedCol);
               } else {
                  alert(`Column "${qualifiedCol}" cannot be used for Group By. Ensure it is selected and not already aggregated.`);
               }
          }
          return newSet;
       });
  };

  // --- Available Columns for Dropdowns ---
  const getAvailableColumns = (targetTable = null) => {
      let cols = [];
      Object.entries(selectedTables).forEach(([tableName, details]) => {
          if (details?.attributes && details.attributes !== 'fetching' && (!targetTable || tableName === targetTable)) {
              details.attributes.forEach(attr => {
                  cols.push({ table: tableName, name: attr.name, qualified: `${tableName}.${attr.name}` });
              });
          }
      });
      return cols;
  };

  const getColumnsForTable = (tableName) => {
       return selectedTables[tableName]?.attributes !== 'fetching' && selectedTables[tableName]?.attributes
          ? selectedTables[tableName].attributes
          : [];
  }

  // Get columns eligible for GROUP BY (selected, not aggregated)
   const getGroupableColumns = () => {
      let groupable = [];
      Object.entries(selectedTables).forEach(([tableName, details]) => {
          if (details?.selectedColumns && details.attributes !== 'fetching') {
              details.selectedColumns.forEach(colName => {
                  const isAggregated = aggregates.some(agg => agg.table === tableName && agg.column === colName);
                  if (!isAggregated) {
                      groupable.push({ table: tableName, name: colName, qualified: `${tableName}.${colName}` });
                  }
              });
          }
      });
      return groupable;
   };


  // --- Updated runQuery Function ---
// Inside DataSelection component

const runQuery = useCallback(async () => {
  setIsQuerying(true); setQueryError(null); setQueryResults(null);

  // --- DETAILED DEBUG LOGS ---
  console.log("--- State inside runQuery ---");
  console.log("selectedTables:", JSON.stringify(selectedTables, null, 2)); // Log the full structure
  console.log("joins:", JSON.stringify(joins));
  console.log("whereClauses:", JSON.stringify(whereClauses));
  console.log("aggregates:", JSON.stringify(aggregates));
  console.log("groupByColumns:", JSON.stringify(Array.from(groupByColumns)));
  console.log("----------------------------");
  // --- END DEBUG LOGS ---

  // 1. Construct query definition object
  const finalSelectedColumns = [];
  const groupByColsArray = Array.from(groupByColumns);

  if (aggregates.length > 0) {
    console.log("Building SELECT for aggregates...");
    aggregates.forEach(agg => {
        console.log("Processing aggregate item from state:", JSON.stringify(agg)); // Log the raw item from state

        if(selectedTables[agg.table]) {
            // Construct the object explicitly before pushing
            const aggregateSelectItem = {
                type: 'aggregate',
                func: agg.func,
                table: agg.table,
                column: agg.column,
                alias: agg.alias || '' // Ensure alias is at least an empty string if undefined/null
            };

            // Log the object *just before* it's pushed
            console.log("--> Pushing aggregate select item:", JSON.stringify(aggregateSelectItem));

            finalSelectedColumns.push(aggregateSelectItem); // Push the constructed object

        } else {
             console.warn(`Aggregate references table "${agg.table}" which is not selected or ready.`);
        }
    });

       groupByColsArray.forEach(qualifiedCol => {
           const [table, column] = qualifiedCol.split('.');
           if(selectedTables[table]) { // Check table exists
              finalSelectedColumns.push({ type: 'column', table, column });
           } else {
               console.warn(`Group By references table "${table}" which is not selected or ready.`);
           }
       });
  } else {
       console.log("Building SELECT for plain columns...");
       Object.entries(selectedTables).forEach(([tableName, details]) => {
           console.log(`Processing table for select: ${tableName}`, details); // Log details object
           // Check if attributes are loaded and selectedColumns exist
           if (details?.attributes && details.attributes !== 'fetching' && details.selectedColumns instanceof Set) {
               details.selectedColumns.forEach(columnName => {
                   finalSelectedColumns.push({ type: 'column', table: tableName, column: columnName });
               });
           } else {
                console.warn(`Skipping columns for table "${tableName}" - details not ready or selectedColumns missing/invalid.`);
           }
       });
  }
  console.log("Final selected columns for queryDef:", finalSelectedColumns);

  // Ensure fromTables is derived correctly
  const fromTables = Object.keys(selectedTables).filter(tableName =>
      selectedTables[tableName]?.attributes && selectedTables[tableName]?.attributes !== 'fetching'
  );
   console.log("Final 'from' tables for queryDef:", fromTables);

  const queryDef = {
      select: finalSelectedColumns,
      from: fromTables, // Use the filtered list
      // Filter joins/where more carefully - ensure tables involved are in the 'fromTables' list
       joins: joins.filter(j => j.leftTable && j.leftCol && j.rightTable && j.rightCol && j.type && fromTables.includes(j.leftTable) && fromTables.includes(j.rightTable)),
       where: whereClauses.filter(w => w.table && w.column && w.operator && fromTables.includes(w.table)),
       groupBy: groupByColsArray.filter(qualifiedCol => { // Ensure groupBy tables are also in fromTables
           const [table] = qualifiedCol.split('.');
           return fromTables.includes(table);
       }),
  };

  // This log should now show the populated object
  console.log("Constructed Query Definition:", JSON.stringify(queryDef, null, 2));

  // Basic check before sending
  if (!queryDef.from || queryDef.from.length === 0 || !queryDef.select || queryDef.select.length === 0) {
       console.error("Query definition is incomplete. Aborting request.");
       setQueryError("Cannot build query. Please select tables and columns.");
       setIsQuerying(false);
       return; // Stop before sending empty/invalid request
  }

  try {
       console.log("Sending query request to backend...");
       const response = await axios.post('http://localhost:5000/api/execute_select', queryDef);
       console.log("Received response from backend:", response.data);
       setQueryResults(response.data);

  } catch (error) {
      // ... (existing error handling) ...
       console.error("Error running query:", error);
       const errorMsg = error.response?.data?.error || error.message || "Failed to execute query";
       setQueryError(errorMsg);
       if (error.response?.data?.sql_attempted) {
            console.error("SQL Attempted:", error.response.data.sql_attempted);
       }
  } finally {
       setIsQuerying(false);
  }

}, [selectedTables, joins, whereClauses, aggregates, groupByColumns]); // Dependencies remain the same
  const selectedTableNames = Object.keys(selectedTables);
  const allColumns = getAvailableColumns(); // All columns from all selected tables
  const requiresJoin = Object.keys(selectedTables).length > 1 && joins.filter(j => j.leftTable && j.leftCol && j.rightTable && j.rightCol && j.type).length === 0;
  const isAnyTableLoading = Object.values(selectedTables).some(details => details?.attributes === 'fetching');

  return (
      <div style={{ display: 'flex', height: 'calc(100vh - 100px)' }}> {/* Adjust height */}
          {/* Sidebar */}
          <div style={{ width: '350px', borderRight: '1px solid #ccc', padding: '10px', overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
              <h3>Tables</h3>
              {loading && <p>Loading tables...</p>}
              {error && <p style={{ color: 'red' }}>Error: {error}</p>}
              {!loading && !error && (
                  <ul style={{ listStyle: 'none', padding: 0, margin: 0, marginBottom: '15px' }}>
                      {allTables.length > 0 ? (
                          allTables.map(tableName => (
                              <li key={tableName} style={{ marginBottom: '5px' }}>
                                  <label title={`Click to ${selectedTables[tableName] ? 'deselect' : 'select'} ${tableName}`}>
                                      <input
                                          type="checkbox"
                                          checked={!!selectedTables[tableName]}
                                          onChange={() => toggleTableSelection(tableName)}
                                          style={{ marginRight: '5px' }}
                                           disabled={selectedTables[tableName]?.attributes === 'fetching'} // Disable while fetching
                                      />
                                      {tableName}
                                       {selectedTables[tableName]?.attributes === 'fetching' && <em style={{fontSize: '0.8em', color: '#888'}}> (loading...)</em>}
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
                      {joins.map((join, index) => (
                          <div key={join.id} style={{ border: '1px solid #ddd', padding: '5px', marginBottom: '5px', fontSize: '0.9em' }}>
                              <select value={join.type} onChange={e => updateJoin(join.id, 'type', e.target.value)} style={{ marginRight: '3px' }}>
                                  <option value="INNER">INNER JOIN</option>
                                  <option value="LEFT">LEFT JOIN</option>
                                  <option value="RIGHT">RIGHT JOIN</option>
                              </select>
                              <select value={join.leftTable} onChange={e => updateJoin(join.id, 'leftTable', e.target.value)} style={{ marginRight: '3px', maxWidth: '80px' }}>
                                  <option value="">Left Table</option>
                                  {selectedTableNames.map(t => <option key={t} value={t}>{t}</option>)}
                              </select>
                              .
                              <select value={join.leftCol} onChange={e => updateJoin(join.id, 'leftCol', e.target.value)} style={{ marginRight: '3px', maxWidth: '80px' }} disabled={!join.leftTable}>
                                  <option value="">Col</option>
                                   {join.leftTable && getColumnsForTable(join.leftTable).map(col => <option key={col.name} value={col.name}>{col.name}</option>)}
                              </select>
                              =
                              <select value={join.rightTable} onChange={e => updateJoin(join.id, 'rightTable', e.target.value)} style={{ marginLeft: '3px', marginRight: '3px', maxWidth: '80px' }}>
                                  <option value="">Right Table</option>
                                  {selectedTableNames.map(t => <option key={t} value={t}>{t}</option>)}
                              </select>
                              .
                              <select value={join.rightCol} onChange={e => updateJoin(join.id, 'rightCol', e.target.value)} style={{ maxWidth: '80px' }} disabled={!join.rightTable}>
                                  <option value="">Col</option>
                                  {join.rightTable && getColumnsForTable(join.rightTable).map(col => <option key={col.name} value={col.name}>{col.name}</option>)}
                              </select>
                              <button onClick={() => removeJoin(join.id)} style={{ marginLeft: '5px', color: 'red', border: 'none', background: 'none', cursor: 'pointer' }}>X</button>
                          </div>
                      ))}
                      <button onClick={addJoin} style={{ fontSize: '0.8em' }}>+ Add Join</button>
                  </div>
              )}

              {/* Columns / Filters Section */}
              {selectedTableNames.length >= 1 && (
                  <div style={{ borderTop: '1px solid #eee', paddingTop: '10px', marginBottom: '15px' }}>
                      <h4>Columns & Filters</h4>
                      {selectedTableNames.map(tableName => (
                          <div key={tableName} style={{ marginBottom: '10px' }}>
                              <strong>{tableName}:</strong>
                              {selectedTables[tableName]?.attributes === 'fetching' ? (
                                   <p style={{fontSize: '0.9em', color: '#888', margin: '5px 0 0 15px'}}>Loading columns...</p>
                              ) : selectedTables[tableName]?.attributes ? (
                                  <ul style={{ listStyle: 'none', paddingLeft: '15px', marginTop: '5px', marginBottom: '5px' }}>
                                      {selectedTables[tableName].attributes.map(attr => (
                                          <li key={`${tableName}-${attr.name}`}>
                                              <label title={aggregates.some(a => a.table === tableName && a.column === attr.name) ? "Cannot select aggregated column directly" : ""}>
                                                  <input
                                                      type="checkbox"
                                                      checked={selectedTables[tableName].selectedColumns.has(attr.name)}
                                                      onChange={() => toggleColumnSelection(tableName, attr.name)}
                                                      style={{ marginRight: '5px' }}
                                                      disabled={aggregates.some(a => a.table === tableName && a.column === attr.name)} // Disable if aggregated
                                                  />
                                                  {attr.name} <span style={{fontSize: '0.8em', color: '#666'}}>({attr.type})</span>
                                              </label>
                                          </li>
                                      ))}
                                  </ul>
                              ) : ( <p style={{fontSize: '0.9em', color: '#888', margin: '5px 0 0 15px'}}>Select table to see columns.</p> )
                              }
                          </div>
                      ))}
                       {/* WHERE Clauses */}
                      <div style={{ borderTop: '1px solid #eee', paddingTop: '10px', marginTop:'10px' }}>
                          <h5>Filters (WHERE)</h5>
                           {whereClauses.map((clause) => (
                              <div key={clause.id} style={{ display: 'flex', alignItems: 'center', marginBottom: '5px', fontSize: '0.9em' }}>
                                  <select value={clause.table} onChange={e => updateWhereClause(clause.id, 'table', e.target.value)} style={{ maxWidth: '80px', marginRight:'3px' }}>
                                       <option value="">Table</option>
                                       {selectedTableNames.map(t => <option key={t} value={t}>{t}</option>)}
                                  </select>
                                  <select value={clause.column} onChange={e => updateWhereClause(clause.id, 'column', e.target.value)} style={{ maxWidth: '80px', marginRight:'3px' }} disabled={!clause.table}>
                                      <option value="">Column</option>
                                       {clause.table && getColumnsForTable(clause.table).map(col => <option key={col.name} value={col.name}>{col.name}</option>)}
                                  </select>
                                  <select value={clause.operator} onChange={e => updateWhereClause(clause.id, 'operator', e.target.value)} style={{ width: '50px', marginRight:'3px' }}>
                                      <option value="=">=</option> <option value="!=">!=</option>
                                      <option value=">">&gt;</option> <option value="<">&lt;</option>
                                      <option value=">=">&gt;=</option> <option value="<=">&lt;=</option>
                                      <option value="LIKE">LIKE</option> <option value="NOT LIKE">NOT LIKE</option>
                                      <option value="IS NULL">IS NULL</option> <option value="IS NOT NULL">IS NOT NULL</option>
                                  </select>
                                  <input
                                      type="text"
                                      value={clause.value}
                                      onChange={e => updateWhereClause(clause.id, 'value', e.target.value)}
                                      placeholder="Value"
                                      style={{ flexGrow: 1, marginRight:'3px', minWidth: '50px' }}
                                      disabled={clause.operator === 'IS NULL' || clause.operator === 'IS NOT NULL'}
                                  />
                                  <button onClick={() => removeWhereClause(clause.id)} style={{ color: 'red', border: 'none', background: 'none', cursor: 'pointer' }}>X</button>
                              </div>
                          ))}
                          <button onClick={addWhereClause} style={{ fontSize: '0.8em' }}>+ Add Filter</button>
                      </div>
                  </div>
              )}

              {/* Aggregates Section */}
              {selectedTableNames.length >= 1 && (
                  <div style={{ borderTop: '1px solid #eee', paddingTop: '10px', marginBottom: '15px' }}>
                      <h4>Aggregates</h4>
                       {aggregates.map((agg) => (
                          <div key={agg.id} style={{ display: 'flex', alignItems: 'center', marginBottom: '5px', fontSize: '0.9em' }}>
                              <select value={agg.func} onChange={e => updateAggregate(agg.id, 'func', e.target.value)} style={{ width: '70px', marginRight:'3px' }}>
                                  <option value="COUNT">COUNT</option> <option value="SUM">SUM</option>
                                  <option value="AVG">AVG</option> <option value="MIN">MIN</option>
                                  <option value="MAX">MAX</option>
                              </select>
                              (
                               <select value={agg.table} onChange={e => updateAggregate(agg.id, 'table', e.target.value)} style={{ maxWidth: '80px', margin:'0 3px' }}>
                                  <option value="">Table</option>
                                  {selectedTableNames.map(t => <option key={t} value={t}>{t}</option>)}
                              </select>
                              .
                              <select value={agg.column} onChange={e => updateAggregate(agg.id, 'column', e.target.value)} style={{ maxWidth: '80px', margin:'0 3px' }} disabled={!agg.table}>
                                   {/* Allow '*' for COUNT, otherwise list columns */}
                                  <option value="*">* (All)</option>
                                   {agg.table && getColumnsForTable(agg.table).map(col => <option key={col.name} value={col.name}>{col.name}</option>)}
                              </select>
                              ) AS
                              <input
                                  type="text" value={agg.alias}
                                  onChange={e => updateAggregate(agg.id, 'alias', e.target.value)}
                                  placeholder="alias (optional)"
                                  style={{ flexGrow: 1, marginLeft:'3px', marginRight:'3px', minWidth:'50px' }}
                              />
                              <button onClick={() => removeAggregate(agg.id)} style={{ color: 'red', border: 'none', background: 'none', cursor: 'pointer' }}>X</button>
                          </div>
                       ))}
                      <button onClick={addAggregate} style={{ fontSize: '0.8em' }}>+ Add Aggregate</button>
                  </div>
              )}

              {/* Group By Section */}
              {aggregates.length > 0 && (
                  <div style={{ borderTop: '1px solid #eee', paddingTop: '10px', marginBottom: '15px' }}>
                      <h4>Group By</h4>
                       <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                           {getGroupableColumns().map(col => (
                               <li key={col.qualified}>
                                   <label>
                                       <input
                                           type="checkbox"
                                           checked={groupByColumns.has(col.qualified)}
                                           onChange={() => toggleGroupByColumn(col.table, col.name)}
                                           style={{ marginRight: '5px' }}
                                       />
                                       {col.qualified}
                                   </label>
                               </li>
                           ))}
                            {getGroupableColumns().length === 0 && <li style={{fontSize:'0.9em', color:'#888'}}>No columns available to group by (select non-aggregated columns).</li>}
                       </ul>
                  </div>
              )}

              {/* Inform user if joins are required */}
              {requiresJoin &&
                     <p style={{color: 'orange', fontSize: '0.9em', textAlign: 'center', border: '1px solid orange', padding: '3px', margin:'5px 0'}}>
                         Please define JOIN conditions for multiple tables.
                     </p>
                 }

              {/* Query Button */}
              {/* Sticky container for the query button */}
                <div style={{
                    // Remove marginTop: 'auto'
                    position: 'sticky',          // Make the container stick
                    bottom: 0,                 // Stick it to the bottom of the scrolling parent
                    background: 'white',       // Add a background color
                    padding: '15px 10px 10px 10px', // Adjust padding (Top, Right, Bottom, Left)
                    borderTop: '1px solid #eee', // Keep the visual separator
                    marginTop: '10px',           // Add space above when content is short
                 }}>
                    <button
                        onClick={runQuery}
                        style={{ width: '100%', padding: '12px 0' }}
                        // Updated disabled condition:
                        disabled={
                            Object.keys(selectedTables).length === 0 || // No tables selected
                            isQuerying || // Query already running
                            isAnyTableLoading || // Details are loading
                            requiresJoin // <<-- Add this check
                        }
                    >
                        {isQuerying ? 'Running...' : 'Run Query'}
                    </button>
                     {/* Optional: Show loading indicator */}
                     {isAnyTableLoading && <p style={{fontSize: '0.8em', color: '#888', textAlign:'center'}}>Loading table details...</p>}
                </div>
            </div>

          {/* Main Content Area - Results */}
          <div style={{ flexGrow: 1, padding: '10px', overflow: 'auto' }}> {/* Make results scrollable too */}
              <h2>Query Results</h2>
              {isQuerying && <p>Executing query...</p>}
              {queryError && <p style={{ color: 'red' }}>Query Error: {queryError}</p>}
              {queryResults ? (
                  queryResults.rows && queryResults.rows.length > 0 ? (
                   <table border="1" style={{ borderCollapse: 'collapse', width: '100%' }}>
                       <thead>
                           <tr>
                               {queryResults.columns.map((colName, index) => <th key={index}>{colName}</th>)}
                           </tr>
                       </thead>
                       <tbody>
                           {queryResults.rows.map((row, rowIndex) => (
                               <tr key={rowIndex}>
                                   {row.map((cell, cellIndex) => <td key={cellIndex}>{cell === null ? <i>NULL</i> : String(cell)}</td>)}
                               </tr>
                           ))}
                       </tbody>
                   </table>
                  ) : ( <p>Query executed successfully, but returned no rows.</p> )
              ) : (
                  !isQuerying && !queryError && <p>Define your query using the sidebar and click "Run Query".</p>
              )}
               {/* Debug view of state */}
               {/* <pre style={{fontSize:'0.7em', background:'#f0f0f0', marginTop:'20px'}}>
                    State Debug:
                    Joins: {JSON.stringify(joins, null, 2)}
                    Where: {JSON.stringify(whereClauses, null, 2)}
                    Aggregates: {JSON.stringify(aggregates, null, 2)}
                    Group By: {JSON.stringify(Array.from(groupByColumns), null, 2)}
               </pre> */}
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
