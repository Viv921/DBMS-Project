import React, { useState, useCallback, useEffect } from 'react';
import axios from 'axios';
import { v4 as uuidv4 } from 'uuid'; // Import uuid

import '@xyflow/react/dist/style.css';

import '../Styles/App.css';


// --- NEW CRUD Operations Component ---
function CrudOperations() {
    const [crudOperation, setCrudOperation] = useState('INSERT'); // 'INSERT', 'UPDATE', 'DELETE'
    const [allTables, setAllTables] = useState([]);
    const [selectedTable, setSelectedTable] = useState('');
    const [tableColumns, setTableColumns] = useState([]);
    const [primaryKeyColumn, setPrimaryKeyColumn] = useState(null); // Store PK column name
  
    // State for form data (using a single object might be easier)
    const [rowsData, setRowsData] = useState([{ id: uuidv4() }]); // Holds values for INSERT (array) / UPDATE SET (first element)
    // Example Structure:
    // INSERT: [{id: uuid, col1: 'val1', col2: 'val2'}, ...]
    // UPDATE: [{id: uuid, set_col1: 'new1', set_col2: 'new2'}] (UI uses first row)
  
    // State for WHERE clauses in UPDATE/DELETE
    const [dmlWhereClauses, setDmlWhereClauses] = useState([]); // Now: [{ id, column, operator, value, connector: 'AND' | 'OR' | null }]
  
  
    const [tableDisplayData, setTableDisplayData] = useState(null); // { columns: [], rows: [] }
    const [isLoadingTables, setIsLoadingTables] = useState(true);
    const [isLoadingColumns, setIsLoadingColumns] = useState(false);
    const [isExecuting, setIsExecuting] = useState(false);
    const [isShowingTable, setIsShowingTable] = useState(false);
    const [error, setError] = useState(null);
    const [successMessage, setSuccessMessage] = useState(null);
  
    // Fetch tables on mount
    useEffect(() => {
        const fetchTables = async () => {
            setIsLoadingTables(true); setError(null);
            try {
                const response = await axios.get('http://localhost:5000/api/tables');
                setAllTables(response.data.tables || []);
            } catch (err) {
                setError(err.response?.data?.error || err.message || "Failed to fetch tables");
                setAllTables([]);
            } finally {
                setIsLoadingTables(false);
            }
        };
        fetchTables();
    }, []);
  
    // Fetch columns when table selection changes
    useEffect(() => {
        if (!selectedTable) {
            setTableColumns([]);
            setPrimaryKeyColumn(null);
            setRowsData([{ id: uuidv4() }]); // Reset to one empty row
            setDmlWhereClauses([]); // Clear WHERE
            return;
        }
  
        const fetchColumns = async () => {
            setIsLoadingColumns(true);
            setTableColumns([]);
            setPrimaryKeyColumn(null);
            setError(null);
            setSuccessMessage(null);
            setTableDisplayData(null); // Clear previous table view
            setRowsData([{ id: uuidv4() }]); // Reset rows data
            setDmlWhereClauses([]); // Clear WHERE
  
            try {
                const response = await axios.get(`http://localhost:5000/api/table_details/${selectedTable}`);
                const columns = response.data.attributes || [];
                setTableColumns(columns);
                // Find and store the primary key column name
                const pkCol = columns.find(col => col.isPK);
                setPrimaryKeyColumn(pkCol ? pkCol.name : null);
  
                // Initialize rowsData with one empty row, keys based on columns
                 const initialRow = { id: uuidv4() };
                 columns.forEach(col => { initialRow[col.name] = ''; });
                 setRowsData([initialRow]);
  
            } catch (err) {
                setError(err.response?.data?.error || err.message || `Failed to fetch columns for ${selectedTable}`);
                setTableColumns([]);
                 setPrimaryKeyColumn(null);
                 setRowsData([{ id: uuidv4() }]);
                 setDmlWhereClauses([]);
            } finally {
                setIsLoadingColumns(false);
            }
        };
        fetchColumns();
    }, [selectedTable]); // Refetch if table changes
  
     // Reset form state when operation changes
     const handleOperationChange = (e) => {
        const newOperation = e.target.value;
        setCrudOperation(newOperation);
        setError(null);
        setSuccessMessage(null);
        setTableDisplayData(null);
        setDmlWhereClauses([]); // Clear WHERE
        // Initialize rowsData based on new operation and existing columns
        const initialRow = { id: uuidv4() };
        tableColumns.forEach(col => { initialRow[col.name] = ''; });
        setRowsData([initialRow]);
     };
  
  
    // Handle input changes for INSERT/UPDATE SET data
    const handleInputChange = (rowIndex, columnName, value) => {
        setRowsData(prevRows =>
            prevRows.map((row, index) => {
                if (index === rowIndex) {
                    return { ...row, [columnName]: value };
                }
                return row;
            })
        );
    };
  
    // --- Handlers for DML WHERE Clauses ---
    const addDmlWhereClause = () => setDmlWhereClauses(prev => [
      ...prev,
      {
          id: uuidv4(),
          column: '',
          operator: '=',
          value: '',
          connector: prev.length > 0 ? 'AND' : null // Default to AND, null for first
      }
    ]);
  
    const updateDmlWhereClause = (id, field, value) => {
        setDmlWhereClauses(prev => prev.map(w => {
            if (w.id === id) {
                const updated = { ...w, [field]: value };
                if (field === 'operator' && (value === 'IS NULL' || value === 'IS NOT NULL')) {
                      updated.value = '';
                }
                return updated;
            }
            return w;
        }));
    };
  
    const removeDmlWhereClause = (id) => {
        setDmlWhereClauses(prev => {
            const remaining = prev.filter(w => w.id !== id);
            if (remaining.length > 0 && remaining[0].connector !== null) {
                remaining[0] = { ...remaining[0], connector: null };
            }
            return remaining;
        });
    };
  
    // Add/Remove Row Handlers for INSERT
    const addRow = () => {
        const newRow = { id: uuidv4() };
        tableColumns.forEach(col => { newRow[col.name] = ''; });
        setRowsData(prevRows => [...prevRows, newRow]);
    };
  
    const removeRow = (rowId) => {
        if (rowsData.length <= 1 && crudOperation === 'INSERT') { // Keep last row for insert
            alert("Cannot remove the last row for Insert.");
            return;
        }
        setRowsData(prevRows => prevRows.filter(row => row.id !== rowId));
    };
  
  
    // Show Table Data
    const showTableData = useCallback(async () => {
        if (!selectedTable) return;
        setIsShowingTable(true); setError(null); setSuccessMessage(null); setTableDisplayData(null);
  
        const columnsToSelect = tableColumns.length > 0
            ? tableColumns.map(col => ({ type: 'column', table: selectedTable, column: col.name }))
            : [{ type: 'column', table: selectedTable, column: '*' }];
  
        const queryDef = {
            select: columnsToSelect,
            from: [selectedTable],
            joins: [], where: [], groupBy: []
        };
  
        try {
            console.log("Sending request to fetch table data:", queryDef);
            const response = await axios.post('http://localhost:5000/api/execute_select', queryDef);
            console.log("Received table data:", response.data);
            setTableDisplayData(response.data);
        } catch (error) {
            console.error("Error fetching table data:", error);
            const errorMsg = error.response?.data?.error || error.message || "Failed to fetch table data";
            setError(errorMsg);
            setTableDisplayData(null);
        } finally {
            setIsShowingTable(false);
        }
    }, [selectedTable, tableColumns]);
  
    // Execute DML Operation
    const executeOperation = useCallback(async () => {
        if (!selectedTable) { setError("Please select a table."); return; }
  
        // Safety Check: Require at least one WHERE clause for UPDATE/DELETE
        const validWhereClauses = dmlWhereClauses.filter(w=>w.column && w.operator);
           if ((crudOperation === 'UPDATE' || crudOperation === 'DELETE') && validWhereClauses.length === 0) {
               setError(`WHERE condition(s) are required for ${crudOperation}.`); return;
           }
  
        setIsExecuting(true); setError(null); setSuccessMessage(null);
  
        let payload = { operation: crudOperation, table: selectedTable };
  
        try {
            if (crudOperation === 'INSERT') {
                const valuesArray = rowsData.map(row => {
                     const rowValues = {};
                     tableColumns.forEach(col => {
                        // Send null if value is undefined or empty string? Adjust as needed.
                        // MySQL typically treats empty string as empty string, not NULL unless column type forces it.
                        rowValues[col.name] = row[col.name] !== undefined ? row[col.name] : null;
                     });
                     return rowValues;
                 }).filter(rowObj => Object.values(rowObj).some(val => val !== '' && val !== null)); // Filter out rows where all values are empty/null
  
                 if (valuesArray.length === 0) throw new Error("No valid rows provided for INSERT (all rows were empty).");
                 payload.values = valuesArray;
  
            } else if (crudOperation === 'UPDATE') {
                 const setData = {};
                 const firstRow = rowsData[0] || {}; // UI uses first row for SET values
                 let hasSetData = false;
                 tableColumns.forEach(col => {
                    // Only include non-PK columns that have a value entered
                    // Check explicitly against empty string ''
                    if (firstRow[col.name] !== undefined && firstRow[col.name] !== '') {
                        // We might allow updating PKs, but usually not advised. Check col.isPK if needed.
                        setData[col.name] = firstRow[col.name];
                        hasSetData = true;
                    }
                 });
                 if (!hasSetData) throw new Error("No values provided to update (SET clause is empty).");
  
                 payload.set = setData;
                 payload.where = validWhereClauses.map(({ id, ...rest }) => rest); // Send array without temporary id
  
  
            } else if (crudOperation === 'DELETE') {
                 payload.where = validWhereClauses.map(({ id, ...rest }) => rest); // Send array without temporary id
            }
  
            console.log(`Executing ${crudOperation}:`, payload);
            const response = await axios.post('http://localhost:5000/api/execute_dml', payload);
            console.log("DML Response:", response.data);
            setSuccessMessage(response.data.message || `${crudOperation} completed.`);
            // Clear form state on success
            if (crudOperation === 'INSERT') {
                 const initialRow = { id: uuidv4() }; tableColumns.forEach(col => { initialRow[col.name] = ''; }); setRowsData([initialRow]);
            } else {
                setDmlWhereClauses([]); // Clear where clauses
                // Optionally clear SET fields for UPDATE?
                 const initialRow = { id: uuidv4() }; tableColumns.forEach(col => { initialRow[col.name] = ''; }); setRowsData([initialRow]);
            }
  
        } catch (error) {
             console.error(`Error executing ${crudOperation}:`, error);
             const errorMsg = error.response?.data?.error || error.message || `Failed to execute ${crudOperation}`;
             setError(errorMsg);
             setSuccessMessage(null);
        } finally {
            setIsExecuting(false);
        }
  
    }, [crudOperation, selectedTable, tableColumns, rowsData, dmlWhereClauses]); // Update dependencies
  
  
    // --- Render Input Fields Dynamically ---
    const renderFormFields = () => {
        if (isLoadingColumns) return <p>Loading columns...</p>;
        if (!selectedTable) return <p>Select a table to perform operations.</p>;
        if (tableColumns.length === 0 && !isLoadingColumns) return <p>Could not load columns for this table.</p>;
  
        switch (crudOperation) {
            case 'INSERT':
                return (
                    <div>
                        <h5>Insert Row(s):</h5>
                        {rowsData.map((row, rowIndex) => (
                            <div key={row.id} style={{ border: '1px solid #eee', padding: '10px', marginBottom: '10px', position:'relative' }}>
                               {rowsData.length > 1 && ( // Show remove button only if more than one row
                                 <button
                                      onClick={() => removeRow(row.id)}
                                      title="Remove this row"
                                      style={{ position:'absolute', top:'5px', right:'5px', background:'#ff4d4d', color:'white', border:'none', borderRadius:'50%', width:'20px', height:'20px', cursor:'pointer', lineHeight:'18px', padding:0, fontSize:'10px'}} >
                                     X
                                 </button>
                               )}
                                {tableColumns.map(col => (
                                    <div key={`${row.id}-${col.name}`} style={{ marginBottom: '8px' }}>
                                        <label style={{ display: 'block', marginBottom: '3px', fontSize: '0.9em' }}>
                                            {col.name} <span style={{ color: '#777' }}>({col.type})</span>
                                            {col.isPK && <span style={{ color: 'purple', fontWeight:'bold' }}> (PK)</span>}
                                            {col.isNotNull && !col.isPK && <span style={{ color: 'red' }}> *</span>} {/* Indicate required */}
                                        </label>
                                        <input
                                            type={col.type.includes('INT') ? 'number' : col.type.includes('DATE') ? 'date' : 'text'}
                                            name={col.name}
                                            value={row[col.name] || ''}
                                            onChange={(e) => handleInputChange(rowIndex, col.name, e.target.value)}
                                            style={{ width: '95%', padding: '4px' }}
                                            placeholder={`${col.name} value`}
                                            // Disable PK input if it's typically auto-generated? Needs more schema info.
                                            // disabled={col.isPK /* && isAutoIncrement? */}
                                        />
                                    </div>
                                ))}
                            </div>
                        ))}
                        <button onClick={addRow} style={{ marginTop: '5px', fontSize:'0.9em' }}>+ Add Another Row</button>
                    </div>
                );
  
            case 'UPDATE':
                 const firstRowForUpdate = rowsData[0] || {}; // UI uses first row for SET values
                   return (
                      <div>
                          {/* WHERE Clause Builder */}
                          <div style={{ borderBottom: '1px solid #eee', paddingBottom: '10px', marginBottom: '10px' }}>
                             <h5>WHERE Conditions (Required):</h5>
                             <p style={{fontSize:'0.8em', color:'orange'}}>Warning: Ensure conditions accurately target ONLY rows you intend to update.</p>
                              {/* Map over dmlWhereClauses to render each condition row */}
                              {dmlWhereClauses.map((clause, index) => (
                                  <React.Fragment key={clause.id}>
                                      {/* Render AND/OR selector between conditions */}
                                      {index > 0 && (
                                          <div style={{ margin: '5px 0 5px 20px', fontSize:'0.8em' }}>
                                              <select
                                                  value={clause.connector || 'AND'}
                                                  onChange={e => updateDmlWhereClause(clause.id, 'connector', e.target.value)}
                                                  style={{ padding:'2px', marginRight:'5px'}}
                                              >
                                                  <option value="AND">AND</option>
                                                  <option value="OR">OR</option>
                                              </select>
                                               <span>Condition {index + 1}:</span>
                                          </div>
                                      )}
                                      {/* Render inputs for the condition */}
                                      <div style={{ display: 'flex', alignItems: 'center', marginBottom: '5px', fontSize: '0.9em', paddingLeft: index > 0 ? '20px' : '0' }}>
                                          {/* Column Dropdown */}
                                          <select value={clause.column} onChange={e => updateDmlWhereClause(clause.id, 'column', e.target.value)} style={{ flexBasis: '100px', marginRight:'3px', flexShrink: 0 }}>
                                              <option value="">Column</option>
                                              {tableColumns.map(col => <option key={col.name} value={col.name}>{col.name}</option>)}
                                          </select>
                                          {/* Operator Dropdown */}
                                          <select value={clause.operator} onChange={e => updateDmlWhereClause(clause.id, 'operator', e.target.value)} style={{ width: '70px', marginRight:'3px', flexShrink: 0 }}>
                                              <option value="=">=</option> <option value="!=">!=</option>
                                              <option value=">">&gt;</option> <option value="<">&lt;</option>
                                              <option value=">=">&gt;=</option> <option value="<=">&lt;=</option>
                                              <option value="LIKE">LIKE</option> <option value="NOT LIKE">NOT LIKE</option>
                                              <option value="IS NULL">IS NULL</option> <option value="IS NOT NULL">IS NOT NULL</option>
                                          </select>
                                          {/* Value Input */}
                                          <input type="text" value={clause.value} onChange={e => updateDmlWhereClause(clause.id, 'value', e.target.value)} placeholder="Value" style={{ flexGrow: 1, marginRight:'3px', minWidth: '50px' }} disabled={clause.operator === 'IS NULL' || clause.operator === 'IS NOT NULL'} />
                                          {/* Remove Button */}
                                          <button onClick={() => removeDmlWhereClause(clause.id)} title="Remove condition" style={{ color: 'red', border: 'none', background: 'none', cursor: 'pointer', padding: '0 5px' }}>X</button>
                                      </div>
                                  </React.Fragment>
                              ))}
                              {/* Button to add a new WHERE condition */}
                              <button onClick={addDmlWhereClause} style={{ fontSize: '0.8em', marginLeft: '20px' }}>+ Add WHERE Condition</button>
                          </div>
  
                          {/* SET Clause Inputs */}
                          <h5>New Values (SET):</h5>
                          {/* Map over table columns to render inputs for SET values */}
                          {tableColumns.map(col => (
                              <div key={`set_${col.name}`} style={{ marginBottom: '8px' }}>
                                  <label style={{ display: 'block', marginBottom: '3px', fontSize: '0.9em' }}>
                                      {col.name} <span style={{ color: '#777' }}>({col.type})</span> {col.isPK && <span style={{ color: 'purple', fontWeight:'bold' }}> (PK - Caution!)</span>}
                                  </label>
                                  <input
                                      type={col.type.includes('INT') ? 'number' : col.type.includes('DATE') ? 'date' : 'text'}
                                      name={col.name}
                                      value={firstRowForUpdate[col.name] || ''} // Value from first row state
                                      onChange={(e) => handleInputChange(0, col.name, e.target.value)} // Update first row state
                                      style={{ width: '95%', padding: '4px' }}
                                      placeholder={`New value for ${col.name} (leave blank to ignore)`}
                                  />
                              </div>
                          ))}
                      </div>
                  );
            case 'DELETE':
              return (
                <div>
                    {/* WHERE Clause Builder */}
                    <h5>WHERE Conditions (Required):</h5>
                    <p style={{fontSize:'0.8em', color:'red'}}>Warning: Deletion is permanent! Ensure conditions accurately target ONLY rows you intend to delete.</p>
                     {/* Map over dmlWhereClauses to render each condition row */}
                     {dmlWhereClauses.map((clause, index) => (
                          <React.Fragment key={clause.id}>
                               {/* Render AND/OR selector */}
                                {index > 0 && (
                                    <div style={{ margin: '5px 0 5px 20px', fontSize:'0.8em' }}>
                                        <select value={clause.connector || 'AND'} onChange={e => updateDmlWhereClause(clause.id, 'connector', e.target.value)} style={{ padding:'2px', marginRight:'5px'}}> <option value="AND">AND</option> <option value="OR">OR</option> </select>
                                         <span>Condition {index + 1}:</span>
                                    </div>
                                )}
                                {/* Render inputs for the condition */}
                                <div style={{ display: 'flex', alignItems: 'center', marginBottom: '5px', fontSize: '0.9em', paddingLeft: index > 0 ? '20px' : '0' }}>
                                    {/* Column Dropdown */}
                                     <select value={clause.column} onChange={e => updateDmlWhereClause(clause.id, 'column', e.target.value)} style={{ flexBasis: '100px', marginRight:'3px', flexShrink: 0 }}>
                                         <option value="">Column</option>
                                         {tableColumns.map(col => <option key={col.name} value={col.name}>{col.name}</option>)}
                                     </select>
                                     {/* Operator Dropdown */}
                                     <select value={clause.operator} onChange={e => updateDmlWhereClause(clause.id, 'operator', e.target.value)} style={{ width: '70px', marginRight:'3px', flexShrink: 0 }}>
                                         <option value="=">=</option> <option value="!=">!=</option>
                                         <option value=">">&gt;</option> <option value="<">&lt;</option>
                                         <option value=">=">&gt;=</option> <option value="<=">&lt;=</option>
                                         <option value="LIKE">LIKE</option> <option value="NOT LIKE">NOT LIKE</option>
                                         <option value="IS NULL">IS NULL</option> <option value="IS NOT NULL">IS NOT NULL</option>
                                     </select>
                                     {/* Value Input */}
                                     <input type="text" value={clause.value} onChange={e => updateDmlWhereClause(clause.id, 'value', e.target.value)} placeholder="Value" style={{ flexGrow: 1, marginRight:'3px', minWidth: '50px' }} disabled={clause.operator === 'IS NULL' || clause.operator === 'IS NOT NULL'} />
                                     {/* Remove Button */}
                                     <button onClick={() => removeDmlWhereClause(clause.id)} title="Remove condition" style={{ color: 'red', border: 'none', background: 'none', cursor: 'pointer', padding: '0 5px' }}>X</button>
                                </div>
                          </React.Fragment>
                     ))}
                     {/* Button to add a new WHERE condition */}
                     <button onClick={addDmlWhereClause} style={{ fontSize: '0.8em', marginLeft: '20px' }}>+ Add WHERE Condition</button>
                </div>
            );
            default:
                return null;
        }
    };
  
  
    // --- Return JSX ---
    const validWhereClausesEntered = dmlWhereClauses.filter(w=>w.column && w.operator).length > 0;
  
    return (
         <div className='component-layout'>
            {/* Sidebar */}
            <div className='sidebar'>
                 <h3>DML Operations</h3>
                 {/* Operation Selection */}
                 <div className='sidebar-section'>
                     <label style={{ marginRight: '10px' }}><input type="radio" value="INSERT" checked={crudOperation === 'INSERT'} onChange={handleOperationChange} /> Insert</label>
                     <label style={{ marginRight: '10px' }}><input type="radio" value="UPDATE" checked={crudOperation === 'UPDATE'} onChange={handleOperationChange} /> Update</label>
                     <label><input type="radio" value="DELETE" checked={crudOperation === 'DELETE'} onChange={handleOperationChange} /> Delete</label>
                 </div>
                 {/* Table Selection */}
                 <div className='sidebar-section'>
                     <label htmlFor="crudTableSelect" style={{ display: 'block', marginBottom: '5px' }}>Table:</label>
                     <select id="crudTableSelect" value={selectedTable} onChange={(e) => setSelectedTable(e.target.value)} disabled={isLoadingTables} style={{ width: '100%', padding: '5px' }}>
                         <option value="">-- Select Table --</option>
                         {allTables.map(tableName => (<option key={tableName} value={tableName}>{tableName}</option>))}
                     </select>
                     {isLoadingTables && <p>Loading tables...</p>}
                 </div>
                 {/* Dynamic Form Area */}
                 <div style={{ borderTop: '1px solid #eee', paddingTop: '10px', flexGrow: 1 }}>
                    {renderFormFields()}
                 </div>
                 {/* Sticky Buttons Container */}
                 <div className='sidebar-sticky-bottom'>
                     {/* Show Table Button */}
                     <button onClick={showTableData} style={{ width: '100%', padding: '12px 0', marginBottom: '10px' }} disabled={!selectedTable || isShowingTable || isExecuting}>
                         {isShowingTable ? 'Loading Table...' : 'Show Table Data'}
                     </button>
                     {/* Execute Button */}
                     <button
                         onClick={executeOperation}
                         style={{ width: '100%', padding: '12px 0', background: crudOperation === 'DELETE' ? '#e60000' : (crudOperation === 'UPDATE' ? '#e6e600' : '#00e600') }}
                         disabled={
                             !selectedTable || isLoadingColumns || isExecuting || isShowingTable ||
                             // Disable UPDATE/DELETE if no valid WHERE clauses are entered
                             ((crudOperation === 'UPDATE' || crudOperation === 'DELETE') && !validWhereClausesEntered)
                         }
                     >
                         {isExecuting ? 'Executing...' : `Execute ${crudOperation}`}
                     </button>
                     {isLoadingColumns && <p style={{fontSize: '0.8em', color: '#888', textAlign:'center', marginTop:'5px'}}>Loading columns...</p>}
                 </div>
            </div>
             {/* Main Content Area */}
             <div className='main-content'>
                 <h2>{selectedTable ? `${selectedTable} - ${crudOperation}` : 'CRUD Operations'}</h2>
                 {error && <p className='error-message'>Error: {error}</p>}
                 {successMessage && <p className='success-message'>Success: {successMessage}</p>}
  
                 {/* Corrected conditional rendering for table display */}
                 {tableDisplayData ? (
                     tableDisplayData.rows && tableDisplayData.rows.length > 0 ? (
                         <table border="1" style={{ borderCollapse: 'collapse', width: '100%', marginTop: '15px' }}>
                             <thead>
                                 <tr>{tableDisplayData.columns.map((colName, index) => <th key={index}>{colName}</th>)}</tr>
                             </thead>
                             <tbody>
                                 {tableDisplayData.rows.map((row, rowIndex) => (
                                     <tr key={rowIndex}>
                                         {row.map((cell, cellIndex) => <td key={cellIndex}>{cell === null ? <i>NULL</i> : String(cell)}</td>)}
                                     </tr>
                                 ))}
                             </tbody>
                         </table>
                     ) : ( <p style={{ marginTop: '15px' }}>Table is empty or query returned no rows.</p> )
                 ) : ( !error && !successMessage && <p style={{ marginTop: '15px' }}>Select a table and operation, or click "Show Table Data".</p> )}
            </div>
        </div>
    );
  }

  export default CrudOperations;
  // --- END CRUD Operations Component ---