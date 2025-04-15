import React, { useCallback, memo } from 'react';
import { Handle, Position, useReactFlow } from '@xyflow/react';

// Basic styling (can be moved to CSS)
const nodeStyle = {
  border: '1px solid #777',
  padding: '10px',
  borderRadius: '5px',
  background: 'white',
  minWidth: '200px',
};

const inputStyle = {
  width: '95%',
  marginBottom: '5px',
};

const attributeRowStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  marginBottom: '4px',
  fontSize: '0.9em',
};

const constraintLabelStyle = {
    fontSize: '0.8em',
    margin: '0 2px',
};

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
    <div style={nodeStyle}>
      {/* Handles */}
      <Handle type="target" position={Position.Left} id={`target-${id}`} />
      <Handle type="source" position={Position.Right} id={`source-${id}`} />

      {/* Table Name */}
      <input
        type="text"
        value={tableName}
        onChange={onTableNameChange}
        style={inputStyle}
        placeholder="Table Name"
      />
      <hr style={{ margin: '5px 0' }} />

      {/* Attributes */}
      <div style={{ marginBottom: '5px', fontSize: '0.8em', fontWeight: 'bold' }}>Attributes:</div>
      {attributes.map((attr, index) => (
        <div key={index} style={attributeRowStyle}>
          {/* Name */}
          <input
            type="text"
            value={attr.name || ''}
            onChange={(e) => onAttributeChange(index, 'name', e.target.value)}
            placeholder="col name"
            style={{ width: '30%', marginRight: '3px' }}
          />
          {/* Type */}
          <select
             value={attr.type || 'VARCHAR(255)'}
             onChange={(e) => onAttributeChange(index, 'type', e.target.value)}
             style={{ width: '30%', marginRight: '3px' }}
          >
            <option value="INT">INT</option>
            <option value="VARCHAR(255)">VARCHAR(255)</option>
            <option value="TEXT">TEXT</option>
            <option value="DATE">DATE</option>
            <option value="BOOLEAN">BOOLEAN</option>
            <option value="DECIMAL(10,2)">DECIMAL(10,2)</option>
            {/* Add more types */}
          </select>
          {/* Constraints */}
          <div style={{ display: 'flex', alignItems: 'center' }}>
             <label style={constraintLabelStyle}>
                PK:
                <input type="checkbox" checked={attr.isPK || false} onChange={(e) => onAttributeChange(index, 'isPK', e.target.checked)} />
             </label>
             <label style={constraintLabelStyle}>
                NN:
                <input type="checkbox" checked={attr.isNotNull || false} onChange={(e) => onAttributeChange(index, 'isNotNull', e.target.checked)} />
             </label>
             <label style={constraintLabelStyle}>
                UQ:
                <input type="checkbox" checked={attr.isUnique || false} onChange={(e) => onAttributeChange(index, 'isUnique', e.target.checked)} />
             </label>
          </div>
          {/* Delete Button */}
          <button onClick={() => deleteAttribute(index)} style={{ padding: '1px 4px', fontSize: '0.8em', lineHeight: '1', marginLeft: '3px', color: 'red', border: '1px solid red', background: 'none', cursor: 'pointer' }}>
            X
          </button>
        </div>
      ))}
      <button onClick={addAttribute} style={{ fontSize: '0.8em', width: '100%', marginTop: '5px' }}>
        + Add Attribute
      </button>
    </div>
  );
};

export default memo(TableNode);