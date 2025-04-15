import os
from flask import Flask, jsonify, request
from dotenv import load_dotenv
from flask_cors import CORS # Import CORS
import mysql.connector
from mysql.connector import Error

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
CORS(app) # Initialize CORS for the app

# Configuration (can be moved to a separate config file later)
# Example: Fetching DB credentials from environment variables
DB_HOST = os.getenv('MYSQL_HOST', 'localhost')
DB_USER = os.getenv('MYSQL_USER', 'root')
DB_PASSWORD = os.getenv('MYSQL_PASSWORD', '')
DB_NAME = os.getenv('MYSQL_DB', 'mydatabase')
# Database Connection Pool (or simple connection function)
def get_db_connection():
    """Establishes a connection to the MySQL database."""
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        return conn
    except Error as e:
        print(f"Error connecting to MySQL Database: {e}")
        # In a real app, you might want to handle this more gracefully
        return None

# Basic route to check if the server is running
@app.route('/api/ping', methods=['GET'])
def ping_pong():
    return jsonify(message='pong!')

# Route to test database connection
@app.route('/api/db_test', methods=['GET'])
def test_db():
    conn = None
    try:
        conn = get_db_connection()
        if conn and conn.is_connected():
            db_info = conn.get_server_info()
            print(f"Connected to MySQL Server version {db_info}")
            cursor = conn.cursor()
            cursor.execute("select database();")
            record = cursor.fetchone()
            print(f"You're connected to database: {record[0]}")
            cursor.close()
            return jsonify(message="Database connection successful!", server_info=db_info, database=record[0])
        else:
            return jsonify(error="Database connection failed."), 500
    except Error as e:
        print(f"Error during DB test: {e}")
        return jsonify(error=f"Database connection error: {e}"), 500
    finally:
        if conn and conn.is_connected():
            conn.close()
            print("MySQL connection is closed")

