import React from 'react';
// Removed Link from react-router-dom as the nav is now just for scrolling
// import {Link} from 'react-router-dom';
import { useNavigate } from 'react-router-dom'; // Import useNavigate

import '@xyflow/react/dist/style.css';
import '../Styles/App.css'; // Keep App.css for layout

// --- Landing Page Component ---
function LandingPage() {
  const navigate = useNavigate(); // Hook for navigation

  // Function to handle smooth scrolling
  const scrollToSection = (sectionId) => {
    const section = document.getElementById(sectionId);
    if (section) {
      section.scrollIntoView({ behavior: 'smooth' });
    }
  };

  // Function to handle navigation for cards
  const handleCardClick = (path) => {
    navigate(path);
  };

  return (
    <> {/* Use Fragment to return multiple root elements */}
      {/* Hero Section */}
      <div className="hero-section"> {/* Added className for styling */}
        <h1 className="hero-title">Supercharge your Database</h1>
        <p className="hero-caption">
          The most effective way to visualize, design, and manage your MySQL databases.
          Enjoy unmatched clarity and intuitive tools while simplifying complexity.
        </p>
        {/* Updated button to scroll */}
        <button className="hero-button" onClick={() => scrollToSection('main-content-section')}>
          Get Started
        </button>
        {/* Optional: Add secondary action if needed, like 'Contact Sales' */}
        {/* <a href="/contact" className="hero-link">Contact sales →</a> */}
      </div>

      {/* Target Section for Scrolling - Now with Feature Cards */}
      <div id="main-content-section" className="main-content-section">
        <h2>Main Features</h2>
        {/* Remove the old nav */}
        {/* <nav className="landing-page-nav"> ... </nav> */}

        {/* Add the features grid */}
        <div className="features-grid">
          <div className="feature-card" onClick={() => handleCardClick('/canvas')}>
            {/* Placeholder for Icon */}
            
            <h3>Schema Design Canvas</h3>
            <p>Visually design and modify your database schema.</p>
          </div>
          <div className="feature-card" onClick={() => handleCardClick('/select')}>
            {/* Placeholder for Icon */}
            
            <h3>Data Selection</h3>
            <p>Query and explore data across your tables.</p>
          </div>
          <div className="feature-card" onClick={() => handleCardClick('/crud')}>
            {/* Placeholder for Icon */}
            
            <h3>CRUD Operations</h3>
            <p>Easily create, read, update, and delete records.</p>
          </div>
          <div className="feature-card" onClick={() => handleCardClick('/normalization')}>
            {/* Placeholder for Icon */}
            
            <h3>Normalization</h3>
            <p>Analyze and normalize your database structure.</p>
          </div>
        </div>
      </div>
    </>
  );
}

export default LandingPage;