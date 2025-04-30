import React, { useState, useCallback, useEffect } from 'react';

import axios from 'axios';
import { v4 as uuidv4 } from 'uuid'; // Import uuid

import '@xyflow/react/dist/style.css';

import '../Styles/App.css';


// --- Normalization Analyzer Component (UPDATED) ---
function NormalizationAnalyzer() {
    // Existing State
    const [allTables, setAllTables] = useState([]);
    const [selectedTable, setSelectedTable] = useState('');
    const [tableColumns, setTableColumns] = useState([]); // Store full column objects {name, type, isPK}
    const [primaryKeyColumns, setPrimaryKeyColumns] = useState([]); // Store just names
    const [functionalDependencies, setFunctionalDependencies] = useState([]); // [{id, determinants:[], dependents:[]}]
    const [currentDeterminants, setCurrentDeterminants] = useState(new Set());
    const [currentDependent, setCurrentDependent] = useState('');
    const [analysisResult, setAnalysisResult] = useState(null); // Stores full analysis result now
    const [isLoadingTables, setIsLoadingTables] = useState(true);
    const [isLoadingColumns, setIsLoadingColumns] = useState(false);
    const [isLoadingAnalysis, setIsLoadingAnalysis] = useState(false);
    const [error, setError] = useState(null); // General errors for analysis/setup
  
    // --- NEW State for Decomposition ---
    const [decomposedSchema, setDecomposedSchema] = useState(null); // Stores results from /api/decompose/*
    const [lostFds, setLostFds] = useState([]); // Specifically for BCNF lost FDs display
    const [isLoadingDecomposition, setIsLoadingDecomposition] = useState(false);
    const [isSavingDecomposition, setIsSavingDecomposition] = useState(false);
    const [saveStatusMessage, setSaveStatusMessage] = useState(null); // Success message for save
    const [saveErrorMessage, setSaveErrorMessage] = useState(null); // Error specific to save operation
  
    // --- Existing useEffect hooks (fetch tables, fetch columns) ---
    // (Keep the existing useEffect hooks for fetching tables and columns)
    // Fetch tables on mount
    useEffect(() => {
        setIsLoadingTables(true);
        axios.get('http://localhost:5000/api/tables')
            .then(response => setAllTables(response.data.tables || []))
            .catch(err => setError(err.response?.data?.error || err.message || "Failed to fetch tables"))
            .finally(() => setIsLoadingTables(false));
    }, []);
  
    // Fetch columns when table changes - RESET decomposition state too
    useEffect(() => {
        if (!selectedTable) {
            setTableColumns([]); setPrimaryKeyColumns([]); setFunctionalDependencies([]);
            setCurrentDeterminants(new Set()); setCurrentDependent('');
            setAnalysisResult(null); setError(null);
            setDecomposedSchema(null); setLostFds([]); // Reset decomposition
            setSaveStatusMessage(null); setSaveErrorMessage(null); // Reset save status
            return;
        }
        setIsLoadingColumns(true); setFunctionalDependencies([]);
        setAnalysisResult(null); setError(null);
        setDecomposedSchema(null); setLostFds([]); // Reset decomposition
        setSaveStatusMessage(null); setSaveErrorMessage(null); // Reset save status
        setCurrentDeterminants(new Set()); setCurrentDependent('');
  
        axios.get(`http://localhost:5000/api/table_details/${selectedTable}`)
            .then(response => {
                const columns = response.data.attributes || [];
                setTableColumns(columns);
                setPrimaryKeyColumns(columns.filter(c => c.isPK).map(c => c.name));
            })
            .catch(err => {
                setError(err.response?.data?.error || err.message || `Failed to fetch columns for ${selectedTable}`);
                setTableColumns([]); setPrimaryKeyColumns([]);
            })
            .finally(() => setIsLoadingColumns(false));
    }, [selectedTable]);
  
  
    // --- Existing FD handling functions ---
    // (Keep handleDeterminantChange, handleDependentChange, addFD, removeFD, formatFD)
     // Handle multi-select for determinants
     const handleDeterminantChange = (e) => {
         const { value, checked } = e.target;
         setCurrentDeterminants(prev => {
             const next = new Set(prev);
             if (checked) {
                 next.add(value);
             } else {
                 next.delete(value);
             }
             return next;
         });
         // If selected determinant is also the current dependent, clear dependent
         if (value === currentDependent && !checked) {
              setCurrentDependent('');
         }
     };
  
     // Handle dependent selection
     const handleDependentChange = (e) => {
         setCurrentDependent(e.target.value);
     };
  
     // Add FD to the list
     const addFD = () => {
         const determinantArray = Array.from(currentDeterminants);
         if (determinantArray.length === 0 || !currentDependent) {
              alert("Please select at least one Determinant column and one Dependent column.");
              return;
         }
         if (determinantArray.includes(currentDependent)) {
             alert("Dependent column cannot be part of the Determinant columns.");
             return;
         }
  
         setFunctionalDependencies(prev => [
             ...prev,
             {
                 id: uuidv4(),
                 determinants: determinantArray,
                 dependents: [currentDependent] // Store dependent as array
             }
         ]);
         // Reset form
         setCurrentDeterminants(new Set());
         setCurrentDependent('');
     };
  
     // Remove FD from the list
     const removeFD = (id) => {
         setFunctionalDependencies(prev => prev.filter(fd => fd.id !== id));
     };
  
     // Helper to display FDs nicely
     const formatFD = ({ determinants, dependents }) => {
         return `{${determinants.join(', ')}} -> {${dependents.join(', ')}}`;
     };
  
     // Filter available columns for dependent dropdown
     const availableDependents = tableColumns.filter(col => !currentDeterminants.has(col.name));
  
  
    // --- UPDATED Analysis function ---
    const handleAnalyze = () => {
        if (!selectedTable) return;
        setIsLoadingAnalysis(true);
        setError(null);
        setAnalysisResult(null); // Clear previous analysis
        setDecomposedSchema(null); // Clear previous decomposition
        setLostFds([]);
        setSaveStatusMessage(null);
        setSaveErrorMessage(null);
  
  
        const payload = {
            table: selectedTable,
            fds: functionalDependencies.map(({ determinants, dependents }) => ({ determinants, dependents }))
        };
  
        console.log("Sending analysis request:", payload);
  
        axios.post('http://localhost:5000/api/analyze_normalization', payload)
            .then(response => {
                console.log("Analysis response:", response.data);
                // Store the entire successful analysis result
                setAnalysisResult(response.data);
            })
            .catch(err => {
                 console.error("Analysis Error:", err);
                 const errorMsg = err.response?.data?.error || err.message || "Normalization analysis failed.";
                 setError(errorMsg); // Set general error
                 setAnalysisResult(null); // Ensure analysis result is null on error
            })
            .finally(() => setIsLoadingAnalysis(false));
    };
  
  
    // --- NEW Decomposition Request Functions ---
    const handleDecomposeRequest = useCallback(async (type) => {
        if (!analysisResult || !analysisResult.tableName) {
            alert("Please run a successful analysis first.");
            return;
        }
        // Check if required info is present in analysisResult
        if (!analysisResult.attributes || !analysisResult.candidateKeys || !analysisResult.processedFds) {
             setError("Analysis result is missing required data for decomposition (attributes, candidateKeys, or processedFds). Backend endpoint '/api/analyze_normalization' might need updating.");
             return;
        }
  
  
        setIsLoadingDecomposition(true);
        setError(null); // Clear general errors
        setDecomposedSchema(null); // Clear previous results
        setLostFds([]);
        setSaveStatusMessage(null);
        setSaveErrorMessage(null);
  
        const endpoint = type === '3NF' ? '/api/decompose/3nf' : '/api/decompose/bcnf';
        const payload = {
            tableName: analysisResult.tableName,
            attributes: analysisResult.attributes, // Pass from analysis result
            candidateKeys: analysisResult.candidateKeys, // Pass from analysis result
            processedFds: analysisResult.processedFds, // Pass from analysis result
        };
  
        console.log(`Sending ${type} decomposition request:`, payload);
  
        try {
            const response = await axios.post(`http://localhost:5000${endpoint}`, payload);
            console.log(`${type} decomposition response:`, response.data);
            setDecomposedSchema(response.data); // Store the decomposition result
            setLostFds(response.data.lost_fds || []); // Store lost FDs if any
        } catch (err) {
            console.error(`${type} Decomposition Error:`, err);
            const errorMsg = err.response?.data?.error || err.message || `Failed to decompose to ${type}.`;
            setError(errorMsg); // Use general error state for decomposition failure
            setDecomposedSchema(null); // Ensure no partial decomposition shown
            setLostFds([]);
        } finally {
            setIsLoadingDecomposition(false);
        }
    }, [analysisResult]); // Dependency on analysisResult
  
  
    // --- NEW Save Decomposition Function ---
    const handleSaveDecomposition = useCallback(async () => {
        if (!decomposedSchema || !decomposedSchema.original_table || !decomposedSchema.decomposed_tables) {
            alert("No valid decomposition result available to save.");
            return;
        }
  
        // Confirmation dialog
        const confirmationMessage = `This will:\n1. Create ${decomposedSchema.decomposed_tables.length} new table(s).\n2. Migrate data from '${decomposedSchema.original_table}'.\n3. DROP the original table '${decomposedSchema.original_table}'.\n\nThis operation is irreversible and might take time. Foreign keys referencing the original table will be lost.\n\nAre you sure you want to proceed?`;
        if (!window.confirm(confirmationMessage)) {
            return;
        }
  
  
        setIsSavingDecomposition(true);
        setSaveStatusMessage(null);
        setSaveErrorMessage(null);
  
        const payload = {
            original_table: decomposedSchema.original_table,
            decomposed_tables: decomposedSchema.decomposed_tables,
        };
  
        console.log("Sending save decomposition request:", payload);
  
        try {
            const response = await axios.post('http://localhost:5000/api/save_decomposition', payload);
            console.log("Save decomposition response:", response.data);
            setSaveStatusMessage(response.data.message || "Decomposition saved successfully!");
            // Reset state after successful save?
            // setSelectedTable(''); // Go back to selecting a table
            setAnalysisResult(null);
            setDecomposedSchema(null);
            setLostFds([]);
            setFunctionalDependencies([]);
            // Optionally trigger a refresh of the main table list if it's stored elsewhere
            // alert("Decomposition saved! The page might require a refresh or re-selecting the table list.");
        } catch (err) {
            console.error("Save Decomposition Error:", err);
            const errorMsg = err.response?.data?.error || err.message || "Failed to save decomposition.";
            setSaveErrorMessage(errorMsg); // Use specific save error state
            // Optionally include details if available:
            if (err.response?.data?.details) {
                console.error("Save Error Details:", err.response.data.details);
                // Potentially display truncated details? Be careful with raw tracebacks.
            }
        } finally {
            setIsSavingDecomposition(false);
        }
    }, [decomposedSchema]); // Dependency on the decomposition result
  
  
    // --- UPDATED Render JSX ---
    return (
        <div className='component-layout'>
            {/* Sidebar */}
            <div className='sidebar'>
                <h3>Normalization Analysis</h3>
                {/* Table Selection (Existing) */}
                <div className='sidebar-section'>
                    <label htmlFor="normTableSelect" style={{ display: 'block', marginBottom: '5px' }}>Table:</label>
                    <select id="normTableSelect" value={selectedTable} onChange={(e) => setSelectedTable(e.target.value)} disabled={isLoadingTables} style={{ width: '100%', padding: '5px' }}>
                        <option value="">-- Select Table --</option>
                        {allTables.map(tableName => (<option key={tableName} value={tableName}>{tableName}</option>))}
                    </select>
                    {isLoadingTables && <p>Loading tables...</p>}
                </div>
  
                {/* Columns & PK Display (Existing) */}
                {selectedTable && !isLoadingColumns && tableColumns.length > 0 && (
                    <div className='sidebar-section'>
                         <strong>Columns:</strong> {tableColumns.map(c => c.name).join(', ')}<br/>
                         <strong>Primary Key:</strong> {primaryKeyColumns.length > 0 ? `{${primaryKeyColumns.join(', ')}}` : 'None Defined!'}
                         {!primaryKeyColumns.length && <span style={{color:'red'}}> (Warning: PK needed for analysis)</span>}
                    </div>
                 )}
                 {isLoadingColumns && <p>Loading columns...</p>}
  
                {/* FD Input Section (Existing) */}
                {selectedTable && !isLoadingColumns && tableColumns.length > 0 && (
                    <div className='sidebar-section'>
                        <h4>Define Functional Dependencies (FDs)</h4>
                        {/* Hint Text (Existing) */}
                        <p style={{fontSize:'0.8em', color:'#666', margin:'0 0 10px 0'}}>
                             {/* ... (Existing hint text) ... */}
                             {'Hint: An FD means knowing values in \'Determinant(s)\' column(s) uniquely tells you the value in the \'Dependent\' column.'} <br/>
                            {'Ex: Knowing `UserID` tells you `Email` (`{UserID} -> {Email}`).'} <br/>
                            {'Ex: Knowing `OrderID` and `ProductID` tells you `Quantity` (`{OrderID, ProductID} -> {Quantity}`).'} <br/>
                            {'(The dependency from the Primary Key to all other columns is assumed automatically).'}
                        </p>
                        {/* Display Added FDs (Existing) */}
                        <div style={{ marginBottom: '10px', maxHeight:'150px', overflowY:'auto', border:'1px solid #eee', padding:'5px' }}>
                            {/* ... (Existing logic to display FDs) ... */}
                            <strong>Defined FDs:</strong>
                            {functionalDependencies.length === 0 ? (
                                <p style={{fontSize:'0.85em', fontStyle:'italic', color:'#888'}}>No user-defined FDs yet.</p>
                            ) : (
                                <ul style={{margin:0, paddingLeft:'20px'}}>
                                    {functionalDependencies.map(fd => (
                                        <li key={fd.id} style={{fontSize:'0.9em', marginBottom:'3px'}}>
                                            {formatFD(fd)}
                                            <button onClick={() => removeFD(fd.id)} title="Remove FD" style={{ marginLeft: '10px', color: 'red', border: 'none', background: 'none', cursor: 'pointer', padding: '0 2px' }}>X</button>
                                        </li>
                                    ))}
                                </ul>
                            )}
                        </div>
                        {/* Add FD Form (Existing) */}
                        <div style={{borderTop:'1px solid #eee', paddingTop:'10px'}}>
                            {/* ... (Existing Add FD Form) ... */}
                            <h5>Add New Dependency Rule:</h5>
                             <div style={{marginBottom:'5px'}}>
                                 <label style={{fontWeight:'bold', fontSize:'0.9em'}}>Determinant(s) (IF I know...):</label>
                                 <div style={{maxHeight:'100px', overflowY:'auto', border:'1px solid #ccc', padding:'5px', background:'white'}}>
                                    {tableColumns.map(col => (
                                        <div key={`det-${col.name}`}>
                                            <input
                                                type="checkbox"
                                                id={`det-cb-${col.name}`}
                                                value={col.name}
                                                checked={currentDeterminants.has(col.name)}
                                                onChange={handleDeterminantChange}
                                                style={{marginRight:'5px'}}
                                                disabled={col.name === currentDependent} // Cannot be both
                                            />
                                            <label htmlFor={`det-cb-${col.name}`}>{col.name}</label>
                                        </div>
                                    ))}
                                 </div>
                             </div>
                             <div style={{margin:'5px 0', textAlign:'center', fontWeight:'bold'}}> → </div>
                              <div style={{marginBottom:'10px'}}>
                                 <label htmlFor="dependentSelect" style={{fontWeight:'bold', fontSize:'0.9em'}}>Dependent (THEN I know...):</label>
                                  <select
                                      id="dependentSelect"
                                      value={currentDependent}
                                      onChange={handleDependentChange}
                                      style={{ width: '100%', padding: '5px', marginTop:'3px' }}
                                      disabled={currentDeterminants.size === 0}
                                  >
                                      <option value="">-- Select Dependent Column --</option>
                                      {availableDependents.map(col => (
                                          <option key={col.name} value={col.name}>{col.name}</option>
                                      ))}
                                  </select>
                             </div>
                              <button onClick={addFD} style={{ width: '100%'}} disabled={currentDeterminants.size === 0 || !currentDependent}>+ Add Dependency Rule</button>
                        </div>
                    </div>
                )}
  
                {/* Sticky Analyze Button (Existing) */}
                <div className='sidebar-sticky-bottom'>
                    <button onClick={handleAnalyze} style={{ width: '100%', padding: '12px 0' }}
                        disabled={!selectedTable || isLoadingColumns || isLoadingAnalysis || isLoadingDecomposition || isSavingDecomposition || !primaryKeyColumns.length} // Disable during various loading states
                    >
                        {isLoadingAnalysis ? 'Analyzing...' : 'Analyze Normalization'}
                    </button>
                    {isLoadingColumns && <p style={{fontSize: '0.8em', color: '#888', textAlign:'center', marginTop:'5px'}}>Loading columns...</p>}
                    {!primaryKeyColumns?.length && selectedTable && !isLoadingColumns && <p style={{fontSize: '0.8em', color: 'red', textAlign:'center', marginTop:'5px'}}>Cannot analyze: Table needs a Primary Key.</p>}
                </div>
            </div> {/* End Sidebar */}
  
            {/* Main Content Area - Analysis Results */}
            <div className='main-content'>
                <h2>Normalization Results {analysisResult?.tableName && `for ${analysisResult.tableName}`}</h2>
  
                {/* Loading/Error Display (Existing & New) */}
                {isLoadingAnalysis && <p>Analyzing...</p>}
                {error && <p className='error-message'>Error: {error}</p>}
                {/* Display specific save error */}
                {saveErrorMessage && <p className='error-message'>Save Error: {saveErrorMessage}</p>}
                {/* Display specific save success */}
                {saveStatusMessage && <p className='success-message'>{saveStatusMessage}</p>}
  
  
                {/* Analysis Result Display (Existing) */}
                {analysisResult && !error && (
                     <div style={{ marginBottom: '20px', borderBottom: '1px solid #ccc', paddingBottom: '15px' }}>
                        {/* Display Keys (Existing) */}
                         <div style={{ marginBottom: '15px', background:'#f8f8f8', padding:'8px', border:'1px solid #eee' }}>
                              {/* ... (Existing Key display) ... */}
                             <strong>Primary Key:</strong> {analysisResult.primaryKey?.length > 0 ? `{${analysisResult.primaryKey.join(', ')}}` : 'None Defined'}<br/>
                              <strong>Candidate Keys Found:</strong>
                              {analysisResult.candidateKeys?.length > 0 ? (
                                 analysisResult.candidateKeys.map((ck, idx) => <span key={idx} style={{marginLeft:'5px', display:'inline-block', background:'#eee', padding:'2px 4px', borderRadius:'3px'}}>{`{${ck.join(', ')}}`}</span> )
                              ) : (
                                 <span style={{fontStyle:'italic'}}> Only Primary Key considered (or analysis failed).</span>
                              )}
                         </div>
  
                         {/* Display Analysis per Normal Form (Existing) */}
                         {Object.entries(analysisResult.analysis || {}).map(([nf, result]) => (
                             <div key={nf} style={{ border: '1px solid #ccc', padding: '10px', marginBottom: '10px', background: result.status?.includes('VIOLATION') ? '#ffdddd' : (result.status?.includes('COMPLIANT') ? '#ddffdd' : '#fffadf') }}>
                                 {/* ... (Existing NF Status Display) ... */}
                                 <h4 style={{ marginTop: 0, marginBottom: '5px' }}>{nf} Status:
                                     <span style={{fontWeight:'bold', marginLeft:'5px'}}>
                                        {result.status?.replace(/_/g, ' ')}
                                    </span>
                                 </h4>
                                 <p style={{fontSize:'0.9em', margin:'0 0 5px 0'}}>{result.message}</p>
                                 {result.violations && result.violations.length > 0 && (
                                     <div style={{marginTop:'5px'}}>
                                         <strong>Violations Found:</strong>
                                         <ul style={{margin:'3px 0 0 0', paddingLeft:'20px'}}>
                                             {result.violations.map((v, i) => <li key={i} style={{fontSize:'0.9em', color:'red'}}>{v}</li>)}
                                         </ul>
                                     </div>
                                 )}
                             </div>
                         ))}
  
                         {/* Display Notes (Existing) */}
                         {analysisResult.notes && analysisResult.notes.length > 0 && (
                             <div style={{borderTop:'1px dashed #ccc', paddingTop:'10px', marginTop:'15px'}}>
                                  {/* ... (Existing Notes Display) ... */}
                                 <strong>Notes:</strong>
                                  <ul style={{margin:'3px 0 0 0', paddingLeft:'20px'}}>
                                     {analysisResult.notes.map((n, i) => <li key={i} style={{fontSize:'0.9em', color:'#555'}}>{n}</li>)}
                                 </ul>
                             </div>
                         )}
                    </div>
                )}
  
                {/* --- NEW Decomposition Section --- */}
                {analysisResult && !error && (
                  <div style={{ marginBottom: '20px' }}>
                      <h4>Decomposition Options</h4>
                      {/* Buttons to trigger decomposition */}
                      <div style={{ display: 'flex', gap: '10px', marginBottom: '15px' }}>
                          <button
                              onClick={() => handleDecomposeRequest('3NF')}
                              disabled={isLoadingAnalysis || isLoadingDecomposition || isSavingDecomposition}
                              style={{backgroundColor: '#ffc107', borderColor: '#ffc107'}} // Example style: Yellowish
                          >
                              {isLoadingDecomposition ? 'Decomposing...' : 'Calculate 3NF Decomposition'}
                          </button>
                          <button
                              onClick={() => handleDecomposeRequest('BCNF')}
                              disabled={isLoadingAnalysis || isLoadingDecomposition || isSavingDecomposition}
                               style={{backgroundColor: '#fd7e14', borderColor: '#fd7e14'}} // Example style: Orange
                          >
                              {isLoadingDecomposition ? 'Decomposing...' : 'Calculate BCNF Decomposition'}
                          </button>
                      </div>
  
                       {/* Display Decomposition Results */}
                       {isLoadingDecomposition && <p>Calculating decomposition...</p>}
                       {decomposedSchema && !isLoadingDecomposition && (
                           <div style={{ marginTop: '15px', border: '1px solid #adb5bd', borderRadius:'5px', padding: '15px', background:'#f8f9fa' }}>
                               <h5>Proposed {decomposedSchema.decomposition_type} Decomposition:</h5>
                               {decomposedSchema.decomposed_tables?.map((table, index) => (
                                   <div key={index} style={{ marginBottom: '10px', borderBottom: '1px dashed #dee2e6', paddingBottom:'10px' }}>
                                       <strong>Table: {table.new_table_name}</strong>
                                       <ul style={{ fontSize: '0.9em', margin: '5px 0 0 20px', padding: 0, listStyle: 'none' }}>
                                           <li>Attributes: <code>{table.attributes.join(', ')}</code></li>
                                           <li>Primary Key: <code>{`{${table.primary_key.join(', ')}}`}</code></li>
                                       </ul>
                                   </div>
                               ))}
  
                               {/* Display Lost FDs (Especially for BCNF) */}
                               {lostFds && lostFds.length > 0 && (
                                   <div style={{ marginTop: '15px', border: '1px solid #ffc107', background: '#fff3cd', padding: '10px', borderRadius:'4px' }}>
                                       <strong>Warning: Lost Functional Dependencies (BCNF):</strong>
                                       <ul style={{ fontSize: '0.9em', margin: '5px 0 0 20px', paddingLeft: '15px', color: '#856404' }}>
                                           {lostFds.map((fdStr, index) => (
                                               <li key={index}>{fdStr}</li>
                                           ))}
                                       </ul>
                                        <p style={{fontSize:'0.8em', color:'#856404', marginTop:'5px'}}>These dependencies might not hold after decomposition and saving.</p>
                                   </div>
                               )}
  
                               {/* Save Button and Warning */}
                               <div style={{ marginTop: '20px', borderTop: '1px solid #ccc', paddingTop: '15px' }}>
                                  <p style={{ fontSize: '0.9em', color: 'red', fontWeight: 'bold' }}>
                                      Warning: Saving this decomposition will permanently drop the original table '{decomposedSchema.original_table}'
                                      and migrate data to the new tables. Any foreign keys referencing the original table will be lost. This cannot be undone easily.
                                  </p>
                                   <button
                                       onClick={handleSaveDecomposition}
                                       disabled={isSavingDecomposition || isLoadingDecomposition}
                                       style={{ backgroundColor: '#dc3545', borderColor: '#dc3545' }} // Red for dangerous action
                                   >
                                       {isSavingDecomposition ? 'Saving...' : `Save ${decomposedSchema.decomposition_type} Decomposition`}
                                   </button>
                               </div>
                           </div>
                       )}
                  </div>
                )}
  
  
                {/* Initial Message (Existing) */}
                {!isLoadingAnalysis && !analysisResult && !error && !saveStatusMessage && !saveErrorMessage && (
                    <p>Select a table and define its functional dependencies (if any beyond the PK) using the sidebar, then click "Analyze Normalization".</p>
                )}
  
            </div> {/* End Main Content */}
        </div> // End component-layout
    );
  }

  export default NormalizationAnalyzer;
  // --- END Normalization Analyzer Component ---