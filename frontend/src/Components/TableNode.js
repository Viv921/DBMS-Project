import React, { useCallback, memo } from 'react';
import { Handle, Position, useReactFlow } from '@xyflow/react';


const TableNode = ({ data, id }) => {
  const { setNodes } = useReactFlow();

  // --- Callbacks using setNodes updater function for robust state access ---
  const onTableNameChange = useCallback((evt) => {
    setNodes((nds) =>
      nds.map((node) => {
        if (node.id === id) {
          return { ...node, data: { ...node.data, label: evt.target.value } };
        }
        return node;
      })
    );
  }, [id, setNodes]);

  const addAttribute = useCallback(() => {
    setNodes((nds) =>
      nds.map((node) => {
        if (node.id === id) {
          const currentAttributes = node.data.attributes || [];
          const newAttribute = { name: `col_${currentAttributes.length + 1}`, type: 'VARCHAR(255)', isPK: false, isNotNull: false, isUnique: false };
          return { ...node, data: { ...node.data, attributes: [...currentAttributes, newAttribute] } };
        }
        return node;
      })
    );
  }, [id, setNodes]);

  const onAttributeChange = useCallback((index, field, value) => {
    setNodes((nds) =>
      nds.map((node) => {
        if (node.id === id) {
          let currentAttributes = [...(node.data.attributes || [])];
          let updatedAttr = { ...currentAttributes[index], [field]: value };

          if (field === 'isPK' && value === true) {
            currentAttributes = currentAttributes.map((attr, i) => ({
              ...attr,
              isPK: i === index
            }));
            updatedAttr = { ...currentAttributes[index], isPK: true };
          }
          currentAttributes[index] = updatedAttr;
          return { ...node, data: { ...node.data, attributes: currentAttributes } };
        }
        return node;
      })
    );
  }, [id, setNodes]);

  const deleteAttribute = useCallback((index) => {
     setNodes((nds) =>
       nds.map((node) => {
         if (node.id === id) {
           const currentAttributes = node.data.attributes || [];
           const newAttributes = currentAttributes.filter((_, i) => i !== index);
           return { ...node, data: { ...node.data, attributes: newAttributes } };
         }
         return node;
       })
     );
  }, [id, setNodes]);

  // --- Render using the data prop directly ---
  // React Flow ensures the 'data' prop is updated when nodeInternals changes
  const attributes = data.attributes || [];
  const tableName = data.label || `Table_${id}`;


  return (
    // Apply the main node class
    <div className="table-node">
      {/* Handles (remain the same) */}
      <Handle type="target" position={Position.Left} id={`target-${id}`} />
      <Handle type="source" position={Position.Right} id={`source-${id}`} />

      {/* Table Name */}
      <div className="table-node-header"> {/* Optional wrapper for header styling */}
        <input
          type="text"
          value={tableName}
          onChange={onTableNameChange}
          // Removed inline style, relies on .table-node input styles
          placeholder="Table Name"
        />
      </div>
      {/* Removed <hr />, styling handled by classes */}

      {/* Attributes */}
      <div className="table-node-attributes-title">Attributes:</div>
      {attributes.map((attr, index) => (
        // Apply attribute row class
        <div key={index} className="table-node-attribute-row">
          {/* Name */}
          <input
            type="text"
            value={attr.name || ''}
            onChange={(e) => onAttributeChange(index, 'name', e.target.value)}
            placeholder="col name"
            // Removed inline style, relies on .table-node-attribute-row input styles
          />
          {/* Type */}
          <select
             value={attr.type || 'VARCHAR(255)'} // Ensure a default value
             onChange={(e) => onAttributeChange(index, 'type', e.target.value)}
             // Removed inline style
          >
            <option value="INT">INT</option>
            <option value="VARCHAR(255)">VARCHAR(255)</option>
            <option value="TEXT">TEXT</option>
            <option value="DATE">DATE</option>
            <option value="BOOLEAN">BOOLEAN</option>
            <option value="DECIMAL(10,2)">DECIMAL(10,2)</option>
            <option value="TIMESTAMP">TIMESTAMP</option>
            <option value="FLOAT">FLOAT</option>
            {/* Add more relevant MySQL types */}
          </select>
          {/* Constraints */}
          {/* Apply constraints container class */}
          <div className="table-node-constraints">
             {/* Removed inline label style */}
             <label title="Primary Key">
                PK:
                <input type="checkbox" checked={attr.isPK || false} onChange={(e) => onAttributeChange(index, 'isPK', e.target.checked)} />
             </label>
             <label title="Not Null">
                NN:
                <input type="checkbox" checked={attr.isNotNull || false} onChange={(e) => onAttributeChange(index, 'isNotNull', e.target.checked)} disabled={attr.isPK} /* NN is implied by PK */ />
             </label>
             <label title="Unique">
                UQ:
                <input type="checkbox" checked={attr.isUnique || false} onChange={(e) => onAttributeChange(index, 'isUnique', e.target.checked)} disabled={attr.isPK} /* Unique is implied by PK */ />
             </label>
          </div>
          {/* Delete Button */}
          {/* Apply delete button class */}
          <button onClick={() => deleteAttribute(index)} className="table-node-delete-button" title="Delete Attribute">
            X
          </button>
        </div>
      ))}
      {/* Apply add button class */}
      <button onClick={addAttribute} className="table-node-add-button">
        + Add Attribute
      </button>
    </div>
  );
};

export default memo(TableNode);