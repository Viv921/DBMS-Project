import React, { useState, useCallback, useEffect } from 'react';
import axios from 'axios';
import { v4 as uuidv4 } from 'uuid'; // Import uuid

import '@xyflow/react/dist/style.css';

import '../Styles/App.css';

// --- Constants from backend (can be fetched or defined here) ---
const ALLOWED_AGGREGATES = ['COUNT', 'SUM', 'AVG', 'MIN', 'MAX'];
const ALLOWED_OPERATORS = ['=', '!=', '>', '<', '>=', '<=', 'LIKE', 'NOT LIKE', 'IS NULL', 'IS NOT NULL'];
const ALLOWED_ORDER_DIRECTIONS = ['ASC', 'DESC'];

// --- NEW: CSV Export Helper Function ---
const escapeCsvCell = (cell) => {
    if (cell == null) { // handles null and undefined
        return '';
    }
    const cellStr = String(cell);
    // Check if the cell contains characters that require quoting (, " \n)
    if (cellStr.includes(',') || cellStr.includes('"') || cellStr.includes('\n')) {
        // Enclose in double quotes and escape existing double quotes by doubling them
        return `"${cellStr.replace(/"/g, '""')}"`;
    }
    return cellStr;
};

// --- Data Selection Component --- (UPDATED with HAVING and ORDER BY - Attempt 2: Preserve Visuals) ---
function DataSelection() {
    const [allTables, setAllTables] = useState([]);
    const [selectedTables, setSelectedTables] = useState({}); // { tableName: { attributes: [], selectedColumns: Set() } }
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [queryResults, setQueryResults] = useState(null);
    const [queryError, setQueryError] = useState(null);
    const [isQuerying, setIsQuerying] = useState(false);

    // --- Existing State ---
    const [joins, setJoins] = useState([]); // Array of { id, type, leftTable, leftCol, rightTable, rightCol }
    const [whereClauses, setWhereClauses] = useState([]); //Arry of [{ id, table, column, operator, value, connector: 'AND' | 'OR' | null }]
    const [aggregates, setAggregates] = useState([]); // Array of { id, func, table, column, alias }
    const [groupByColumns, setGroupByColumns] = useState(new Set()); // Set of "tableName.columnName"

    // --- NEW STATE for HAVING and ORDER BY ---
    const [havingClauses, setHavingClauses] = useState([]); // Array of { id, func?, columnOrAlias, operator, value, connector: 'AND' | 'OR' | null }
    const [orderByClauses, setOrderByClauses] = useState([]); // Array of { id, term, direction }

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
        if (selectedTables[tableName]?.attributes && selectedTables[tableName]?.attributes !== 'fetching') {
            // console.log(`Details for ${tableName} already loaded.`); // Keep console logs minimal unless debugging
            return;
        }
         // Check if already fetching (simple lock)
         if (selectedTables[tableName] && selectedTables[tableName].attributes === 'fetching') {
            // console.log(`Details for ${tableName} are currently being fetched.`);
            return;
         }

        // console.log(`Fetching details for ${tableName}...`);
        setSelectedTables(prev => ({
            ...prev,
            [tableName]: { attributes: 'fetching', selectedColumns: new Set() } // Mark as fetching
        }));

        try {
            const response = await axios.get(`http://localhost:5000/api/table_details/${tableName}`);
            const details = response.data;
            if (details && details.attributes) {
                // console.log(`Successfully fetched details for ${tableName}`);
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

    // Handle selecting/deselecting a table - *Includes necessary cleanup logic for new state*
     const toggleTableSelection = useCallback((tableName) => {
        setSelectedTables(prevSelected => {
            const newSelected = { ...prevSelected };
            const isSelecting = !newSelected[tableName];

            if (isSelecting) {
                // Select: Add placeholder and trigger detail fetch
                // console.log(`Selecting table: ${tableName}`);
                newSelected[tableName] = { attributes: null, selectedColumns: new Set() }; // Placeholder
                fetchTableDetails(tableName); // Trigger detail fetch
            } else {
                // Deselect: Remove table and related joins, filters, aggregates, group bys, having, order by
                // console.log(`Deselecting table: ${tableName}`);
                const aliasToRemove = aggregates.filter(a => a.table === tableName).map(a => a.alias).filter(Boolean); // Get aliases from the removed table
                const columnsToRemove = groupByColumns.forEach(gc => gc.startsWith(`${tableName}.`) ? gc : undefined); // Get grouped columns from the removed table
                setQueryResults(null);
                setQueryError(null);
                delete newSelected[tableName];
                // Clean up related clauses
                setJoins(prev => prev.filter(j => j.leftTable !== tableName && j.rightTable !== tableName));
                setWhereClauses(prev => prev.filter(w => w.table !== tableName));
                setAggregates(prev => prev.filter(a => a.table !== tableName));
                setGroupByColumns(prev => {
                    const newSet = new Set(prev);
                    prev.forEach(col => {
                        if (col.startsWith(`${tableName}.`)) { newSet.delete(col); }
                    });
                    return newSet;
                });
                // --- Essential cleanup for new state ---
                setHavingClauses(prev => prev.filter(h => {
                     const referencesRemovedAlias = aliasToRemove.includes(h.columnOrAlias);
                     const referencesRemovedGroupedCol = h.columnOrAlias.startsWith(`${tableName}.`);
                     return !(referencesRemovedAlias || referencesRemovedGroupedCol);
                }));
                setOrderByClauses(prev => prev.filter(o => {
                     const referencesRemovedAlias = aliasToRemove.includes(o.term);
                     const referencesSelectedCol = o.term.startsWith(`${tableName}.`);
                     return !(referencesRemovedAlias || referencesSelectedCol);
                }));
                // --- End essential cleanup ---
            }
            // Clean up aggregates/group by if no tables left
            if (Object.keys(newSelected).length === 0) {
                setAggregates([]);
                setGroupByColumns(new Set());
                setHavingClauses([]);
                setOrderByClauses([]);
            }
            return newSelected;
        });
    }, [fetchTableDetails, aggregates, groupByColumns]); // Added aggregates/groupByColumns to dependency for cleanup logic

    // Handle selecting/deselecting a column - *Includes necessary cleanup logic for new state*
    const toggleColumnSelection = (tableName, columnName) => {
        setSelectedTables(prevSelected => {
            if (!prevSelected[tableName] || !prevSelected[tableName].attributes || prevSelected[tableName].attributes === 'fetching') return prevSelected;

            const currentTable = prevSelected[tableName];
            const newSelectedColumns = new Set(currentTable.selectedColumns);
            const qualifiedCol = `${tableName}.${columnName}`;
            setQueryResults(null);
            setQueryError(null);
            if (newSelectedColumns.has(columnName)) {
                newSelectedColumns.delete(columnName);
                // Also remove from Group By and Order By if it was there
                setGroupByColumns(prev => {
                     const newSet = new Set(prev);
                     newSet.delete(qualifiedCol);
                     return newSet;
                });
                 // --- Essential cleanup for new state ---
                setOrderByClauses(prev => prev.filter(o => o.term !== qualifiedCol));
                // --- End essential cleanup ---
            } else {
                newSelectedColumns.add(columnName);
            }

            return {
                ...prevSelected,
                [tableName]: { ...currentTable, selectedColumns: newSelectedColumns }
            };
        });
    };

    // --- Handler Functions for State ---

    // Joins (Original logic)
    const addJoin = () => setJoins(prev => [...prev, { id: uuidv4(), type: 'INNER', leftTable: '', leftCol: '', rightTable: '', rightCol: '' }]);
    const updateJoin = (id, field, value) => {
        setJoins(prev => prev.map(j => {
            if (j.id === id) {
                const updated = { ...j, [field]: value };
                // Reset columns if table changes
                if (field === 'leftTable') updated.leftCol = '';
                if (field === 'rightTable') updated.rightCol = '';
                return updated;
            }
            return j;
        }));
        setQueryResults(null);
        setQueryError(null);
    };
    const removeJoin = (id) => {
        setJoins(prev => prev.filter(j => j.id !== id));
        setQueryResults(null);
        setQueryError(null);
    };

    // Where Clauses (Original logic)
    const addWhereClause = () => setWhereClauses(prev => [
      ...prev,
      {
          id: uuidv4(),
          table: '',
          column: '',
          operator: '=',
          value: '',
          connector: prev.length > 0 ? 'AND' : null
      }
    ]);
    const updateWhereClause = (id, field, value) => {
      setWhereClauses(prev => prev.map(w => {
          if (w.id === id) {
              const updated = { ...w, [field]: value };
              if (field === 'operator' && (value === 'IS NULL' || value === 'IS NOT NULL')) {
                   updated.value = '';
              }
              if (field === 'table') updated.column = '';
              return updated;
          }
          return w;
      }));
      setQueryResults(null);
      setQueryError(null);
    };
    const removeWhereClause = (id) => {
      setWhereClauses(prev => {
          const remaining = prev.filter(w => w.id !== id);
          if (remaining.length > 0 && remaining[0].connector !== null) {
              remaining[0] = { ...remaining[0], connector: null };
          }
          return remaining;
      });
      setQueryResults(null);
      setQueryError(null);
    };

    // Aggregates - *Includes necessary cleanup logic for new state*
    const addAggregate = () => setAggregates(prev => [...prev, { id: uuidv4(), func: 'COUNT', table: '', column: '*', alias: '' }]);
    const updateAggregate = (id, field, value) => {
        // Get the old alias before updating, in case it changes
        const oldAlias = aggregates.find(a => a.id === id)?.alias;

        setAggregates(prev => prev.map(a => {
            if (a.id === id) {
                const updated = { ...a, [field]: value };
                if (field === 'table') {
                    updated.column = '*'; // Default back to *
                }
                // Basic validation for alias uniqueness (console warning)
                if (field === 'alias' && value) {
                    const otherAliases = prev.filter(other => other.id !== id).map(other => other.alias);
                    if (otherAliases.includes(value)) {
                        console.warn(`Alias "${value}" is already in use. Consider a unique alias.`);
                    }
                }
                 // Clear alias if function becomes COUNT(*) maybe? (Optional UX decision)
                // if(field === 'func' && value === 'COUNT' && updated.column === '*') updated.alias = '';
                return updated;
            }
            return a;
        }));

        // If alias changed, update references in Having/Order By
         const newAlias = field === 'alias' ? value : aggregates.find(a => a.id === id)?.alias;
         if (field === 'alias' && oldAlias && oldAlias !== newAlias) {
             setHavingClauses(prev => prev.map(h => h.columnOrAlias === oldAlias ? { ...h, columnOrAlias: newAlias } : h));
             setOrderByClauses(prev => prev.map(o => o.term === oldAlias ? { ...o, term: newAlias } : o));
         }
        setQueryResults(null);
        setQueryError(null);
    };
    const removeAggregate = (id) => {
        const aliasToRemove = aggregates.find(a => a.id === id)?.alias;
        setAggregates(prev => prev.filter(a => a.id !== id));
        // If removing last aggregate, clear Group By and Having
        if (aggregates.length === 1) {
            setGroupByColumns(new Set());
            setHavingClauses([]); // Clear having if last aggregate is gone
        }
        // Remove from Having and Order By if alias was used
         // --- Essential cleanup for new state ---
        if (aliasToRemove) {
             setHavingClauses(prev => prev.filter(h => h.columnOrAlias !== aliasToRemove));
             setOrderByClauses(prev => prev.filter(o => o.term !== aliasToRemove));
        }
        setQueryResults(null);
        setQueryError(null);
    };

    // Group By - *Includes necessary cleanup logic for new state*
    const toggleGroupByColumn = (tableName, columnName) => {
         const qualifiedCol = `${tableName}.${columnName}`;
         setGroupByColumns(prev => {
            const newSet = new Set(prev);
            if (newSet.has(qualifiedCol)) {
                newSet.delete(qualifiedCol);
                // --- Essential cleanup for new state ---
                // Remove from Having if it was referencing this specific grouped column
                setHavingClauses(prevHaving => prevHaving.filter(h => h.columnOrAlias !== qualifiedCol));
                // --- End essential cleanup ---
            } else {
                // Original validation logic
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
        setQueryResults(null);
        setQueryError(null);
    };

    // --- NEW Handler Functions for HAVING and ORDER BY ---

    // Having Clauses
    const addHavingClause = () => setHavingClauses(prev => [
      ...prev,
      {
          id: uuidv4(),
          func: '', // Optional: Not fully implemented in UI for simplicity but backend supports
          columnOrAlias: '',
          operator: '=',
          value: '',
          connector: prev.length > 0 ? 'AND' : null
      }
    ]);
    const updateHavingClause = (id, field, value) => {
      setHavingClauses(prev => prev.map(h => {
          if (h.id === id) {
              const updated = { ...h, [field]: value };
              if (field === 'operator' && (value === 'IS NULL' || value === 'IS NOT NULL')) {
                   updated.value = '';
              }
              // If columnOrAlias changes, maybe reset func? (Not implemented)
              return updated;
          }
          return h;
      }));
      setQueryResults(null);
      setQueryError(null);
    };
    const removeHavingClause = (id) => {
      setHavingClauses(prev => {
          const remaining = prev.filter(h => h.id !== id);
          if (remaining.length > 0 && remaining[0].connector !== null) {
              remaining[0] = { ...remaining[0], connector: null };
          }
          return remaining;
      });
      setQueryResults(null);
      setQueryError(null);
    };

    // Order By Clauses
    const addOrderByClause = () => setOrderByClauses(prev => [...prev, { id: uuidv4(), term: '', direction: 'ASC' }]);
    const updateOrderByClause = (id, field, value) => {
        setOrderByClauses(prev => prev.map(o => o.id === id ? { ...o, [field]: value } : o));
        setQueryResults(null);
        setQueryError(null);
    };
    const removeOrderByClause = (id) => {setOrderByClauses(prev => prev.filter(o => o.id !== id));
        setQueryResults(null);
        setQueryError(null);
    };

    // --- Helper Functions for Dropdowns/Availability ---

    const getColumnsForTable = (tableName) => {
         return (selectedTables[tableName]?.attributes && selectedTables[tableName]?.attributes !== 'fetching')
            ? selectedTables[tableName].attributes
            : [];
    }

    // Get columns eligible for GROUP BY (selected, not aggregated) - Original Logic
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

    // Get terms eligible for HAVING clause (grouped columns and aggregate aliases)
    const getHavingTerms = () => {
         const grouped = Array.from(groupByColumns).map(gc => ({ value: gc, label: `Grouped: ${gc}` }));
         const aliased = aggregates.filter(a => a.alias).map(a => ({ value: a.alias, label: `Alias: ${a.alias}` }));
         // Allow aggregates directly? e.g., COUNT(col) > 5 - More complex UI needed, stick to aliases/grouped cols for now
         return [...grouped, ...aliased];
    };

    // Get terms eligible for ORDER BY clause (selected non-aggregate columns and aggregate aliases)
    const getOrderableTerms = () => {
         const selectedCols = [];
          Object.entries(selectedTables).forEach(([tableName, details]) => {
             if (details?.selectedColumns && details.attributes !== 'fetching') {
                 details.selectedColumns.forEach(colName => {
                     const qualifiedCol = `${tableName}.${colName}`;
                     const isAggregated = aggregates.some(agg => agg.table === tableName && agg.column === colName);
                     if(!isAggregated) {
                         selectedCols.push({ value: qualifiedCol, label: `Column: ${qualifiedCol}` });
                     }
                 });
             }
         });
         const aliased = aggregates.filter(a => a.alias).map(a => ({ value: a.alias, label: `Alias: ${a.alias}` }));
         return [...selectedCols, ...aliased];
    };

    // --- runQuery Function (UPDATED with having and orderBy - *Essential Change*) ---
    const runQuery = useCallback(async () => {
        setIsQuerying(true); setQueryError(null); setQueryResults(null);

        // --- Minimal logging ---
        // console.log("--- State inside runQuery ---");
        // console.log("Aggregates:", JSON.stringify(aggregates));
        // console.log("Group By:", JSON.stringify(Array.from(groupByColumns)));
        // console.log("Having:", JSON.stringify(havingClauses));
        // console.log("Order By:", JSON.stringify(orderByClauses));
        // console.log("----------------------------");
        // --- End Minimal logging ---

        // 1. Construct query definition object (Logic adapted from original + new clauses)
        const finalSelectedColumns = [];
        const groupByColsArray = Array.from(groupByColumns);
        const hasAggregates = aggregates.length > 0;

        // Build SELECT part
        if (hasAggregates) {
            aggregates.forEach(agg => {
                if(selectedTables[agg.table]) {
                    // Ensure alias is provided if needed later (Having/Order By)
                    if (!agg.alias && (havingClauses.some(h=>h.columnOrAlias === agg.id) || orderByClauses.some(o=>o.term === agg.id))) {
                       console.warn("Aggregate used in Having/Order By requires an alias.");
                       // Maybe set error state here? For now, just warn.
                    }
                    finalSelectedColumns.push({
                        type: 'aggregate',
                        func: agg.func,
                        table: agg.table,
                        column: agg.column,
                        alias: agg.alias || '' // Backend requires alias if aggregate exists
                    });
                } else { console.warn(`Aggregate references table "${agg.table}" which is not selected.`); }
            });
             groupByColsArray.forEach(qualifiedCol => {
                 const [table, column] = qualifiedCol.split('.');
                 if(selectedTables[table]) {
                    finalSelectedColumns.push({ type: 'column', table, column });
                 } else { console.warn(`Group By references table "${table}" which is not selected.`); }
             });
        } else {
             Object.entries(selectedTables).forEach(([tableName, details]) => {
                 if (details?.attributes && details.attributes !== 'fetching' && details.selectedColumns instanceof Set) {
                     details.selectedColumns.forEach(columnName => {
                         finalSelectedColumns.push({ type: 'column', table: tableName, column: columnName });
                     });
                 } else { console.warn(`Skipping columns for table "${tableName}" - details not ready.`); }
             });
        }

        const fromTables = Object.keys(selectedTables).filter(tableName =>
            selectedTables[tableName]?.attributes && selectedTables[tableName]?.attributes !== 'fetching'
        );

        // Prepare HAVING clauses for backend
        const finalHavingClauses = havingClauses.map(h => ({
            column: h.columnOrAlias, // Backend uses 'column' for the reference term
            func: h.func || undefined,
            operator: h.operator,
            value: h.value,
            connector: h.connector
        })).filter(h => h.column && h.operator);

        // Prepare ORDER BY clauses for backend
        const finalOrderByClauses = orderByClauses.map(o => ({
            term: o.term,
            direction: o.direction
        })).filter(o => o.term && o.direction);

        const queryDef = {
            select: finalSelectedColumns,
            from: fromTables,
            joins: joins.filter(j => j.leftTable && j.leftCol && j.rightTable && j.rightCol && j.type && fromTables.includes(j.leftTable) && fromTables.includes(j.rightTable)),
            where: whereClauses.filter(w => w.table && w.column && w.operator && fromTables.includes(w.table)),
            groupBy: groupByColsArray.filter(qualifiedCol => {
                const [table] = qualifiedCol.split('.'); return fromTables.includes(table);
            }),
            // --- Add new clauses ---
            having: finalHavingClauses,
            orderBy: finalOrderByClauses,
        };

        // console.log("Constructed Query Definition:", JSON.stringify(queryDef, null, 2));

        if (!queryDef.from || queryDef.from.length === 0 || !queryDef.select || queryDef.select.length === 0) {
             setQueryError("Cannot build query. Please select tables and columns/aggregates.");
             setIsQuerying(false);
             return;
        }
        if (queryDef.having.length > 0 && !(queryDef.groupBy.length > 0 || hasAggregates)) {
            setQueryError("HAVING clause requires GROUP BY or aggregate functions to be defined.");
            setIsQuerying(false);
            return;
        }

        try {
             const response = await axios.post('http://localhost:5000/api/execute_select', queryDef);
             setQueryResults(response.data);
        } catch (error) {
             console.error("Error running query:", error);
             const errorMsg = error.response?.data?.error || error.message || "Failed to execute query";
             setQueryError(errorMsg);
             if (error.response?.data?.sql_attempted) {
                  console.error("SQL Attempted:", error.response.data.sql_attempted);
             }
        } finally {
             setIsQuerying(false);
        }

    }, [selectedTables, joins, whereClauses, aggregates, groupByColumns, havingClauses, orderByClauses]); // Keep dependencies including new state

    // --- NEW: Export to CSV Function ---
    const exportToCsv = useCallback(() => {
        if (!queryResults || !queryResults.columns || !queryResults.rows || queryResults.rows.length === 0) {
            console.error("No data available to export.");
            return;
        }

        const { columns, rows } = queryResults;

        // Create header row
        const header = columns.map(escapeCsvCell).join(',');

        // Create data rows
        const csvRows = rows.map(row =>
            row.map(escapeCsvCell).join(',')
        );

        // Combine header and rows
        const csvString = [header, ...csvRows].join('\n');

        // Create Blob and trigger download
        const blob = new Blob([csvString], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.setAttribute('href', url);
        link.setAttribute('download', 'query_results.csv');
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url); // Clean up

    }, [queryResults]); // Dependency on queryResults

    // --- UI Rendering ---
    const selectedTableNames = Object.keys(selectedTables);
    const requiresJoin = selectedTableNames.length > 1 && joins.filter(j => j.leftTable && j.leftCol && j.rightTable && j.rightCol && j.type).length === 0;
    const isAnyTableLoading = Object.values(selectedTables).some(details => details?.attributes === 'fetching');
    // Visibility conditions based on original file structure
    const showGroupBy = aggregates.length > 0;
    const showHaving = showGroupBy || aggregates.length > 0; // Show if Group By shown OR aggregates exist
    const showOrderBy = selectedTableNames.length > 0; // Show if any tables selected

    // Get terms for dropdowns
    const availableHavingTerms = getHavingTerms();
    const availableOrderTerms = getOrderableTerms();

    // --- Essential change to button disabled logic ---
    const isRunQueryDisabled = Object.keys(selectedTables).length === 0 ||
                              isQuerying ||
                              isAnyTableLoading ||
                              requiresJoin ||
                              (havingClauses.length > 0 && !(groupByColumns.size > 0 || aggregates.length > 0)); // Added HAVING validation


    const showExportButton = queryResults && queryResults.rows && queryResults.rows.length > 0;
    
    return (
        <div className='component-layout'> {/* Using original top-level structure */}
            {/* Sidebar */}
            <div className='sidebar'>

                {/* --- Tables Section (Original Structure) --- */}
                <div className="sidebar-section">
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
                                                disabled={selectedTables[tableName]?.attributes === 'fetching'}
                                            />
                                            {tableName}
                                            {selectedTables[tableName]?.attributes === 'fetching' && <em style={{fontSize: '0.8em', color: '#888'}}> (loading...)</em>}
                                        </label>
                                    </li>
                                ))
                            ) : ( <p>No tables found.</p> )}
                        </ul>
                    )}
                </div>

                {/* --- Joins Section (Original Structure) --- */}
                {selectedTableNames.length >= 2 && (
                    <div className="sidebar-section">
                        <h4>Joins</h4>
                        {joins.map((join) => (
                            // Using original inline style approach for joins row
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
                                <button onClick={() => removeJoin(join.id)} title="Remove join" style={{ marginLeft: '5px', color: 'red', border: 'none', background: 'none', cursor: 'pointer', padding:'0 5px' }}>X</button>
                            </div>
                        ))}
                        <button onClick={addJoin} style={{ fontSize: '0.8em' }}>+ Add Join</button>
                    </div>
                )}

                 {/* --- Columns & Filters Section (Original Structure) --- */}
                 {selectedTableNames.length >= 1 && (
                    <div className='sidebar-section'>
                        <h4>Columns & Filters</h4>
                        {/* Column Selection (Original Structure) */}
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
                         {/* WHERE Clauses (Original Structure) */}
                        {/* Note: Original file placed this inside the Columns & Filters section */}
                        <div className='sidebar-section' style={{marginTop:'15px'}}> {/* Added margin for visual separation, maybe adjust */}
                            <h5>Filters (WHERE)</h5>
                             {whereClauses.map((clause, index) => (
                                <div key={clause.id} style={{ marginBottom: '10px'}}>
                                     {index > 0 && (
                                         <div style={{ margin: '5px 0 5px 20px', fontSize:'0.8em', display: 'flex', alignItems: 'center' }}>
                                             <select
                                                 value={clause.connector || 'AND'}
                                                 onChange={e => updateWhereClause(clause.id, 'connector', e.target.value)}
                                                 style={{ padding:'2px', marginRight:'5px', paddingRight: '20px', minWidth: '70px' }}
                                             >
                                                 <option value="AND">AND</option>
                                                 <option value="OR">OR</option>
                                             </select>
                                              <span>Condition {index + 1}:</span>
                                         </div>
                                     )}
                                    <div style={{ display: 'flex', alignItems: 'center', fontSize: '0.9em', marginBottom: '5px' }}>
                                        <select value={clause.table} onChange={e => updateWhereClause(clause.id, 'table', e.target.value)} style={{ maxWidth: '80px', marginRight:'3px' }}>
                                             <option value="">Table</option>
                                             {selectedTableNames.map(t => <option key={t} value={t}>{t}</option>)}
                                        </select>
                                        <select value={clause.column} onChange={e => updateWhereClause(clause.id, 'column', e.target.value)} style={{ maxWidth: '80px', marginRight:'3px' }} disabled={!clause.table}>
                                            <option value="">Column</option>
                                             {clause.table && getColumnsForTable(clause.table).map(col => <option key={col.name} value={col.name}>{col.name}</option>)}
                                        </select>
                                        <select value={clause.operator} onChange={e => updateWhereClause(clause.id, 'operator', e.target.value)} style={{ width: '70px', marginRight:'3px' }}>
                                            {ALLOWED_OPERATORS.map(op => <option key={op} value={op}>{op}</option>)}
                                        </select>
                                        <input type="text" value={clause.value} onChange={e => updateWhereClause(clause.id, 'value', e.target.value)} placeholder="Value" style={{ flexGrow: 1, marginRight:'3px', minWidth: '50px' }} disabled={clause.operator === 'IS NULL' || clause.operator === 'IS NOT NULL'} />
                                        <button onClick={() => removeWhereClause(clause.id)} title="Remove condition" style={{ color: 'red', border: 'none', background: 'none', cursor: 'pointer', padding: '0 5px' }}>X</button>
                                    </div>
                                </div>
                            ))}
                            <button onClick={addWhereClause} style={{ width: '100%', fontSize: '0.8em' }}>+ Add Filter Condition</button>
                        </div>
                    </div>
                )}

                {/* --- Aggregates Section (Original Structure) --- */}
                {selectedTableNames.length >= 1 && (
                    <div className='sidebar-section'>
                        <h4>Aggregates</h4>
                         {aggregates.map((agg) => (
                            // Using original inline style approach
                            <div key={agg.id} style={{ display: 'flex', alignItems: 'center', marginBottom: '5px', fontSize: '0.9em' }}>
                                <select value={agg.func} onChange={e => updateAggregate(agg.id, 'func', e.target.value)} style={{ width: '70px', marginRight:'3px' }}>
                                    {ALLOWED_AGGREGATES.map(f => <option key={f} value={f}>{f}</option>)}
                                </select>
                                (
                                 <select value={agg.table} onChange={e => updateAggregate(agg.id, 'table', e.target.value)} style={{ maxWidth: '80px', margin:'0 3px' }}>
                                    <option value="">Table</option>
                                    {selectedTableNames.map(t => <option key={t} value={t}>{t}</option>)}
                                </select>
                                .
                                <select value={agg.column} onChange={e => updateAggregate(agg.id, 'column', e.target.value)} style={{ maxWidth: '80px', margin:'0 3px' }} disabled={!agg.table}>
                                    <option value="*">* (All)</option>
                                     {agg.table && getColumnsForTable(agg.table).map(col => <option key={col.name} value={col.name}>{col.name}</option>)}
                                </select>
                                ) AS
                                <input
                                    type="text" value={agg.alias}
                                    onChange={e => updateAggregate(agg.id, 'alias', e.target.value)}
                                    placeholder="alias (required)" // Encourage alias
                                    style={{ flexGrow: 1, marginLeft:'3px', marginRight:'3px', minWidth:'50px' }}
                                    required
                                />
                                <button onClick={() => removeAggregate(agg.id)} title="Remove aggregate" style={{ color: 'red', border: 'none', background: 'none', cursor: 'pointer', padding: '0 5px' }}>X</button>
                            </div>
                         ))}
                        <button onClick={addAggregate} style={{ width: '100%', fontSize: '0.8em' }}>+ Add Aggregate</button>
                    </div>
                )}

                {/* --- Group By Section (Original Structure & Condition) --- */}
                {showGroupBy && ( // Condition from original file: aggregates.length > 0
                    <div className='sidebar-section'>
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
                              {getGroupableColumns().length === 0 && aggregates.length > 0 && <li style={{fontSize:'0.9em', color:'#888'}}>No columns available to group by (select non-aggregated columns).</li>}
                         </ul>
                    </div>
                )}

                {/* --- NEW: HAVING Section --- */}
                {/* Added after existing sections, using similar structure */}
                {showHaving && ( // Conditionally render based on Group By / Aggregates
                    <div className='sidebar-section'>
                        <h4>Filter Groups (HAVING)</h4>
                        {havingClauses.map((clause, index) => (
                            <div key={clause.id} style={{ marginBottom: '10px'}}>
                                {index > 0 && (
                                     // Mimicking WHERE connector style
                                     <div style={{ margin: '5px 0px 5px 20px', fontSize:'0.8em', display: 'flex', alignItems: 'center' }}>
                                         <select
                                             value={clause.connector || 'AND'}
                                             onChange={e => updateHavingClause(clause.id, 'connector', e.target.value)}
                                             style={{ padding:'2px', marginRight:'5px', paddingRight: '20px', minWidth: '70px' }}
                                         >
                                             <option value="AND">AND</option>
                                             <option value="OR">OR</option>
                                         </select>
                                          <span>Condition {index + 1}:</span>
                                     </div>
                                )}
                                 {/* Mimicking WHERE row style */}
                                <div style={{ display: 'flex', alignItems: 'center', fontSize: '0.9em', marginBottom: '5px' }}>
                                    {/* UI for func() part is omitted for simplicity, backend supports it if added */}
                                    <select value={clause.columnOrAlias} onChange={e => updateHavingClause(clause.id, 'columnOrAlias', e.target.value)} style={{ maxWidth: '120px', marginRight:'3px' }}> {/* Adjusted width slightly */}
                                        <option value="">Grouped Col / Alias</option>
                                        {availableHavingTerms.map(term => <option key={term.value} value={term.value}>{term.label}</option>)}
                                    </select>
                                     <select value={clause.operator} onChange={e => updateHavingClause(clause.id, 'operator', e.target.value)} style={{ width: '70px', marginRight:'3px' }}>
                                         {ALLOWED_OPERATORS.map(op => <option key={op} value={op}>{op}</option>)}
                                    </select>
                                    <input type="text" value={clause.value} onChange={e => updateHavingClause(clause.id, 'value', e.target.value)} placeholder="Value" style={{ flexGrow: 1, marginRight:'3px', minWidth: '50px' }} disabled={clause.operator === 'IS NULL' || clause.operator === 'IS NOT NULL'} />
                                    <button onClick={() => removeHavingClause(clause.id)} title="Remove condition" style={{ color: 'red', border: 'none', background: 'none', cursor: 'pointer', padding: '0 5px' }}>X</button>
                                </div>
                            </div>
                        ))}
                        <button onClick={addHavingClause} style={{ width: '100%', fontSize: '0.8em' }}>+ Add Having Condition</button>
                        {availableHavingTerms.length === 0 && <p style={{fontSize:'0.9em', color:'#888', marginTop:'5px'}}>Define aggregates with aliases or Group By columns first.</p>}
                    </div>
                )}

                {/* --- NEW: ORDER BY Section --- */}
                {/* Added after existing sections, using similar structure */}
                 {showOrderBy && ( // Conditionally render
                    <div className='sidebar-section'>
                        <h4>Order Results (ORDER BY)</h4>
                        {orderByClauses.map((clause) => (
                            // Mimicking WHERE/Aggregate row style loosely
                            <div key={clause.id} style={{ display: 'flex', alignItems: 'center', marginBottom: '5px', fontSize: '0.9em' }}>
                                <select value={clause.term} onChange={e => updateOrderByClause(clause.id, 'term', e.target.value)} style={{ flexGrow: 1, marginRight:'3px', minWidth:'150px' }}> {/* Adjusted style */}
                                    <option value="">Select Column/Alias</option>
                                    {availableOrderTerms.map(term => <option key={term.value} value={term.value}>{term.label}</option>)}
                                </select>
                                <select value={clause.direction} onChange={e => updateOrderByClause(clause.id, 'direction', e.target.value)} style={{ width: '65px', marginRight:'3px' }}> {/* Adjusted style */}
                                    {ALLOWED_ORDER_DIRECTIONS.map(dir => <option key={dir} value={dir}>{dir}</option>)}
                                </select>
                                <button onClick={() => removeOrderByClause(clause.id)} title="Remove order clause" style={{ color: 'red', border: 'none', background: 'none', cursor: 'pointer', padding: '0 5px' }}>X</button>
                            </div>
                        ))}
                        <button onClick={addOrderByClause} style={{ width: '100%', fontSize: '0.8em' }}>+ Add Order Clause</button>
                         {availableOrderTerms.length === 0 && <p style={{fontSize:'0.9em', color:'#888', marginTop:'5px'}}>Select columns or define aggregate aliases first.</p>}
                    </div>
                 )}


                {/* --- Inform user if joins are required (Original) --- */}
                {requiresJoin &&
                       <p className='warning-message'>
                           Please define JOIN conditions for multiple tables.
                       </p>
                   }

                {/* --- Query Button Section (Original Structure) --- */}
                  <div className='sidebar-sticky-bottom'>
                      <button
                          onClick={runQuery}
                          style={{ width: '100%', padding: '12px 0' }} // Style from original
                          disabled={isRunQueryDisabled} // Uses updated disabled logic
                      >
                          {isQuerying ? 'Running...' : 'Run Query'}
                      </button>
                       {/* Original loading indicator */}
                       {isAnyTableLoading && <p style={{fontSize: '0.8em', color: '#888', textAlign:'center'}}>Loading table details...</p>}
                       {/* Added feedback for HAVING validation */}
                       {(havingClauses.length > 0 && !(groupByColumns.size > 0 || aggregates.length > 0)) && <p style={{fontSize: '0.8em', color: 'orange', textAlign:'center'}}>HAVING requires Group By or Aggregates</p>}
                  </div>
              </div> {/* End Sidebar */}

            {/* Main Content Area - Results */}
            <div className='main-content'>
                {/* --- NEW: Header container for Title and Export Button --- */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                    <h2>Query Results</h2>
                    {/* --- NEW: Conditional Export Button --- */}
                    {showExportButton && (
                        <button
                            onClick={exportToCsv}
                            title="Export results to CSV"
                            style={{
                                padding: '5px 10px',
                                cursor: 'pointer',

                            }}
                        >
                            Export CSV
                        </button>
                    )}
                </div>
                {isQuerying && <p>Executing query...</p>}
                {queryError && <p className='error-message'>Query Error: {queryError}</p>}
                {queryResults ? (
                    queryResults.rows && queryResults.rows.length > 0 ? (
                     <table border="1" style={{ borderCollapse: 'collapse', width: '100%', marginTop: '15px' }}>
                         <thead>
                             <tr>{queryResults.columns.map((colName, index) => <th key={index}>{colName}</th>)}</tr>
                         </thead>
                         <tbody>
                             {queryResults.rows.map((row, rowIndex) => (
                                 <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell === null ? <i>NULL</i> : String(cell)}</td>)}</tr>
                             ))}
                         </tbody>
                     </table>
                    ) : ( <p style={{marginTop:'15px'}}>Query executed successfully, but returned no rows.</p> )
                ) : ( !isQuerying && !queryError && <p style={{marginTop:'15px'}}>Define your query using the sidebar and click "Run Query".</p> )}
            </div> {/* End Main Content */}
        </div> // End Component Layout
    );
}

export default DataSelection;