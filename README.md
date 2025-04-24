# Accessible - MySQL Visual Web UI

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/Python-3.7+-blue.svg)](https://www.python.org/)
[![React Version](https://img.shields.io/badge/React-18+-blue.svg)](https://reactjs.org/)
[![Flask Version](https://img.shields.io/badge/Flask-2.x-orange.svg)](https://flask.palletsprojects.com/)

**Accessible** is a local web application designed for developers to interact with MySQL databases through an intuitive visual interface. It allows for schema design, data querying with joins and conditions, CRUD operations, and schema normalization analysis without needing to write raw SQL.

---

## 📖 Table of Contents

* [📍 About The Project](#-about-the-project)
* [✨ Features](#-features)
* [🖼️ Screenshots (Placeholder)](#️-screenshots-placeholder)
* [🛠️ Built With](#️-built-with)
* [🚀 Getting Started](#-getting-started)
    * [Prerequisites](#prerequisites)
    * [Installation](#installation)
        * [Windows (using run.bat)](#windows-using-runbat)
        * [macOS / Linux (Manual Setup)](#macos--linux-manual-setup)
* [⚙️ Configuration](#️-configuration)
* [▶️ Usage](#️-usage)
    * [Windows (using run.bat)](#windows-using-runbat-1)
    * [macOS / Linux (Manual Start)](#macos--linux-manual-start)
* [🤝 Contributing](#-contributing)
* [📜 License](#-license)

---

## 📍 About The Project

This tool aims to simplify common database tasks for developers working with MySQL. By providing a visual layer over standard SQL operations, it speeds up development workflows related to schema management, data inspection/manipulation, and understanding database structure.

**Key goals include:**
* Visual schema design and modification.
* Intuitive data selection and filtering.
* Simplified CRUD operations.
* Tools for analyzing and improving schema normalization.

---

## ✨ Features

* **Visual Schema Designer:** Drag-and-drop interface (`@xyflow/react`) to create/modify tables, define columns (name, type, PK, constraints), and visualize relationships. Changes can be applied directly to the database.
* **Data Query Builder:** Select tables and columns, define JOIN conditions, and apply WHERE clauses through a UI to fetch and display data.
* **CRUD Operations Interface:** View table data and perform Insert, Update, and Delete operations via forms, with support for WHERE conditions on updates/deletes.
* **Normalization Analyzer:** Analyze table schemas against 1NF, 2NF, 3NF, and BCNF based on Primary Keys and user-defined Functional Dependencies.
* **Schema Decomposition:** Calculate and apply 3NF or BCNF decompositions based on analysis results (includes data migration and dropping the original table).

---

## 🖼️ Screenshots (Placeholder)

<p align="center">
  *Add screenshots of the main features (Canvas, Select, CRUD, Normalization) here.*
</p>

---

## 🛠️ Built With

This project utilizes the following major technologies:

* **Backend:**
    * ![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white)
    * ![Flask](https://img.shields.io/badge/Flask-000000?style=flat&logo=flask&logoColor=white)
    * `mysql-connector-python`
    * `python-dotenv`
* **Frontend:**
    * ![React](https://img.shields.io/badge/React-61DAFB?style=flat&logo=react&logoColor=black)
    * `react-router-dom`
    * `axios`
    * `@xyflow/react` (React Flow)
    * CSS
* **Database:**
    * ![MySQL](https://img.shields.io/badge/MySQL-4479A1?style=flat&logo=mysql&logoColor=white)

---

## 🚀 Getting Started

Follow these steps to get a local copy up and running.

### Prerequisites

Ensure you have the following installed and configured in your system's PATH:

* **Python:** Version 3.7+ recommended (`pip` included).
* **Node.js & npm:** Node.js version 14+ recommended (`npm` included).
* **MySQL Server:** A running MySQL instance (local or remote).
* **Git:** For cloning the repository.

### Installation

#### Windows (using `run.bat`)

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/Viv921/Accessible
    cd Accessible
    ```

2.  **Configure Database:**
    * Create the database connection file by following the steps in the [⚙️ Configuration](#️-configuration) section below. **This is essential.**

3.  **Run the Installer/Launcher:**
    * Double-click the `run.bat` file located in the project's root directory.
    * The script will automatically perform setup checks and install dependencies if needed before launching the servers.

#### macOS / Linux (Manual Setup)

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/Viv921/Accessible
    cd Accessible
    ```

2.  **Backend Setup:**
    * Navigate to the backend directory: `cd backend`
    * Create and activate a virtual environment:
        ```bash
        python3 -m venv venv  # Or python -m venv venv
        source venv/bin/activate
        ```
    * Install Python dependencies:
        ```bash
        pip install -r requirements.txt
        ```
    * Configure database connection (see [⚙️ Configuration](#️-configuration) below). **This is essential.**
    * Deactivate the virtual environment for now: `deactivate`
    * Navigate back to the root directory: `cd ..`

3.  **Frontend Setup:**
    * Navigate to the frontend directory: `cd frontend`
    * Install Node.js dependencies:
        ```bash
        npm install
        ```
    * Navigate back to the root directory: `cd ..`

4.  **Database Setup:**
    * Ensure your MySQL server is running.
    * Create the database specified in your `.env` file (see [⚙️ Configuration](#️-configuration) below) if it doesn't exist.
        ```sql
        -- Example using MySQL client:
        CREATE DATABASE mydatabase; -- Or your chosen DB_NAME
        ```

---

## ⚙️ Configuration

The backend requires a `.env` file in the `backend` directory to configure the database connection. This step is required for **all operating systems**.

1.  Navigate to the `backend` directory.
2.  Create a file named `.env`.
3.  Add the following environment variables, replacing the placeholder values with your actual MySQL credentials:

    ```dotenv
    # .env file in the backend directory
    MYSQL_HOST=localhost
    MYSQL_USER=your_mysql_user
    MYSQL_PASSWORD=your_mysql_password
    MYSQL_DB=your_database_name
    ```

    * `MYSQL_HOST`: Hostname or IP address of your MySQL server.
    * `MYSQL_USER`: MySQL username.
    * `MYSQL_PASSWORD`: Password for the MySQL user.
    * `MYSQL_DB`: The name of the database to connect to.

---

## ▶️ Usage

#### Windows (using `run.bat`)

1.  **Ensure Configuration is Done:** Make sure you have created the `backend/.env` file.
2.  **Run the Script:** Double-click the `run.bat` file in the project root directory.
3.  **Wait:** The script launches two new command prompt windows (backend and frontend).
4.  **Access:** The application should open automatically in your browser at `http://localhost:3000`.
5.  **Stop:** Close **both** command prompt windows opened by the script.

#### macOS / Linux (Manual Start)

1.  **Start Backend:**
    * Open Terminal 1.
    * `cd <repository-directory>`
    * `source backend/venv/bin/activate`
    * `cd backend`
    * `flask run` (or `python app.py`)
    * Keep this terminal open.

2.  **Start Frontend:**
    * Open Terminal 2.
    * `cd <repository-directory>`
    * `cd frontend`
    * `npm start`
    * Keep this terminal open.

3.  **Access:** Open `http://localhost:3000` in your browser.

4.  **Stop:** Press `Ctrl + C` in both terminals. Deactivate the backend venv in Terminal 1 (`deactivate`).

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1.  Fork the Project
2.  Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3.  Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4.  Push to the Branch (`git push origin feature/AmazingFeature`)
5.  Open a Pull Request

---

## 📜 License

Distributed under the MIT License. See `LICENSE` file for more information.

