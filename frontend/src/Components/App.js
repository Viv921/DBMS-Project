import React, { useContext } from 'react';
import { BrowserRouter as Router, Routes, Route, NavLink } from 'react-router-dom';

import LandingPage from './LandingPage';
import SchemaCanvas from './SchemaCanvas';
import DataSelection from './DataSelection'
import CrudOperations from './CrudOperations';
import NormalizationAnalyzer from './NormalizationAnalyzer';
import { ThemeProvider } from './ThemeContext';

import '@xyflow/react/dist/style.css';

import '../Styles/App.css';

// --- Main App Component ---
function AppContent() {
  return (
    <Router>
      <div className="App">
        <nav className="app-nav">
          <ul>
            <li><NavLink to="/">Home</NavLink></li>
            <li><NavLink to="/canvas">Canvas</NavLink></li>
            <li><NavLink to="/select">Select</NavLink></li>
            <li><NavLink to="/crud">CRUD</NavLink></li>
            <li><NavLink to="/normalization">Normalization</NavLink></li>
          </ul>
        </nav>
        <div className="app-content">
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

function App() {
  return (
    <ThemeProvider>
      <AppContent />
    </ThemeProvider>
  );
}

export default App;
