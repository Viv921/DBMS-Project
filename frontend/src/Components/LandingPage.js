import React from 'react';
import {Link} from 'react-router-dom';

import '@xyflow/react/dist/style.css';

import '../Styles/App.css';


// --- Landing Page Component ---
function LandingPage() {
    // Apply landing-page class
    return (
      <div className="landing-page"> {/* Added className */}
        <h1>Welcome to the MySQL Visual UI</h1>
        <p>Select an option:</p>
        {/* Use nav element structure as defined in CSS */}
        <nav>
          <ul>
            {/* Use regular Links here if specific landing page styling is preferred */}
            <li><Link to="/canvas">Schema Design Canvas</Link></li>
            <li><Link to="/select">Data Selection</Link></li>
            <li><Link to="/crud">CRUD Operations</Link></li>
            <li><Link to="/normalization">Normalization</Link></li>
          </ul>
        </nav>
      </div>
    );
  }

export default LandingPage;