# --- Helper Function for Sanitization ---
def sanitize_identifier(name):
    if not name:
        return None
    # Basic sanitization: replace spaces/invalid chars with underscore, ensure valid start
    sanitized = "".join(c if c.isalnum() or c == '_' else '_' for c in name.replace(' ', '_'))
    if not sanitized or not (sanitized[0].isalpha() or sanitized[0] == '_'):
        sanitized = f"tbl_{sanitized}" # Prepend if starts invalidly
    # Avoid SQL keywords (very basic check, needs improvement for production)
    if sanitized.upper() in ['TABLE', 'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'WHERE', 'FROM', 'CREATE', 'ALTER', 'DROP', 'INDEX', 'KEY', 'PRIMARY', 'FOREIGN']:
            sanitized = f"tbl_{sanitized}"
    return sanitized

# Endpoint to handle schema creation/update
@app.route('/api/schema', methods=['POST'])
def handle_schema():
    """
    Receives detailed schema design data (tables, attributes, relationships)
    and attempts to create the corresponding database schema using a
    destructive recreation strategy (DROP IF EXISTS, then CREATE).
    """
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    schema_data = request.get_json()
    if not schema_data:
        return jsonify({"error": "No JSON data received"}), 400

    print("Received schema data:", schema_data)

    tables_data = schema_data.get('tables', [])
    relationships_data = schema_data.get('relationships', [])

    if not tables_data:
        return jsonify({"message": "No table data found in schema"}), 200

    conn = None
    cursor = None
    created_tables_details = {} # Store details of created tables {node_id: safe_name}
    added_foreign_keys = []
    errors = {"table_creation": [], "fk_creation": []}

    # --- Phase 0: Drop Existing Tables (Destructive Recreation) ---
    try:
        conn = get_db_connection()
        if not conn or not conn.is_connected():
            return jsonify({"error": "Database connection failed"}), 500
        cursor = conn.cursor()

        # Disable foreign key checks temporarily for dropping
        cursor.execute("SET FOREIGN_KEY_CHECKS=0;")
        print("Disabled foreign key checks.")

        tables_to_drop = []
        for table_info in tables_data:
             safe_name = sanitize_identifier(table_info.get('name'))
             if safe_name:
                 tables_to_drop.append(safe_name)

        for safe_table_name in reversed(tables_to_drop): # Drop in reverse order potentially helps with dependencies if FK checks were on
             try:
                 drop_sql = f"DROP TABLE IF EXISTS `{safe_table_name}`;"
                 print(f"Executing SQL: {drop_sql}")
                 cursor.execute(drop_sql)
             except Error as drop_error:
                 print(f"Warning: Error dropping table {safe_table_name}: {drop_error}")
                 # Log warning but continue, as IF EXISTS should prevent fatal errors
                 errors["table_creation"].append({"table_name": safe_table_name, "warning": f"Error during drop: {drop_error}"})

        conn.commit() # Commit the drops
        print("Finished dropping tables.")

        # --- Phase 1: Create Tables ---
        # Re-enable foreign key checks before creating tables and constraints
        cursor.execute("SET FOREIGN_KEY_CHECKS=1;")
        print("Re-enabled foreign key checks.")

        for table_info in tables_data:
            original_table_name = table_info.get('name')
            node_id = table_info.get('id') # Get the node ID for FK mapping
            attributes = table_info.get('attributes', [])

            safe_table_name = sanitize_identifier(original_table_name)
            if not safe_table_name or not node_id:
                errors["table_creation"].append({"table_info": table_info, "error": "Missing table name or node ID"})
                continue

            if not attributes:
                 errors["table_creation"].append({"table_name": safe_table_name, "error": "Table has no attributes defined"})
                 continue # Skip tables without attributes

            column_definitions = []
            primary_keys = []
            for attr in attributes:
                col_name = sanitize_identifier(attr.get('name'))
                col_type = attr.get('type', 'VARCHAR(255)') # Default type
                # Basic type validation/mapping (expand as needed)
                if col_type.upper() not in ['INT', 'VARCHAR(255)', 'TEXT', 'DATE', 'BOOLEAN', 'DECIMAL(10,2)']: # Example valid types
                    col_type = 'VARCHAR(255)' # Fallback

                if not col_name:
                    errors["table_creation"].append({"table_name": safe_table_name, "error": f"Attribute missing name: {attr}"})
                    continue # Skip invalid attribute

                col_def_parts = [f"`{col_name}`", col_type]
                if attr.get('isNotNull', False):
                    col_def_parts.append("NOT NULL")
                if attr.get('isUnique', False):
                    # Note: Adding UNIQUE here might conflict if it's also part of a composite PK.
                    # A more robust solution might add UNIQUE constraints separately.
                    col_def_parts.append("UNIQUE")

                column_definitions.append(" ".join(col_def_parts))

                if attr.get('isPK', False):
                    primary_keys.append(f"`{col_name}`")

            if not column_definitions:
                 errors["table_creation"].append({"table_name": safe_table_name, "error": "No valid column definitions generated"})
                 continue

            # Construct CREATE TABLE statement
            sql = f"CREATE TABLE IF NOT EXISTS `{safe_table_name}` (\n"
            sql += ",\n".join(f"    {col_def}" for col_def in column_definitions)
            if primary_keys:
                sql += f",\n    PRIMARY KEY ({', '.join(primary_keys)})"
            sql += "\n);"

            try:
                print(f"Executing SQL: {sql}")
                cursor.execute(sql)
                created_tables_details[node_id] = safe_table_name # Map node ID to safe name
            except Error as table_error:
                print(f"Error creating table {safe_table_name}: {table_error}")
                errors["table_creation"].append({"table_name": safe_table_name, "sql": sql, "error": str(table_error)})

        # Commit table creations before attempting FKs
        if not errors["table_creation"]: # Only commit if table creation had no errors initially reported
             conn.commit()
             print("Table creation phase committed.")
        else:
             print("Errors during table creation phase, rolling back.")
             conn.rollback() # Rollback if table creation failed
             # Skip FK creation if tables failed
             raise Exception("Table creation failed, cannot proceed to FKs.")


        # --- Phase 2: Add Foreign Keys ---
        # This runs only if table creation was successful and committed
        for fk_info in relationships_data:
            source_node_id = fk_info.get('sourceTableId')
            target_node_id = fk_info.get('targetTableId')

            source_table_name = created_tables_details.get(source_node_id)
            target_table_name = created_tables_details.get(target_node_id)

            if not source_table_name or not target_table_name:
                errors["fk_creation"].append({"fk_info": fk_info, "error": "Could not find source or target table for relationship"})
                continue

            # --- Simplification: Assume target PK is 'id' and type INT ---
            # --- Simplification: Generate FK column name automatically ---
            target_pk_col = 'id' # Assumed target PK column name
            fk_col_name = sanitize_identifier(f"{target_table_name}_id") # Auto-generated FK column name
            fk_col_type = 'INT' # Assumed FK column type

            # 1. Add the FK column to the source table
            sql_add_col = f"ALTER TABLE `{source_table_name}` ADD COLUMN IF NOT EXISTS `{fk_col_name}` {fk_col_type};" # Added IF NOT EXISTS
            # 2. Add the FK constraint
            constraint_name = sanitize_identifier(f"fk_{source_table_name}_{target_table_name}")
            sql_add_fk = f"""
            ALTER TABLE `{source_table_name}`
            ADD CONSTRAINT `{constraint_name}`
            FOREIGN KEY (`{fk_col_name}`)
            REFERENCES `{target_table_name}` (`{target_pk_col}`);
            """

            try:
                print(f"Executing SQL: {sql_add_col}")
                cursor.execute(sql_add_col)
                print(f"Executing SQL: {sql_add_fk.strip()}")
                cursor.execute(sql_add_fk)
                added_foreign_keys.append({
                    "source_table": source_table_name,
                    "fk_column": fk_col_name,
                    "target_table": target_table_name,
                    "target_pk_column": target_pk_col,
                    "constraint_name": constraint_name
                })
            except Error as fk_error:
                 print(f"Error adding FK from {source_table_name} to {target_table_name}: {fk_error}")
                 # Check for specific errors like duplicate column or constraint
                 if fk_error.errno == 1060: # Duplicate column name
                     print(f"FK column '{fk_col_name}' likely already exists in '{source_table_name}'. Skipping ADD COLUMN.")
                     # Try adding constraint anyway if column exists
                     try:
                         print(f"Attempting to add FK constraint directly: {sql_add_fk.strip()}")
                         cursor.execute(sql_add_fk)
                         added_foreign_keys.append({
                             "source_table": source_table_name, "fk_column": fk_col_name,
                             "target_table": target_table_name, "target_pk_column": target_pk_col,
                             "constraint_name": constraint_name
                         })
                     except Error as fk_constraint_error:
                          print(f"Error adding FK constraint directly: {fk_constraint_error}")
                          errors["fk_creation"].append({
                              "source_table": source_table_name, "target_table": target_table_name,
                              "error": f"Failed to add FK constraint even after column likely existed: {fk_constraint_error}"
                          })

                 elif fk_error.errno == 1061: # Duplicate key name
                      print(f"FK constraint name '{constraint_name}' likely already exists. Skipping ADD CONSTRAINT.")
                      # Assume FK is already correctly set up if name exists
                      pass # Or potentially add to added_foreign_keys with a note?
                 else:
                     errors["fk_creation"].append({
                         "source_table": source_table_name, "target_table": target_table_name,
                         "sql_add_col": sql_add_col, "sql_add_fk": sql_add_fk,
                         "error": str(fk_error)
                     })

        # Commit FK changes if any were attempted
        conn.commit()
        print("Foreign key creation phase committed.")


    except Exception as e: # Catch general errors including DB connection or the explicit raise
        print(f"Error during schema handling: {e}")
        # Ensure errors dict exists even if connection failed early
        if "table_creation" not in errors: errors["table_creation"] = []
        if "fk_creation" not in errors: errors["fk_creation"] = []
        errors["general"] = str(e) # Add general error
        if conn: conn.rollback() # Rollback any partial changes
    finally:
        if cursor:
            # Ensure FK checks are re-enabled even if errors occurred
            try:
                cursor.execute("SET FOREIGN_KEY_CHECKS=1;")
                print("Ensured foreign key checks re-enabled.")
            except Error as fk_check_error:
                 print(f"Warning: Could not re-enable FK checks: {fk_check_error}")
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
            print("MySQL connection is closed")

    # --- Construct Final Response ---
    final_message = "Schema processing attempted."
    if not errors.get("table_creation") and not errors.get("fk_creation") and not errors.get("general"):
        final_message = "Schema created successfully."
    elif created_tables_details or added_foreign_keys:
         final_message = "Schema processing completed with errors."

    response = {
        "message": final_message,
        "created_tables": list(created_tables_details.values()), # List of names created
        "added_foreign_keys": added_foreign_keys,
        "errors": errors # Contains table_creation, fk_creation, general
    }
    # Determine status code based on errors
    status_code = 200 if not errors.get("table_creation") and not errors.get("fk_creation") and not errors.get("general") else 400
    if status_code == 400 and (created_tables_details or added_foreign_keys):
        status_code = 207 # Multi-Status: indicates partial success

    return jsonify(response), status_code

# Endpoint to get list of tables
@app.route('/api/tables', methods=['GET'])
def get_tables():
    """Fetches and returns a list of tables from the database."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn or not conn.is_connected():
            return jsonify({"error": "Database connection failed"}), 500

        cursor = conn.cursor()
        cursor.execute("SHOW TABLES;")
        tables = [table[0] for table in cursor.fetchall()] # Extract table names
        return jsonify({"tables": tables}), 200

    except Error as e:
        print(f"Error fetching tables: {e}")
        return jsonify({"error": f"Database error fetching tables: {e}"}), 500
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
            print("MySQL connection is closed")

# Endpoint to get details for a specific table
@app.route('/api/table_details/<table_name>', methods=['GET'])
def get_table_details(table_name):
    """Fetches column details for a specific table."""
    # Basic sanitization for the table name used in the query
    safe_table_name = sanitize_identifier(table_name) # Use existing helper
    if not safe_table_name:
        return jsonify({"error": "Invalid table name provided"}), 400

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn or not conn.is_connected():
            return jsonify({"error": "Database connection failed"}), 500

        cursor = conn.cursor(dictionary=True) # Fetch results as dictionaries

        # Use DESCRIBE to get column info
        describe_sql = f"DESCRIBE `{safe_table_name}`;"
        print(f"Executing SQL: {describe_sql}")
        cursor.execute(describe_sql)
        columns_raw = cursor.fetchall()

        attributes = []
        for col in columns_raw:
            # Map DESCRIBE output to the frontend attribute format
            col_type_raw = col.get('Type', '').upper()
            col_type = col_type_raw
            # Basic type normalization (can be expanded)
            if 'VARCHAR' in col_type_raw: col_type = 'VARCHAR(255)'
            elif 'INT' in col_type_raw: col_type = 'INT'
            elif 'TEXT' in col_type_raw: col_type = 'TEXT'
            elif 'DATE' in col_type_raw: col_type = 'DATE'
            elif 'BOOL' in col_type_raw: col_type = 'BOOLEAN'
            elif 'DECIMAL' in col_type_raw: col_type = 'DECIMAL(10,2)'

            attributes.append({
                "name": col.get('Field'),
                "type": col_type,
                "isPK": col.get('Key') == 'PRI',
                "isNotNull": col.get('Null') == 'NO',
                "isUnique": col.get('Key') == 'UNI',
            })

        return jsonify({"table_name": safe_table_name, "attributes": attributes}), 200

    except Error as e:
        print(f"Error fetching details for table {safe_table_name}: {e}")
        if e.errno == 1146: # Table doesn't exist
             return jsonify({"error": f"Table '{safe_table_name}' not found."}), 404
        return jsonify({"error": f"Database error fetching table details: {e}"}), 500
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
            print("MySQL connection is closed")


# @app.route('/api/query', methods=['POST'])
# def handle_query():
#     # Logic for executing select queries
#     pass
#     pass

# @app.route('/api/crud', methods=['POST', 'PUT', 'DELETE'])
# def handle_crud():
#     # Logic for CRUD operations
#     pass


if __name__ == '__main__':
    # Use a port different from React's default (3000)
    app.run(host='0.0.0.0', debug=True, port=5000)