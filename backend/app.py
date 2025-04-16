import os
from flask import Flask, jsonify, request
from dotenv import load_dotenv
from flask_cors import CORS # Import CORS
import mysql.connector
from mysql.connector import Error
from collections import defaultdict # For grouping columns by table

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
CORS(app) # Initialize CORS for the app

# Configuration (can be moved to a separate config file later)
DB_HOST = os.getenv('MYSQL_HOST', 'localhost')
DB_USER = os.getenv('MYSQL_USER', 'root')
DB_PASSWORD = os.getenv('MYSQL_PASSWORD', '')
DB_NAME = os.getenv('MYSQL_DB', 'mydatabase')

# Database Connection Helper
def get_db_connection():
    """Establishes a connection to the MySQL database."""
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME # Connect directly to the target DB
        )
        return conn
    except Error as e:
        print(f"Error connecting to MySQL Database: {e}")
        return None

# --- Helper Function for Sanitization ---
def sanitize_identifier(name):
    if not name: return None
    sanitized = "".join(c if c.isalnum() or c == '_' else '_' for c in name.replace(' ', '_'))
    if not sanitized or not (sanitized[0].isalpha() or sanitized[0] == '_'):
        sanitized = f"tbl_{sanitized}"
    if sanitized.upper() in ['TABLE', 'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'WHERE', 'FROM', 'CREATE', 'ALTER', 'DROP', 'INDEX', 'KEY', 'PRIMARY', 'FOREIGN']:
        sanitized = f"tbl_{sanitized}"
    return sanitized

# --- API Endpoints ---

@app.route('/api/ping', methods=['GET'])
def ping_pong():
    return jsonify(message='pong!')

@app.route('/api/db_test', methods=['GET'])
def test_db():
    # (Code remains the same as before)
    conn = None
    try:
        conn = get_db_connection()
        if conn and conn.is_connected():
            db_info = conn.get_server_info()
            cursor = conn.cursor()
            cursor.execute("select database();")
            record = cursor.fetchone()
            cursor.close()
            return jsonify(message="Database connection successful!", server_info=db_info, database=record[0])
        else:
            return jsonify(error="Database connection failed."), 500
    except Error as e:
        return jsonify(error=f"Database connection error: {e}"), 500
    finally:
        if conn and conn.is_connected(): conn.close()

@app.route('/api/schema', methods=['POST'])
def handle_schema():
    """
    Receives schema design from frontend.
    Compares with current DB state. Drops tables removed from canvas.
    Drops/Recreates tables present on canvas (destructive update).
    """
    if not request.is_json: return jsonify({"error": "Request must be JSON"}), 400
    schema_data = request.get_json()
    if not schema_data: return jsonify({"error": "No JSON data received"}), 400

    print("Received schema data:", schema_data)
    tables_from_canvas_data = schema_data.get('tables', [])
    relationships_data = schema_data.get('relationships', []) # FKs defined on canvas

    conn = None
    cursor = None
    created_tables_details = {}
    added_foreign_keys = []
    dropped_tables = []
    errors = {"fetching": [], "dropping": [], "table_creation": [], "fk_creation": []}

    try:
        conn = get_db_connection()
        if not conn or not conn.is_connected():
            return jsonify({"error": "Database connection failed"}), 500
        cursor = conn.cursor()
        db_name = DB_NAME

        # --- Phase 0a: Get existing tables from DB ---
        existing_db_tables = set()
        try:
            cursor.execute("SHOW TABLES;")
            for (table_name,) in cursor.fetchall():
                existing_db_tables.add(table_name)
            print(f"Existing tables in DB: {existing_db_tables}")
        except Error as e:
            errors["fetching"].append(f"Error fetching existing tables: {e}")
            raise Exception("Failed to fetch existing tables.") # Stop processing

        # --- Phase 0b: Identify tables to drop (in DB but not on canvas) ---
        tables_on_canvas_safe_names = {sanitize_identifier(t.get('name')) for t in tables_from_canvas_data if t.get('name')}
        print(f"Tables on canvas (safe names): {tables_on_canvas_safe_names}")
        tables_to_explicitly_drop = existing_db_tables - tables_on_canvas_safe_names
        print(f"Tables to explicitly drop: {tables_to_explicitly_drop}")

        # --- Phase 0c: Drop tables ---
        cursor.execute("SET FOREIGN_KEY_CHECKS=0;")
        print("Disabled foreign key checks.")

        # Drop tables removed from canvas
        for table_to_drop in reversed(list(tables_to_explicitly_drop)): # Reverse order might help
             try:
                 drop_sql = f"DROP TABLE IF EXISTS `{table_to_drop}`;"
                 print(f"Executing SQL (Explicit Drop): {drop_sql}")
                 cursor.execute(drop_sql)
                 dropped_tables.append(table_to_drop)
             except Error as drop_error:
                 print(f"Warning: Error explicitly dropping table {table_to_drop}: {drop_error}")
                 errors["dropping"].append({"table_name": table_to_drop, "error": str(drop_error)})

        # Drop tables that ARE on the canvas (for recreation)
        tables_to_recreate_safe_names = list(tables_on_canvas_safe_names)
        for safe_table_name in reversed(tables_to_recreate_safe_names):
             try:
                 # Only drop if it actually existed (handles case where it was just added to canvas)
                 if safe_table_name in existing_db_tables:
                     drop_sql = f"DROP TABLE IF EXISTS `{safe_table_name}`;"
                     print(f"Executing SQL (Recreation Drop): {drop_sql}")
                     cursor.execute(drop_sql)
                 else:
                      print(f"Skipping drop for {safe_table_name} as it doesn't exist in DB yet.")
             except Error as drop_error:
                 print(f"Warning: Error dropping table {safe_table_name} for recreation: {drop_error}")
                 errors["dropping"].append({"table_name": safe_table_name, "warning": f"Error during recreation drop: {drop_error}"})

        conn.commit() # Commit all drops
        print("Finished dropping tables phase.")

        # --- Phase 1: Create Tables ---
        cursor.execute("SET FOREIGN_KEY_CHECKS=1;") # Re-enable FK checks
        print("Re-enabled foreign key checks.")

        node_id_to_safe_name = {} # Map node ID to safe name for FK creation
        for table_info in tables_from_canvas_data:
            # (Table creation logic remains the same as before)
            original_table_name = table_info.get('name')
            node_id = table_info.get('id')
            attributes = table_info.get('attributes', [])
            safe_table_name = sanitize_identifier(original_table_name)

            if not safe_table_name or not node_id:
                errors["table_creation"].append({"table_info": table_info, "error": "Missing table name or node ID"})
                continue
            if not attributes:
                 errors["table_creation"].append({"table_name": safe_table_name, "error": "Table has no attributes defined"})
                 continue

            column_definitions = []
            primary_keys = []
            for attr in attributes:
                col_name = sanitize_identifier(attr.get('name'))
                col_type = attr.get('type', 'VARCHAR(255)')
                if col_type.upper() not in ['INT', 'VARCHAR(255)', 'TEXT', 'DATE', 'BOOLEAN', 'DECIMAL(10,2)']:
                    col_type = 'VARCHAR(255)'
                if not col_name:
                    errors["table_creation"].append({"table_name": safe_table_name, "error": f"Attribute missing name: {attr}"})
                    continue

                col_def_parts = [f"`{col_name}`", col_type]
                if attr.get('isNotNull', False): col_def_parts.append("NOT NULL")
                if attr.get('isUnique', False): col_def_parts.append("UNIQUE")
                column_definitions.append(" ".join(col_def_parts))
                if attr.get('isPK', False): primary_keys.append(f"`{col_name}`")

            if not column_definitions:
                 errors["table_creation"].append({"table_name": safe_table_name, "error": "No valid column definitions generated"})
                 continue

            sql = f"CREATE TABLE `{safe_table_name}` (\n" # Removed IF NOT EXISTS
            sql += ",\n".join(f"    {col_def}" for col_def in column_definitions)
            if primary_keys: sql += f",\n    PRIMARY KEY ({', '.join(primary_keys)})"
            sql += "\n);"

            try:
                print(f"Executing SQL: {sql}")
                cursor.execute(sql)
                node_id_to_safe_name[node_id] = safe_table_name # Store mapping after successful creation
            except Error as table_error:
                print(f"Error creating table {safe_table_name}: {table_error}")
                errors["table_creation"].append({"table_name": safe_table_name, "sql": sql, "error": str(table_error)})

        # Commit table creations before attempting FKs
        if not errors["table_creation"]:
             conn.commit()
             print("Table creation phase committed.")
        else:
             print("Errors during table creation phase, rolling back.")
             conn.rollback()
             raise Exception("Table creation failed, cannot proceed to FKs.")

        # --- Phase 2: Add Foreign Keys ---
        for fk_info in relationships_data:
            source_node_id = fk_info.get('sourceTableId')
            target_node_id = fk_info.get('targetTableId')

            # Map node IDs from frontend back to the actual (safe) table names created
            source_table_name = node_id_to_safe_name.get(source_node_id)
            target_table_name = node_id_to_safe_name.get(target_node_id)

            if not source_table_name or not target_table_name:
                errors["fk_creation"].append({"fk_info": fk_info, "error": f"Could not map source ({source_node_id}) or target ({target_node_id}) node ID to created table name"})
                continue

            # --- Determine FK column name and target PK column name ---
            target_pk_col = 'id' # Default assumption
            target_table_data = next((t for t in tables_from_canvas_data if t.get('id') == target_node_id), None)
            if target_table_data:
                pk_attr = next((a for a in target_table_data.get('attributes', []) if a.get('isPK')), None)
                if pk_attr:
                    target_pk_col = sanitize_identifier(pk_attr.get('name', 'id'))

            fk_col_name = sanitize_identifier(f"{target_table_name}_{target_pk_col}")
            fk_col_type = 'INT' # Default assumption, ideally fetch target PK type

            # 1. Add the FK column to the source table (Removed IF NOT EXISTS)
            sql_add_col = f"ALTER TABLE `{source_table_name}` ADD COLUMN `{fk_col_name}` {fk_col_type};"
            # 2. Add the FK constraint
            constraint_name = sanitize_identifier(f"fk_{source_table_name}_{target_table_name}_{fk_col_name}")
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
                    "source_table": source_table_name, "fk_column": fk_col_name,
                    "target_table": target_table_name, "target_pk_column": target_pk_col,
                    "constraint_name": constraint_name
                })
            except Error as fk_error:
                 print(f"Error adding FK from {source_table_name} to {target_table_name}: {fk_error}")
                 if fk_error.errno == 1060: # Duplicate column
                     print(f"FK column '{fk_col_name}' likely already exists. Attempting ADD CONSTRAINT only.")
                     try:
                         cursor.execute(sql_add_fk)
                         added_foreign_keys.append({
                             "source_table": source_table_name, "fk_column": fk_col_name,
                             "target_table": target_table_name, "target_pk_column": target_pk_col,
                             "constraint_name": constraint_name
                         })
                     except Error as fk_constraint_error:
                          print(f"Error adding FK constraint directly: {fk_constraint_error}")
                          errors["fk_creation"].append({"source_table": source_table_name, "target_table": target_table_name, "error": f"Failed ADD CONSTRAINT after column existed: {fk_constraint_error}"})
                 elif fk_error.errno == 1061: # Duplicate key name
                      print(f"FK constraint name '{constraint_name}' likely already exists. Skipping.")
                 elif fk_error.errno == 1822: # Failed adding foreign key constraint (e.g., type mismatch)
                      print(f"Failed adding FK constraint '{constraint_name}'. Check column types/existence.")
                      errors["fk_creation"].append({"source_table": source_table_name, "target_table": target_table_name, "error": f"Failed adding FK constraint '{constraint_name}': {fk_error}"})
                 else:
                     errors["fk_creation"].append({"source_table": source_table_name, "target_table": target_table_name, "sql_add_col": sql_add_col, "sql_add_fk": sql_add_fk, "error": str(fk_error)})

        conn.commit()
        print("Foreign key creation phase committed.")

    except Exception as e:
        print(f"Error during schema handling: {e}")
        if "table_creation" not in errors: errors["table_creation"] = []
        if "fk_creation" not in errors: errors["fk_creation"] = []
        if "dropping" not in errors: errors["dropping"] = []
        if "fetching" not in errors: errors["fetching"] = []
        errors["general"] = str(e)
        if conn: conn.rollback()
    finally:
        if cursor:
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
    has_errors = any(errors.get(k) for k in errors if k != 'general') or errors.get("general")
    has_success = created_tables_details or added_foreign_keys or dropped_tables

    if not has_errors:
        final_message = "Schema applied successfully."
    elif has_success:
         final_message = "Schema applied with errors/warnings."

    response = {
        "message": final_message,
        "created_tables": list(created_tables_details.values()),
        "dropped_tables": dropped_tables,
        "added_foreign_keys": added_foreign_keys,
        "errors": errors
    }
    status_code = 200 if not has_errors else (207 if has_success else 400)

    return jsonify(response), status_code


