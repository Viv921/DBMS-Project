# Accessible - MySQL Visual Web UI

Accessible is a local web application designed for developers to interact with MySQL databases through an intuitive visual interface. It allows for schema design, data querying with joins and conditions, CRUD operations, and schema normalization analysis without needing to write raw SQL.

## Table of Contents

* [About The Project](#about-the-project)
* [Features](#features)
* [Built With](#built-with)
* [Getting Started](#getting-started)
    * [Prerequisites](#prerequisites)
    * [Installation](#installation)
* [Configuration](#configuration)
* [Usage](#usage)
* [Contributing](#contributing)
* [License](#license)

## About The Project

This tool aims to simplify common database tasks for developers working with MySQL. By providing a visual layer over standard SQL operations, it speeds up development workflows related to schema management, data inspection/manipulation, and understanding database structure.

Key goals include:
* Visual schema design and modification.
* Intuitive data selection and filtering.
* Simplified CRUD operations.
* Tools for analyzing and improving schema normalization.

## Features

* **Visual Schema Designer:** Drag-and-drop interface (`@xyflow/react`) to create/modify tables, define columns (name, type, PK, constraints), and visualize relationships. Changes can be applied directly to the database.
* **Data Query Builder:** Select tables and columns, define JOIN conditions, and apply WHERE clauses through a UI to fetch and display data.
* **CRUD Operations Interface:** View table data and perform Insert, Update, and Delete operations via forms, with support for WHERE conditions on updates/deletes.
* **Normalization Analyzer:** Analyze table schemas against 1NF, 2NF, 3NF, and BCNF based on Primary Keys and user-defined Functional Dependencies.
* **Schema Decomposition:** Calculate and apply 3NF or BCNF decompositions based on analysis results (includes data migration and dropping the original table).

## Built With

* **Backend:**
    * Python 3.x
    * Flask
    * mysql-connector-python
    * python-dotenv
* **Frontend:**
    * React
    * React Router DOM
    * Axios
    * @xyflow/react (React Flow)
    * CSS (basic styling provided)
* **Database:**
    * MySQL

## Getting Started

Follow these steps to get a local copy up and running.

### Prerequisites

* **Python:** Version 3.7+ recommended. Ensure `pip` is available.
* **Node.js & npm:** Node.js version 14+ recommended (check `react-scripts` compatibility). npm is included with Node.js.
* **MySQL Server:** A running MySQL instance (local or remote) that the backend can connect to.

### Installation

1.  **Clone the repository:**
    ```bash
    git clone <your-repository-url>
    cd <repository-directory>
    ```

2.  **Backend Setup:**
    * Navigate to the backend directory (where `app.py` is located).
    * Create and activate a virtual environment (recommended):
        ```bash
        python -m venv venv
        # On Windows:
        .\venv\Scripts\activate
        # On macOS/Linux:
        source venv/bin/activate
        ```
    * Install Python dependencies:
        ```bash
        # Make sure you have a requirements.txt file generated
        # If not, create one based on imports: flask, flask-cors, python-dotenv, mysql-connector-python
        pip install -r requirements.txt # Or pip install flask flask-cors python-dotenv mysql-connector-python
        ```
    * Configure database connection (see [Configuration](#configuration) below).

3.  **Frontend Setup:**
    * Navigate to the frontend directory (where `package.json` is located).
    * Install Node.js dependencies:
        ```bash
        npm install
        ```

4.  **Database Setup:**
    * Ensure your MySQL server is running.
    * Create the database specified in your `.env` file (see below) if it doesn't exist.
        ```sql
        -- Example using MySQL client:
        CREATE DATABASE mydatabase; -- Or your chosen DB_NAME
        ```

## Configuration

The backend requires a `.env` file in its root directory to configure the database connection.

1.  Create a file named `.env` in the backend directory.
2.  Add the following environment variables, replacing the placeholder values with your actual MySQL credentials:

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

## Usage

1.  **Start the Backend Server:**
    * Make sure your Python virtual environment is activated (if used).
    * Navigate to the backend directory.
    * Run the Flask application:
        ```bash
        flask run
        # Or: python app.py
        ```
    * The backend API should now be running, typically on `http://localhost:5000`.

2.  **Start the Frontend Development Server:**
    * Navigate to the frontend directory.
    * Run the React development server:
        ```bash
        npm start
        ```
    * This should automatically open the application in your default web browser, usually at `http://localhost:3000`. If not, open it manually.

3.  **Use the Application:**
    * Navigate through the different sections using the navigation bar:
        * **Home:** Landing page.
        * **Canvas:** Design and modify database schemas. Click "Apply Schema Changes to DB" to save.
        * **Select:** Build and execute SELECT queries.
        * **CRUD:** Perform Create, Read, Update, Delete operations on table data.
        * **Normalization:** Analyze table schemas for normalization forms and perform decompositions.

## Contributing

Contributions are welcome! Please follow these steps:

1.  Fork the Project
2.  Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3.  Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4.  Push to the Branch (`git push origin feature/AmazingFeature`)
5.  Open a Pull Request

## License

Distributed under the MIT License. See `LICENSE` file for more information.

