import React from 'react';
import { BrowserRouter as Router, Routes, Route, NavLink } from 'react-router-dom';

import LandingPage from './LandingPage';
import SchemaCanvas from './SchemaCanvas';
import DataSelection from './DataSelection'
import CrudOperations from './CrudOperations';
import NormalizationAnalyzer from './NormalizationAnalyzer';

import '@xyflow/react/dist/style.css';

import '../Styles/App.css';


// --- Main App Component ---
function App() {
  return (
    <Router>
      <div className="App"> {/* Added className */}
        <nav className="app-nav"> {/* Added className */}
          <ul>
            {/* Use NavLink for active styling */}
            <li><NavLink to="/">Home</NavLink></li>
            <li><NavLink to="/canvas">Canvas</NavLink></li>
            <li><NavLink to="/select">Select</NavLink></li>
            <li><NavLink to="/crud">CRUD</NavLink></li>
            <li><NavLink to="/normalization">Normalization</NavLink></li>
          </ul>
        </nav>
        {/* Removed <hr /> */}
        <div className="app-content"> {/* Added className */}
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/canvas" element={<SchemaCanvas />} />
            <Route path="/select" element={<DataSelection />} />
            <Route path="/crud" element={<CrudOperations />} />
            <Route path="/normalization" element={<NormalizationAnalyzer />} />
          </Routes>
        </div>
      </div>
    </Router>
  );
}

export default App;