@app.route('/api/tables', methods=['GET'])
def get_tables():
    # (Code remains the same as before)
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn or not conn.is_connected(): return jsonify({"error": "Database connection failed"}), 500
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES;")
        tables = [table[0] for table in cursor.fetchall()]
        return jsonify({"tables": tables}), 200
    except Error as e:
        return jsonify({"error": f"Database error fetching tables: {e}"}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


@app.route('/api/table_details/<table_name>', methods=['GET'])
def get_table_details(table_name):
    # (Code remains the same as before)
    safe_table_name = sanitize_identifier(table_name)
    if not safe_table_name: return jsonify({"error": "Invalid table name provided"}), 400
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn or not conn.is_connected(): return jsonify({"error": "Database connection failed"}), 500
        cursor = conn.cursor(dictionary=True)
        describe_sql = f"DESCRIBE `{safe_table_name}`;"
        cursor.execute(describe_sql)
        columns_raw = cursor.fetchall()
        attributes = []
        for col in columns_raw:
            col_type_raw = col.get('Type', '').upper()
            col_type = col_type_raw
            if 'VARCHAR' in col_type_raw: col_type = 'VARCHAR(255)'
            elif 'INT' in col_type_raw: col_type = 'INT'
            elif 'TEXT' in col_type_raw: col_type = 'TEXT'
            elif 'DATE' in col_type_raw: col_type = 'DATE'
            elif 'BOOL' in col_type_raw: col_type = 'BOOLEAN'
            elif 'DECIMAL' in col_type_raw: col_type = 'DECIMAL(10,2)'
            attributes.append({
                "name": col.get('Field'), "type": col_type,
                "isPK": col.get('Key') == 'PRI', "isNotNull": col.get('Null') == 'NO',
                "isUnique": col.get('Key') == 'UNI',
            })
        return jsonify({"table_name": safe_table_name, "attributes": attributes}), 200
    except Error as e:
        if e.errno == 1146: return jsonify({"error": f"Table '{safe_table_name}' not found."}), 404
        return jsonify({"error": f"Database error fetching table details: {e}"}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


@app.route('/api/current_schema', methods=['GET'])
def get_current_schema():
    """Fetches the current schema (tables, columns, FKs) from the database."""
    conn = None
    cursor = None
    schema = {'tables': {}, 'relationships': []}

    try:
        conn = get_db_connection()
        if not conn or not conn.is_connected():
            return jsonify({"error": "Database connection failed"}), 500

        cursor = conn.cursor(dictionary=True)
        db_name = DB_NAME

        # 1. Get Tables
        cursor.execute("SHOW TABLES;")
        tables_raw = cursor.fetchall()
        table_names = [t['Tables_in_' + db_name] for t in tables_raw]

        if not table_names:
            return jsonify(schema), 200

        # 2. Get Columns and Constraints for each table
        for table_name in table_names:
            safe_table_name = sanitize_identifier(table_name)
            if not safe_table_name: continue

            cols_sql = """
            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_KEY, EXTRA
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION;
            """
            cursor.execute(cols_sql, (db_name, table_name))
            columns_raw = cursor.fetchall()

            attributes = []
            for col in columns_raw:
                col_type_raw = col.get('DATA_TYPE', '').upper()
                col_type = col_type_raw
                if 'VARCHAR' in col_type_raw: col_type = 'VARCHAR(255)'
                elif 'INT' in col_type_raw: col_type = 'INT'
                elif 'TEXT' in col_type_raw: col_type = 'TEXT'
                elif 'DATE' in col_type_raw: col_type = 'DATE'
                elif 'BOOL' in col_type_raw: col_type = 'BOOLEAN'
                elif 'DECIMAL' in col_type_raw: col_type = 'DECIMAL(10,2)'
                attributes.append({
                    "name": col.get('COLUMN_NAME'), "type": col_type,
                    "isPK": col.get('COLUMN_KEY') == 'PRI', "isNotNull": col.get('IS_NULLABLE') == 'NO',
                    "isUnique": col.get('COLUMN_KEY') == 'UNI',
                })
            schema['tables'][table_name] = {"name": table_name, "attributes": attributes}

        # 3. Get Foreign Keys
        fks_sql = """
        SELECT TABLE_NAME, COLUMN_NAME, CONSTRAINT_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
        FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = %s AND REFERENCED_TABLE_SCHEMA IS NOT NULL;
        """
        cursor.execute(fks_sql, (db_name,))
        fks_raw = cursor.fetchall()
        print(f"[DEBUG] Raw FKs fetched from DB: {fks_raw}") # DEBUG LOG

        for fk in fks_raw:
            print(f"[DEBUG] Processing FK row: {fk}") # DEBUG LOG
            # Ensure source/target use table names for consistency with edge generation logic
            source_table = fk['TABLE_NAME']
            target_table = fk['REFERENCED_TABLE_NAME']
            if source_table in schema['tables'] and target_table in schema['tables']:
                 print(f"[DEBUG] Adding relationship: {source_table} -> {target_table}") # DEBUG LOG
                 schema['relationships'].append({
                     "id": f"fk-{fk['CONSTRAINT_NAME']}",
                     "source": source_table, # Use table name
                     "target": target_table, # Use table name
                 })
            else:
                 print(f"[DEBUG] Skipping FK: Source '{source_table}' or Target '{target_table}' not found in schema tables dict.") # DEBUG LOG

        return jsonify(schema), 200
    except Error as e:
        print(f"Error fetching current schema: {e}")
        return jsonify({"error": f"Database error fetching current schema: {e}"}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
        print("MySQL connection closed after fetching current schema")


# @app.route('/api/query', methods=['POST'])
# def handle_query():
#     # Logic for executing select queries
#     pass

# @app.route('/api/crud', methods=['POST', 'PUT', 'DELETE'])
# def handle_crud():
#     # Logic for CRUD operations
#     pass


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000)