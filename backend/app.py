import os
from flask import Flask, jsonify, request
from dotenv import load_dotenv
from flask_cors import CORS # Import CORS
import mysql.connector
from mysql.connector import Error
from collections import defaultdict # For grouping columns by table
from itertools import chain, combinations # For closure/key algorithms
from copy import deepcopy

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
CORS(app) # Initialize CORS for the app

# Configuration (can be moved to a separate config file later)
DB_HOST = os.getenv('MYSQL_HOST', 'localhost')
DB_USER = os.getenv('MYSQL_USER', 'root')
DB_PASSWORD = os.getenv('MYSQL_PASSWORD', '')
DB_NAME = os.getenv('MYSQL_DB', 'mydatabase')

ALLOWED_AGGREGATES = {'COUNT', 'SUM', 'AVG', 'MIN', 'MAX'}
ALLOWED_JOIN_TYPES = {'INNER', 'LEFT', 'RIGHT'}
ALLOWED_OPERATORS = {'=', '!=', '>', '<', '>=', '<=', 'LIKE', 'NOT LIKE', 'IS NULL', 'IS NOT NULL'}


MYSQL_TYPE_MAP = {
    'INT': 'INT',
    'VARCHAR(255)': 'VARCHAR(255)',
    'TEXT': 'TEXT',
    'DATE': 'DATE',
    'BOOLEAN': 'BOOLEAN', # Or TINYINT(1) depending on creation
    'DECIMAL(10,2)': 'DECIMAL(10, 2)',
    'TIMESTAMP': 'TIMESTAMP',
    'FLOAT': 'FLOAT',
    # Add more mappings as needed based on your get_table_details logic
}


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

# --- Helper to build WHERE clause string and params ---
def build_where_clause(conditions_list):
    """
    Builds a WHERE clause string and parameter list from a list of condition objects.
    Handles AND/OR connectors between conditions.
    """
    where_clause_parts = []
    where_params = []
    if not isinstance(conditions_list, list):
        raise ValueError("WHERE conditions must be a list")

    for index, condition in enumerate(conditions_list):
        column = sanitize_identifier(condition.get('column'))
        operator = str(condition.get('operator', '=')).strip().upper()
        value = condition.get('value')
        # Get connector, default to AND for conditions after the first
        connector = str(condition.get('connector', 'AND')).strip().upper() if index > 0 else None

        if not column: raise ValueError(f"Incomplete where condition (missing column): {condition}")
        if operator not in ALLOWED_OPERATORS: raise ValueError(f"Invalid where operator: {operator}")
        if connector and connector not in ('AND', 'OR'): raise ValueError(f"Invalid connector: {connector}")

        # Add connector (AND/OR) before the condition (if not the first condition)
        if connector:
            where_clause_parts.append(connector)

        # Build the condition part
        safe_col_ref = f"`{column}`" # Table name comes from the main query part (FROM/UPDATE/DELETE)
        if operator in ('IS NULL', 'IS NOT NULL'):
            where_clause_parts.append(f"{safe_col_ref} {operator}")
            if value is not None and value != '':
                print(f"Warning: Value '{value}' provided for operator '{operator}' will be ignored.")
        else:
            where_clause_parts.append(f"{safe_col_ref} {operator} %s")
            where_params.append(value)

    if not where_clause_parts:
        # Return empty string and list if no valid conditions were processed
        # Let the calling function decide if an empty WHERE is allowed/required
        return "", []
        # Or raise ValueError("WHERE clause cannot be empty for UPDATE/DELETE operations.") if needed

    # Join parts with spaces
    # Consider adding parentheses for complex logic, but linear joining is simpler for now
    final_where_sql = " ".join(where_clause_parts)

    # Basic check for dangling connector if only one clause remained after filtering? (unlikely with UI)
    # if final_where_sql == "AND" or final_where_sql == "OR": return "", []

    return final_where_sql, where_params
# --- End Helper ---

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


@app.route('/api/execute_select', methods=['POST'])
def execute_select_query():
    # ... (Keep initial request validation) ...
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    query_def = request.get_json()
    if not query_def:
        return jsonify({"error": "No JSON data received"}), 400
    print(f"Received query definition: {query_def}")

    # --- Extract and Validate Query Definition ---
    select_parts = query_def.get('select', [])
    from_tables = query_def.get('from', []) # List of tables selected in UI
    join_conditions = query_def.get('joins', [])
    where_conditions = query_def.get('where', [])
    group_by_columns = query_def.get('groupBy', [])

    # --- Basic Validation ---
    if not from_tables:
        return jsonify({"error": "Query must specify at least one table in 'from'"}), 400
    if not select_parts:
        return jsonify({"error": "Query must specify columns or aggregates in 'select'"}), 400

    # --- *** NEW VALIDATION: Require JOINs for multiple tables *** ---
    if len(from_tables) > 1 and not join_conditions:
        return jsonify({"error": f"Multiple tables ({', '.join(from_tables)}) selected. Please define JOIN conditions between them."}), 400
    # --- *** END NEW VALIDATION *** ---

    sql_parts = []
    params = []

    # --- 1. Build SELECT Clause ---
    # ... (Keep SELECT clause logic the same, including has_aggregates check) ...
    select_clause_items = []
    has_aggregates = any(p.get('type') == 'aggregate' for p in select_parts)
    tables_in_select = set() # Keep track of tables used in SELECT

    for item in select_parts:
        item_type = item.get('type')
        table = sanitize_identifier(item.get('table'))
        column = item.get('column')
        tables_in_select.add(table) # Record table used

        # ... (rest of SELECT item processing logic remains the same) ...
        # ... (Ensure proper qualification based on len(from_tables) > 1) ...
        if item_type == 'column':
             safe_column = sanitize_identifier(column)
             if not safe_column: return jsonify({"error": f"Missing or invalid column name: {item}"}), 400
             qualify = len(from_tables) > 1
             select_clause_items.append(f"`{table}`.`{safe_column}`" if qualify else f"`{safe_column}`")
        elif item_type == 'aggregate':
             # ... (aggregate logic remains same) ...
             func = str(item.get('func', '')).upper()
             alias = sanitize_identifier(item.get('alias'))
             if func not in ALLOWED_AGGREGATES: return jsonify({"error": f"Invalid aggregate func: {func}"}), 400
             if not column: return jsonify({"error": f"Missing column for aggregate {func}"}), 400
             target_col = f"`{sanitize_identifier(column)}`" if column != '*' else '*'
             if column == '*' and func != 'COUNT': return jsonify({"error": f"'*' only allowed with COUNT"}), 400
             if column != '*' and not sanitize_identifier(column): return jsonify({"error": f"Invalid col name for aggregate {func}: {column}"}), 400
             qualify = len(from_tables) > 1
             agg_target = f"`{table}`.{target_col}" if qualify and column != '*' else target_col
             agg_str = f"{func}({agg_target})"
             if alias: agg_str += f" AS `{alias}`"
             select_clause_items.append(agg_str)
        else:
             return jsonify({"error": f"Unknown select item type: {item_type}"}), 400


    sql_parts.append(f"SELECT {', '.join(select_clause_items)}")

    # --- 2. Build FROM and JOIN Clauses ---
    first_table = sanitize_identifier(from_tables[0])
    if not first_table: return jsonify({"error": "Invalid first table name"}), 400
    sql_parts.append(f"FROM `{first_table}`")

    tables_in_query = {first_table} # Tables accessible via FROM or JOIN

    # Add JOIN clauses
    joined_tables = set() # Keep track to ensure joins connect necessary tables
    for join in join_conditions:
        join_type = str(join.get('type', 'INNER')).upper()
        left_table = sanitize_identifier(join.get('leftTable'))
        left_col = sanitize_identifier(join.get('leftCol'))
        right_table = sanitize_identifier(join.get('rightTable'))
        right_col = sanitize_identifier(join.get('rightCol'))

        if join_type not in ALLOWED_JOIN_TYPES: return jsonify({"error": f"Invalid join type: {join_type}"}), 400
        if not (left_table and left_col and right_table and right_col): return jsonify({"error": f"Incomplete join definition: {join}"}), 400

        # Ensure joined tables are actually selected tables
        if left_table not in from_tables or right_table not in from_tables:
             return jsonify({"error": f"JOIN involves table(s) not selected in the 'FROM' list: {left_table}, {right_table}"}), 400

        # Add the JOIN clause - assumes right_table is being joined TO the existing query structure
        sql_parts.append(f"{join_type} JOIN `{right_table}` ON `{left_table}`.`{left_col}` = `{right_table}`.`{right_col}`")
        tables_in_query.add(right_table) # Mark table as accessible
        joined_tables.add(left_table)
        joined_tables.add(right_table)

    # --- *** Validation: Check if all selected tables are connected by FROM/JOIN *** ---
    if len(from_tables) > 1:
        unjoined_tables = set(from_tables) - tables_in_query
        if unjoined_tables:
             return jsonify({"error": f"Table(s) '{', '.join(unjoined_tables)}' selected but not included in any JOIN condition."}), 400
    # --- *** END Validation *** ---

    # --- *** Validation: Check if SELECT uses tables not in FROM/JOIN *** ---
    select_tables_not_in_query = tables_in_select - tables_in_query
    if select_tables_not_in_query:
        return jsonify({"error": f"SELECT list uses columns from table(s) '{', '.join(select_tables_not_in_query)}' which are not in FROM or JOIN clauses."}), 400
    # --- *** END Validation *** ---


    # --- 3. Build WHERE Clause ---
    # ... (Keep WHERE clause logic the same) ...
    # ... (Ensure tables used in WHERE are in tables_in_query) ...
    if where_conditions:
        try:
            where_clause_sql, where_params = build_where_clause(where_conditions)
            if where_clause_sql: # Only add WHERE if the helper returned a clause
                sql_parts.append(f"WHERE {where_clause_sql}")
                params.extend(where_params) # Use extend for list concatenation
        except ValueError as ve:
             return jsonify({"error": f"Invalid WHERE clause: {ve}"}), 400


    # --- 4. Build GROUP BY Clause ---
    # ... (Keep GROUP BY clause logic the same) ...
    # ... (Ensure tables used in GROUP BY are in tables_in_query) ...
    if group_by_columns:
        # ... (validation logic for aggregates/group by columns remains the same) ...
        group_by_clause_items = []
        allowed_group_by_cols = { f"{sanitize_identifier(p.get('table'))}.{sanitize_identifier(p.get('column'))}" for p in select_parts if p.get('type') == 'column'}
        for col_ref in group_by_columns:
             parts = col_ref.split('.', 1); table = sanitize_identifier(parts[0]); column = sanitize_identifier(parts[1])
             safe_qualified_col = f"`{table}`.`{column}`"; internal_ref = f"{table}.{column}"
             if not (table and column): return jsonify({"error": f"Invalid GROUP BY format: {col_ref}"}), 400
             if table not in tables_in_query: return jsonify({"error": f"GROUP BY col '{col_ref}' uses table not in query"}), 400
             if internal_ref not in allowed_group_by_cols and has_aggregates: # Check only needed if aggregates present
                  return jsonify({"error": f"GROUP BY column '{col_ref}' must be in non-aggregated SELECT list"}), 400
             group_by_clause_items.append(safe_qualified_col)
        if group_by_clause_items: sql_parts.append(f"GROUP BY {', '.join(group_by_clause_items)}")
        # ... (validation for aggregates without group by columns remains same) ...


    # --- Combine and Execute ---
    final_sql = "\n".join(sql_parts) + ";"
    print(f"--- Generated SQL ---")
    print(final_sql)
    print(f"Parameters: {params}")
    print(f"---------------------")

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn or not conn.is_connected(): return jsonify({"error": "Database connection failed"}), 500
        cursor = conn.cursor()
        cursor.execute(final_sql, params)
        results_tuples = cursor.fetchall()
        column_names = cursor.column_names
        print(f"Query executed successfully. Columns: {column_names}, Rows fetched: {len(results_tuples)}")
        return jsonify({"columns": column_names, "rows": results_tuples}), 200

    except Error as e:
        print(f"Database Error executing query: {e}")
        print(f"SQL attempted: {final_sql}")
        print(f"Params: {params}")

        # --- FIX: Assign default error_msg first ---
        error_msg = f"Database error: {e.msg}" if hasattr(e, 'msg') else f"Database error: {e}"
        # --- Map common errors ---
        if hasattr(e, 'errno'):
             if e.errno == 1054: error_msg = f"Database error: Unknown column specified. Check spelling/tables. (Details: {e.msg})"
             elif e.errno == 1146: error_msg = f"Database error: Table does not exist. (Details: {e.msg})"
             elif e.errno == 1064: error_msg = f"Database error: Syntax error in SQL. Check query builder logic. (Details: {e.msg})"
             # Add more specific error mappings if needed
        # --- END FIX ---

        return jsonify({"error": error_msg, "sql_attempted": final_sql}), 500 # Return SQL only in debug/dev?
    except Exception as ex:
         print(f"Unexpected Error executing query: {ex}")
         return jsonify({"error": f"An unexpected server error occurred: {ex}"}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


@app.route('/api/execute_dml', methods=['POST'])
def execute_dml_statement():
    """
    Executes INSERT (multi-row), UPDATE, or DELETE statements based on frontend request.
    Uses parameterized queries for values.
    Generates WHERE clause dynamically for UPDATE/DELETE.
    """
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    payload = request.get_json()
    if not payload:
        return jsonify({"error": "No JSON data received"}), 400

    print(f"Received DML payload: {payload}") # Debug log

    operation = str(payload.get('operation', '')).upper()
    table_name = sanitize_identifier(payload.get('table'))
    values_data = payload.get('values') # For INSERT [{col: val}, ...]
    set_data = payload.get('set', {})       # For UPDATE SET {col: val, ...}
    where_conditions = payload.get('where', []) # For UPDATE/DELETE WHERE [{col, op, val}, ...]

    if not table_name:
        return jsonify({"error": "Missing table name"}), 400

    conn = None
    cursor = None
    sql = ""
    params = [] # Use a single list for execute, or list of lists/tuples for executemany

    try:
        conn = get_db_connection()
        if not conn or not conn.is_connected():
            return jsonify({"error": "Database connection failed"}), 500
        cursor = conn.cursor()

        # -- Where clause --

        # -- End Where clause --


        # --- Generate SQL based on operation ---

        if operation == 'INSERT':
            if not values_data or not isinstance(values_data, list) or len(values_data) == 0:
                return jsonify({"error": "Missing or invalid 'values' list for INSERT operation"}), 400

            # Assume all dicts in list have the same keys, use first row to get columns
            first_row = values_data[0]
            columns = [sanitize_identifier(col) for col in first_row.keys()]
            if not all(columns):
                 return jsonify({"error": "Invalid column name(s) provided for INSERT"}), 400

            # Create placeholders for a single row
            placeholders = ['%s'] * len(columns)
            sql = f"INSERT INTO `{table_name}` ({', '.join([f'`{col}`' for col in columns])}) VALUES ({', '.join(placeholders)});"

            # Prepare params as a list of tuples/lists for executemany
            params_list_of_tuples = []
            for row_dict in values_data:
                row_values = []
                for col in columns: # Iterate in the determined column order
                    row_values.append(row_dict.get(col)) # Use .get() for safety, defaults to None if missing
                params_list_of_tuples.append(tuple(row_values)) # executemany expects list of tuples

            params = params_list_of_tuples # Assign for logging/executemany

        elif operation == 'UPDATE':
            if not set_data: return jsonify({"error": "Missing SET data for UPDATE"}), 400
            # --- Use updated build_where_clause ---
            if not where_conditions: return jsonify({"error": "Missing WHERE conditions for UPDATE"}), 400
            try:
                where_clause_sql, where_params = build_where_clause(where_conditions)
                 # Check if helper returned an empty clause (might happen if conditions were invalid)
                if not where_clause_sql: raise ValueError("Valid WHERE conditions are required for UPDATE.")
            except ValueError as ve:
                 return jsonify({"error": f"Invalid WHERE clause: {ve}"}), 400

            set_clauses = []; set_values = []
            for col, val in set_data.items():
                safe_col = sanitize_identifier(col);
                if not safe_col: return jsonify({"error": f"Invalid column name in SET: {col}"}), 400
                set_clauses.append(f"`{safe_col}` = %s"); set_values.append(val)

            sql = f"UPDATE `{table_name}` SET {', '.join(set_clauses)} WHERE {where_clause_sql};"
            params = set_values + where_params # Combine params

        elif operation == 'DELETE':
            if not where_conditions: return jsonify({"error": "Missing WHERE conditions for DELETE"}), 400
            try:
                where_clause_sql, where_params = build_where_clause(where_conditions)
                if not where_clause_sql: raise ValueError("Valid WHERE conditions are required for DELETE.")
            except ValueError as ve:
                 return jsonify({"error": f"Invalid WHERE clause: {ve}"}), 400

            sql = f"DELETE FROM `{table_name}` WHERE {where_clause_sql};"
            params = where_params
        else:
            return jsonify({"error": f"Unsupported DML operation: {operation}"}), 400

        # --- Execute SQL ---
        print(f"--- Generated DML ---")
        print(sql)
        print(f"Parameters: {params}") # For INSERT, this now prints a list of tuples
        print(f"---------------------")

        if operation == 'INSERT':
            cursor.executemany(sql, params)
        else: # UPDATE or DELETE
            cursor.execute(sql, params)

        conn.commit() # Commit changes for DML statements

        affected_rows = cursor.rowcount
        message = f"{operation} successful. Rows affected: {affected_rows}"
        if (operation == 'UPDATE' or operation == 'DELETE') and affected_rows == 0:
             message = f"{operation} executed, but no rows matched the WHERE condition(s)."

        print(message)
        return jsonify({"message": message, "affectedRows": affected_rows}), 200

    except Error as e:
        if conn: conn.rollback() # Rollback on error
        print(f"Database Error executing DML: {e}")
        print(f"SQL attempted: {sql}")
        print(f"Params: {params}")
        # Specific error check (e.g., duplicate entry)
        # if e.errno == errorcode.ER_DUP_ENTRY:
        #     error_msg = f"Database error: Duplicate entry detected. {e.msg}"
        # else:
        error_msg = f"Database error: {e.msg}" if hasattr(e, 'msg') else f"Database error: {e}"
        return jsonify({"error": error_msg, "sql_attempted": sql}), 500
    except ValueError as ve: # Catch errors from build_where_clause
         if conn: conn.rollback()
         print(f"Validation Error building WHERE clause: {ve}")
         return jsonify({"error": f"Invalid WHERE condition: {ve}"}), 400
    except Exception as ex:
         if conn: conn.rollback()
         print(f"Unexpected Error executing DML: {ex}")
         return jsonify({"error": f"An unexpected server error occurred: {ex}"}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected():
            conn.close()
            print("MySQL connection closed after DML execution")

def get_table_schema_details(table_name):
    """ Helper to fetch columns and designated primary key. """
    safe_table_name = sanitize_identifier(table_name)
    if not safe_table_name:
        raise ValueError("Invalid table name provided")

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn or not conn.is_connected():
            raise ConnectionError("Database connection failed")

        cursor = conn.cursor(dictionary=True)

        # Get Columns (similar to get_table_details endpoint)
        cursor.execute(f"DESCRIBE `{safe_table_name}`;")
        cols_raw = cursor.fetchall()
        if not cols_raw:
             raise ValueError(f"Table '{safe_table_name}' not found or has no columns.")

        attributes_info = {}
        all_attributes = set()
        pk_columns = set()
        for col in cols_raw:
            col_name = col.get('Field')
            if not col_name: continue
            safe_col_name = sanitize_identifier(col_name) # Should match schema name
            all_attributes.add(safe_col_name)
            attributes_info[safe_col_name] = {
                "name": safe_col_name,
                "type": col.get('Type', ''),
                "isPK": col.get('Key') == 'PRI'
                # Add other info if needed
            }
            if col.get('Key') == 'PRI':
                pk_columns.add(safe_col_name)

        if not pk_columns:
            # Handle tables without a designated PK? For normalization, PK is usually essential.
            print(f"Warning: Table '{safe_table_name}' has no designated Primary Key.")
            # raise ValueError(f"Table '{safe_table_name}' must have a Primary Key for normalization analysis.")


        return list(all_attributes), list(pk_columns), attributes_info

    except Error as e:
        raise ConnectionError(f"Database error fetching schema for {safe_table_name}: {e}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

def calculate_closure(attributes_to_close, fds_dict, all_attributes):
    """ Calculates the attribute closure (X+) using basic iterative approach. """
    closure = set(attributes_to_close)
    changed = True
    while changed:
        changed = False
        for determinant_tuple, dependents in fds_dict.items():
            determinant_set = set(determinant_tuple)
            # If determinant is subset of current closure AND
            # there are dependents not yet in closure
            if determinant_set.issubset(closure) and not dependents.issubset(closure):
                new_attributes = dependents - closure
                if new_attributes:
                    closure.update(new_attributes)
                    changed = True
    return closure

def find_candidate_keys(attributes, fds_dict):
     """ Basic algorithm to find candidate keys (can be computationally expensive). """
     all_attributes_set = set(attributes)
     candidate_keys = []

     # Generate power set of attributes (potential keys)
     # Start from smaller sets first
     for k in range(1, len(attributes) + 1):
         possible_keys = combinations(attributes, k)
         found_superkey_at_this_level = False

         for key_tuple in possible_keys:
             key_set = set(key_tuple)
             closure = calculate_closure(key_set, fds_dict, all_attributes_set)

             # Check if it's a superkey
             if closure == all_attributes_set:
                 found_superkey_at_this_level = True
                 # Check if it's minimal (no proper subset is also a superkey)
                 is_minimal = True
                 for ck in candidate_keys:
                     # If an existing CK is a subset of this new key, it's not minimal
                     if set(ck).issubset(key_set):
                         is_minimal = False
                         break
                 if is_minimal:
                     # Remove any existing superkeys that contain this new minimal key
                     candidate_keys = [ck for ck in candidate_keys if not key_set.issubset(set(ck))]
                     candidate_keys.append(key_tuple) # Add the new minimal key

         # Optimization: If we found superkeys at level k, no need to check level k+1 subsets of those
         # (More complex optimization: Pruning based on non-prime attributes)
         if found_superkey_at_this_level and candidate_keys:
              pass # Continue checking larger sets that might be minimal due to different combinations

     # Return sorted list of tuples for consistency
     return sorted([tuple(sorted(ck)) for ck in candidate_keys])




# --- Helper Functions (New or Modified) ---

def get_minimal_cover(fds_dict):
    """
    Calculates a minimal cover for the given set of FDs.
    Corrected version for Step 3 (Redundancy Check).
    fds_dict: { frozenset(determinants): set(dependents) } original FDs
    Returns: { frozenset(determinants): set(dependents) } minimal cover
    """
    # --- Step 0: Get all attributes involved ---
    all_attributes = set(chain.from_iterable(fds_dict.keys())) | set(chain.from_iterable(fds_dict.values()))
    if not all_attributes:
        return {} # Handle empty case

    # --- Step 1: Standard Form (Singleton Right-Hand Side) ---
    # This creates a dict like { frozenset(det): set(dep1, dep2), ... } from the input
    # We actually need a list of pairs (frozenset(det), dep) for step 3
    standard_fds_list = []
    standard_fds_dict_temp = {} # Temporary dict to build sets
    for det, deps in fds_dict.items():
        for dep in deps:
             # Ensure dependent is not already in determinant (trivial)
            if dep not in det:
                standard_fds_list.append((det, dep))
                # Also build a temporary dict representation for Step 2 closure check
                if det not in standard_fds_dict_temp:
                     standard_fds_dict_temp[det] = set()
                standard_fds_dict_temp[det].add(dep)


    current_fds_list = deepcopy(standard_fds_list) # Work with the list of pairs

    # --- Step 2: Minimize Left-Hand Side (Remove extraneous attributes) ---
    minimized_lhs_list = []
    for det_fset, dep in current_fds_list:
        minimized_det = set(det_fset) # Start with the full determinant
        if len(minimized_det) > 1: # Only minimize if determinant has > 1 attribute
            for attr in list(det_fset): # Iterate over original determinant attributes
                # Only try removing if still > 1 attribute left
                if len(minimized_det) > 1:
                    temp_det = minimized_det - {attr}
                    # Calculate closure of reduced determinant using ORIGINAL standard FDs dict
                    # Pass the standard_fds_dict_temp for correct closure context in this step
                    closure = calculate_closure(temp_det, standard_fds_dict_temp, all_attributes)

                    # If the single dependent is still in the closure, the attribute was extraneous FOR THIS FD
                    if dep in closure:
                        minimized_det = temp_det # Keep the reduced determinant
                        print(f"DEBUG: Minimized LHS: Removed '{attr}' from {det_fset} -> {dep}. New det: {minimized_det}")

        # Add the FD with the potentially minimized determinant to the new list
        minimized_lhs_list.append((frozenset(minimized_det), dep))

    current_fds_list = minimized_lhs_list

    # --- Step 3: Remove Redundant FDs (Corrected Logic) ---
    # We need to iterate through the list and build the final cover incrementally
    final_min_cover_list = []
    # Create the dictionary form needed by calculate_closure from the current list
    current_fds_dict = {}
    for det_fset, dep in current_fds_list:
         if det_fset not in current_fds_dict: current_fds_dict[det_fset] = set()
         current_fds_dict[det_fset].add(dep)

    # Check each FD from the minimized list
    for det_fset, dep in current_fds_list:
        # Temporarily remove the current FD (det_fset -> dep)
        temp_cover_dict = {}
        for d, dp_set in current_fds_dict.items():
             temp_cover_dict[d] = set(dp_set) # Deep copy the set

        if det_fset in temp_cover_dict:
            if dep in temp_cover_dict[det_fset]:
                temp_cover_dict[det_fset].remove(dep)
                if not temp_cover_dict[det_fset]: # Remove determinant if no dependents left
                    del temp_cover_dict[det_fset]

        # Check if the single dependent 'dep' can still be derived from the remaining FDs
        closure = calculate_closure(det_fset, temp_cover_dict, all_attributes)

        # If 'dep' is NOT in the closure, then the FD is essential and kept
        if dep not in closure:
            final_min_cover_list.append((det_fset, dep))
        else:
            print(f"DEBUG: Removed redundant FD: {det_fset} -> {dep}")


    # --- Convert final list back to dictionary format ---
    final_min_cover_dict = {}
    for det_fset, dep in final_min_cover_list:
        if det_fset not in final_min_cover_dict:
            final_min_cover_dict[det_fset] = set()
        final_min_cover_dict[det_fset].add(dep)

    print(f"DEBUG: Final Minimal Cover Dict: {final_min_cover_dict}")
    return final_min_cover_dict

def check_fd_preservation(original_fds_dict, decomposed_schemas):
    """
    Checks which FDs from the original set are preserved in the decomposition.
    An FD X -> Y is preserved if all attributes in X U Y exist in at least one of the decomposed schemas.
    original_fds_dict: { frozenset(determinants): set(dependents) }
    decomposed_schemas: List of sets, where each set contains the attributes of a decomposed table.
    Returns: List of lost FDs (as strings for display)
    """
    lost_fds = []
    for det_fset, deps_set in original_fds_dict.items():
        is_preserved = False
        fd_attributes = det_fset.union(deps_set)
        for schema_set in decomposed_schemas:
            if fd_attributes.issubset(schema_set):
                is_preserved = True
                break
        if not is_preserved:
            lost_fds.append(f"{{{', '.join(sorted(det_fset))}}} -> {{{', '.join(sorted(deps_set))}}}")
    return lost_fds

def generate_create_table_sql(table_name, attributes_set, pk_set, attributes_info):
    """ Generates CREATE TABLE SQL for a decomposed table. """
    safe_table_name = sanitize_identifier(table_name)
    column_definitions = []
    primary_keys = []

    for attr in sorted(list(attributes_set)): # Ensure consistent column order
        if attr not in attributes_info:
            # Fallback if type info missing (shouldn't happen ideally)
            print(f"Warning: No type info found for attribute '{attr}' in table '{safe_table_name}'. Defaulting to TEXT.")
            col_type = 'TEXT'
            is_pk_attr = attr in pk_set
        else:
            col_info = attributes_info[attr]
            # Attempt to map type, default if necessary
            raw_type = col_info.get('type', '').upper()
            col_type = next((mapped for key, mapped in MYSQL_TYPE_MAP.items() if key in raw_type), 'TEXT')
            is_pk_attr = col_info.get('isPK', False) or attr in pk_set # Check info OR if it's part of the derived PK

        # Basic definition: name and type
        col_def_parts = [f"`{sanitize_identifier(attr)}`", col_type]

        # Add NOT NULL if it's part of the derived primary key for this table
        # (More complex logic could preserve original NULL/NOT NULL status if needed)
        if attr in pk_set:
            col_def_parts.append("NOT NULL")
            primary_keys.append(f"`{sanitize_identifier(attr)}`")

        column_definitions.append(" ".join(col_def_parts))

    if not column_definitions:
        raise ValueError(f"Cannot create table '{safe_table_name}' with no columns.")
    # Ensure the table has a primary key defined using the attributes identified as the key for this sub-schema
    if not primary_keys and pk_set:
         # This might happen if pk_set attributes weren't in attributes_set for some reason? Error check.
         raise ValueError(f"Primary key columns {pk_set} not found in attributes {attributes_set} for table {safe_table_name}")
    if not primary_keys and not pk_set:
         raise ValueError(f"Cannot create table '{safe_table_name}' without a primary key.")


    sql = f"CREATE TABLE `{safe_table_name}` (\n"
    sql += ",\n".join(f"    {col_def}" for col_def in column_definitions)
    if primary_keys:
        sql += f",\n    PRIMARY KEY ({', '.join(primary_keys)})"
    sql += "\n);"
    return sql

def generate_data_migration_sql(original_table_name, new_table_name, attributes_set):
    """ Generates INSERT INTO ... SELECT DISTINCT ... SQL """
    safe_original_name = sanitize_identifier(original_table_name)
    safe_new_name = sanitize_identifier(new_table_name)
    safe_columns = [f"`{sanitize_identifier(attr)}`" for attr in sorted(list(attributes_set))] # Consistent order
    cols_str = ", ".join(safe_columns)

    if not cols_str:
         raise ValueError(f"No columns specified for data migration to {safe_new_name}")

    sql = f"INSERT INTO `{safe_new_name}` ({cols_str})\n"
    sql += f"SELECT DISTINCT {cols_str}\n"
    sql += f"FROM `{safe_original_name}`;"
    return sql


# --- Endpoint Modifications (/api/analyze_normalization) ---

@app.route('/api/analyze_normalization', methods=['POST'])
def analyze_normalization():
    if not request.is_json: return jsonify({"error": "Request must be JSON"}), 400
    payload = request.get_json()
    if not payload: return jsonify({"error": "No JSON data received"}), 400

    table_name = payload.get('table')
    user_fds_raw = payload.get('fds', []) # Expecting list like [{determinants: [col], dependents: [col]}, ...]

    if not table_name: return jsonify({"error": "Missing table name"}), 400

    results = {
        "tableName": table_name,
        "primaryKey": [],
        "candidateKeys": [],
        "attributes": [], # ADDED: List all attributes
        "processedFds": {}, # ADDED: Store processed FDs for decomposition use {det: [deps]}
        "analysis": {
            "1NF": {"status": "ASSUMED_COMPLIANT", "message": "Relational databases generally enforce atomicity.", "violations": []},
            "2NF": {"status": "NOT_CHECKED", "message": "Requires PK and FDs.", "violations": []},
            "3NF": {"status": "NOT_CHECKED", "message": "Requires PK and FDs.", "violations": []},
            "BCNF": {"status": "NOT_CHECKED", "message": "Requires Candidate Keys and FDs.", "violations": []}
        },
        "notes": [],
        "error": None
    }

    try:
        # 1. Get Schema Details
        all_attributes_list, pk_columns_list, attributes_info = get_table_schema_details(table_name)
        all_attributes = set(all_attributes_list)
        pk_set = frozenset(pk_columns_list) # Use frozenset for dict keys
        results["primaryKey"] = sorted(pk_columns_list)
        results["attributes"] = sorted(all_attributes_list) # Store all attributes

        if not pk_set:
            results["error"] = "Designated Primary Key is required for standard normalization analysis."
            return jsonify(results), 400

        # 2. Process Functional Dependencies
        processed_fds = {} # { frozenset(determinants): set(dependents) }
        non_pk_attributes = all_attributes - pk_set
        if pk_set and non_pk_attributes:
             processed_fds[pk_set] = non_pk_attributes

        for fd in user_fds_raw:
            determinants_raw = fd.get('determinants', [])
            dependents_raw = fd.get('dependents', [])
            if not determinants_raw or not dependents_raw: raise ValueError(f"Invalid FD format: {fd}")
            determinants = frozenset(sanitize_identifier(d) for d in determinants_raw)
            dependents = set(sanitize_identifier(dep) for dep in dependents_raw)
            if not determinants.issubset(all_attributes): raise ValueError(f"Determinant(s) not in table: {determinants - all_attributes}")
            if not dependents.issubset(all_attributes): raise ValueError(f"Dependent(s) not in table: {dependents - all_attributes}")
            if not dependents.isdisjoint(determinants): raise ValueError(f"FD cannot have same attribute on both sides: {fd}")
            if determinants in processed_fds: processed_fds[determinants].update(dependents)
            else: processed_fds[determinants] = dependents

        # Store processed FDs in results for later use (convert sets back to lists for JSON)
        results["processedFds"] = {",".join(sorted(list(det))): sorted(list(deps)) for det, deps in processed_fds.items()}

        # 3. Find Candidate Keys
        print("Finding candidate keys...") # Debug
        candidate_keys_tuples = find_candidate_keys(all_attributes_list, processed_fds)
        candidate_keys_sets = [frozenset(ck) for ck in candidate_keys_tuples]
        results["candidateKeys"] = [sorted(list(ck)) for ck in candidate_keys_sets]
        print(f"Found Candidate Keys: {results['candidateKeys']}") # Debug
        if not candidate_keys_sets: raise ValueError("Could not determine any Candidate Keys.")

        prime_attributes = set(chain.from_iterable(candidate_keys_sets))
        non_prime_attributes = all_attributes - prime_attributes

        # 4. Perform Normalization Checks (Logic remains the same as before)
        # ... [1NF check - assumed] ...
        # ... [2NF check logic] ...
        # ... [3NF check logic] ...
        # ... [BCNF check logic] ...
        # (Copy the existing checking logic here)

        # --- 1NF --- (Remains basic assumption)
        results["analysis"]["1NF"]["message"] = "Assumed compliant (atomic values enforced by RDBMS)."

        # --- 2NF --- (No partial dependencies)
        is_2nf = True
        results["analysis"]["2NF"]["status"] = "COMPLIANT"
        results["analysis"]["2NF"]["message"] = "No partial dependencies found."
        for ck_set in candidate_keys_sets:
            if len(ck_set) > 1:
                for k in range(1, len(ck_set)):
                    subsets = combinations(ck_set, k)
                    for subset_tuple in subsets:
                        subset_set = frozenset(subset_tuple)
                        subset_closure = calculate_closure(subset_set, processed_fds, all_attributes)
                        partially_determined_non_primes = subset_closure.intersection(non_prime_attributes)
                        if partially_determined_non_primes:
                             is_2nf = False
                             violation_str = f"Partial Dependency: {{{', '.join(sorted(subset_set))}}} -> {{{', '.join(sorted(partially_determined_non_primes))}}} (violates dependency on CK {{{', '.join(sorted(ck_set))}}})"
                             if violation_str not in results["analysis"]["2NF"]["violations"]:
                                 results["analysis"]["2NF"]["violations"].append(violation_str)
        if not is_2nf:
             results["analysis"]["2NF"]["status"] = "VIOLATION_DETECTED"
             results["analysis"]["2NF"]["message"] = "Partial dependencies found (non-prime attributes depend on only part of a candidate key)."

        # --- 3NF --- (No transitive dependencies)
        is_3nf = True
        results["analysis"]["3NF"]["status"] = "COMPLIANT"
        results["analysis"]["3NF"]["message"] = "No transitive dependencies found."
        for determinant_set, dependents_set in processed_fds.items():
             determinant_closure = calculate_closure(determinant_set, processed_fds, all_attributes)
             is_superkey = (determinant_closure == all_attributes)
             if not is_superkey:
                 for dependent in dependents_set:
                     if dependent not in determinant_set:
                        is_prime = (dependent in prime_attributes)
                        if not is_prime:
                             is_3nf = False
                             violation_str = f"Transitive Dependency: {{{', '.join(sorted(determinant_set))}}} -> {{{dependent}}} (Determinant is not superkey, Dependent is not prime)"
                             if violation_str not in results["analysis"]["3NF"]["violations"]:
                                 results["analysis"]["3NF"]["violations"].append(violation_str)
        if not is_3nf:
            results["analysis"]["3NF"]["status"] = "VIOLATION_DETECTED"
            results["analysis"]["3NF"]["message"] = "Transitive dependencies found (non-prime attributes depend on other non-prime attributes)."

        # --- BCNF --- (Every determinant must be a superkey)
        is_bcnf = True
        results["analysis"]["BCNF"]["status"] = "COMPLIANT"
        results["analysis"]["BCNF"]["message"] = "All determinants are superkeys."
        for determinant_set, dependents_set in processed_fds.items():
            if not dependents_set.issubset(determinant_set):
                determinant_closure = calculate_closure(determinant_set, processed_fds, all_attributes)
                is_superkey = (determinant_closure == all_attributes)
                if not is_superkey:
                    is_bcnf = False
                    dependent_part = dependents_set - determinant_set
                    violation_str = f"BCNF Violation: Determinant {{{', '.join(sorted(determinant_set))}}} is not a superkey (determines {{{', '.join(sorted(dependent_part))}}})"
                    if violation_str not in results["analysis"]["BCNF"]["violations"]:
                        results["analysis"]["BCNF"]["violations"].append(violation_str)
        if not is_bcnf:
            results["analysis"]["BCNF"]["status"] = "VIOLATION_DETECTED"
            results["analysis"]["BCNF"]["message"] = "BCNF violation(s) found (determinant of an FD is not a superkey)."
        if not is_3nf and is_bcnf: pass


        results["notes"].append("Analysis based on schema, designated PK, and user-provided FDs.")
        if not results["candidateKeys"] or len(results["candidateKeys"]) <= 1:
             results["notes"].append("Full accuracy requires identifying ALL candidate keys. Ensure all relevant FDs were provided.")

        return jsonify(results), 200

    except (ConnectionError, ValueError, Error) as e: # Catch specific errors
        print(f"Error during normalization analysis for table '{table_name}': {e}")
        results["error"] = str(e)
        return jsonify(results), 400 # Return 400 for client/schema errors
    except Exception as ex:
         print(f"Unexpected Error during normalization analysis: {ex}")
         results["error"] = f"An unexpected server error occurred: {ex}"
         return jsonify(results), 500


# --- NEW Decomposition Endpoints ---

@app.route('/api/decompose/3nf', methods=['POST'])
def decompose_3nf():
    """
    Performs 3NF decomposition based on provided schema info and FDs.
    Uses the Synthesis Algorithm.
    """
    if not request.is_json: return jsonify({"error": "Request must be JSON"}), 400
    payload = request.get_json()
    if not payload: return jsonify({"error": "No JSON data received"}), 400

    table_name = payload.get('tableName')
    attributes_list = payload.get('attributes', []) # All attributes from original table
    candidate_keys_list = payload.get('candidateKeys', []) # List of lists
    processed_fds_str_keys = payload.get('processedFds', {}) # { "det1,det2": [dep1], ... }

    if not table_name or not attributes_list or not candidate_keys_list or not processed_fds_str_keys:
        return jsonify({"error": "Missing required data: tableName, attributes, candidateKeys, processedFds"}), 400

    # Convert processedFds back to { frozenset: set }
    processed_fds = {}
    for det_str, deps_list in processed_fds_str_keys.items():
        det_fset = frozenset(det_str.split(','))
        deps_set = set(deps_list)
        processed_fds[det_fset] = deps_set

    candidate_keys_sets = [frozenset(ck) for ck in candidate_keys_list]
    all_attributes = set(attributes_list)

    decomposed_schemas = [] # List of sets (attributes for each new table)
    lost_fds_display = [] # 3NF should preserve FDs

    try:
        # 1. Find Minimal Cover
        min_cover = get_minimal_cover(processed_fds)
        print(f"DEBUG: Minimal Cover for 3NF: {min_cover}")

        # 2. Create Tables for each FD in Minimal Cover
        # Each table schema is {Determinant U Dependent}
        for det_fset, deps_set in min_cover.items():
            schema_set = det_fset.union(deps_set)
            decomposed_schemas.append(schema_set)

        # 3. Ensure a Candidate Key is present
        # Check if any decomposed schema contains a candidate key of the original table
        ck_found = False
        for schema_set in decomposed_schemas:
            for ck_set in candidate_keys_sets:
                if ck_set.issubset(schema_set):
                    ck_found = True
                    break
            if ck_found: break

        # If no candidate key found, add a table containing one candidate key
        if not ck_found and candidate_keys_sets:
            # Add the first candidate key found (or potentially a preferred one if logic existed)
            ck_to_add = candidate_keys_sets[0]
            # Check if this schema is already fully contained in an existing one
            already_covered = any(ck_to_add.issubset(existing_schema) for existing_schema in decomposed_schemas)
            if not already_covered:
                print(f"DEBUG: Adding Candidate Key table for 3NF: {ck_to_add}")
                decomposed_schemas.append(ck_to_add)


        # 4. Combine/Minimize schemas (Optional but good practice)
        # Remove schemas that are subsets of others
        minimal_schemas = []
        for s1 in decomposed_schemas:
            is_subset = False
            for s2 in decomposed_schemas:
                if s1 != s2 and s1.issubset(s2):
                    is_subset = True
                    break
            if not is_subset:
                 # Check for duplicates before adding
                 if s1 not in minimal_schemas:
                     minimal_schemas.append(s1)
        decomposed_schemas = minimal_schemas


        # 5. Prepare response (Schema definitions only, no data migration yet)
        final_schemas_details = []
        for i, schema_set in enumerate(decomposed_schemas):
            new_table_name = f"{table_name}_3NF_{i+1}"
             # Determine PK for this sub-schema (usually the original determinant or a CK subset)
            schema_pk = set()
            # Best guess: Find the original determinant or CK that generated/covers this schema
            found_pk_basis = False
            for det_fset in min_cover.keys(): # Check minimal cover determinants first
                 if det_fset.issubset(schema_set):
                      schema_pk = det_fset
                      found_pk_basis = True
                      break
            if not found_pk_basis:
                 for ck_set in candidate_keys_sets: # Then check candidate keys
                     if ck_set.issubset(schema_set):
                         schema_pk = ck_set
                         break

            final_schemas_details.append({
                "new_table_name": new_table_name,
                "attributes": sorted(list(schema_set)),
                "primary_key": sorted(list(schema_pk)) # PK is the determinant or CK subset
            })

        return jsonify({
            "decomposition_type": "3NF",
            "original_table": table_name,
            "decomposed_tables": final_schemas_details,
            "lost_fds": [] # 3NF should be dependency preserving
        }), 200

    except Exception as e:
        print(f"Error during 3NF decomposition for {table_name}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to decompose to 3NF: {e}"}), 500


@app.route('/api/decompose/bcnf', methods=['POST'])
def decompose_bcnf():
    """
    Performs BCNF decomposition based on provided schema info and FDs.
    Uses the Analysis Algorithm. This may not preserve all dependencies.
    Corrected PK determination logic.
    """
    if not request.is_json: return jsonify({"error": "Request must be JSON"}), 400
    payload = request.get_json()
    if not payload: return jsonify({"error": "No JSON data received"}), 400

    table_name = payload.get('tableName')
    attributes_list = payload.get('attributes', [])
    # Use original FDs before minimal cover for decomposition check (as per most algorithms)
    # The 'processedFds' from analysis might be minimal cover or just includes PK->others.
    # Let's re-fetch schema to get original PK and re-build initial FDs for BCNF checks
    # Or, assume payload['processedFds'] contains ALL relevant FDs (original + user)
    processed_fds_str_keys = payload.get('processedFds', {}) # Assuming this has ALL needed FDs

    if not table_name or not attributes_list or not processed_fds_str_keys:
        return jsonify({"error": "Missing required data: tableName, attributes, processedFds"}), 400

    # Convert FDs back { frozenset: set }
    processed_fds = {}
    for det_str, deps_list in processed_fds_str_keys.items():
        det_fset = frozenset(det_str.split(','))
        deps_set = set(deps_list)
        # Basic validation: ensure attributes exist? Already done in analysis presumably.
        processed_fds[det_fset] = deps_set

    all_attributes = set(attributes_list)

    # Initial state: one table with all attributes
    decomposed_schemas = [all_attributes] # List of sets
    work_list = [all_attributes] # Schemas to check for violations

    # --- Main Decomposition Loop ---
    while work_list:
        current_schema_set = work_list.pop(0)
        print(f"DEBUG: Checking schema for BCNF: {current_schema_set}")
        violation_found_in_current = False

        # Find relevant FDs for the current sub-schema
        # An FD X->Y is relevant if X and Y are subsets of current_schema_set
        relevant_fds = {}
        for det_fset, deps_set in processed_fds.items():
            # Check if determinant is within current schema before proceeding
            if det_fset.issubset(current_schema_set):
                 # Keep only the dependents that are also *in* the current schema
                relevant_deps = deps_set.intersection(current_schema_set)
                # Ensure the FD is non-trivial *within this schema* (relevant_deps not subset of det_fset)
                if relevant_deps and not relevant_deps.issubset(det_fset):
                    relevant_fds[det_fset] = relevant_deps

        # Check each relevant FD for BCNF violation within this schema
        # Use a copy of keys to allow modification during iteration if needed, although break avoids it here
        for det_fset, rel_deps_set in list(relevant_fds.items()):
            # Calculate closure within the context of the *current schema* using *only relevant FDs*
            # This determines if det_fset is a superkey OF THE CURRENT SCHEMA
            closure_local = calculate_closure(det_fset, relevant_fds, current_schema_set)
            is_superkey_local = (closure_local == current_schema_set)

            if not is_superkey_local: # VIOLATION! det_fset is not a superkey of current_schema_set
                print(f"DEBUG: BCNF Violation in {current_schema_set}: {det_fset} -> {rel_deps_set}")
                violation_found_in_current = True

                # Decompose: R1 = X U Y, R2 = R - (Y - X)
                schema1 = det_fset.union(rel_deps_set)
                schema2 = (current_schema_set - rel_deps_set).union(det_fset)

                # Remove the violating schema, add the two new ones
                if current_schema_set in decomposed_schemas:
                    decomposed_schemas.remove(current_schema_set)

                # Add new schemas only if they aren't subsets of existing ones (basic check)
                # More robust check might be needed later
                is_s1_subset = any(schema1 != s and schema1.issubset(s) for s in decomposed_schemas)
                is_s2_subset = any(schema2 != s and schema2.issubset(s) for s in decomposed_schemas)

                if not is_s1_subset and schema1 not in decomposed_schemas:
                     decomposed_schemas.append(schema1)
                     if schema1 not in work_list: work_list.append(schema1)
                if not is_s2_subset and schema2 not in decomposed_schemas:
                     decomposed_schemas.append(schema2)
                     if schema2 not in work_list: work_list.append(schema2)


                # Stop checking current schema and restart loop with updated lists
                break # Exit inner FD loop for current_schema_set

        if violation_found_in_current:
            # Clean up work_list: remove schemas that are now subsets of newly added ones
            # This helps prevent redundant checks
            current_work_list = list(work_list) # Copy to iterate
            for w_schema in current_work_list:
                 is_subset_of_new = any(w_schema != d_schema and w_schema.issubset(d_schema) for d_schema in decomposed_schemas)
                 if is_subset_of_new and w_schema in work_list:
                      work_list.remove(w_schema)

            continue # Restart outer while loop to process next item in work_list


    # --- Post-processing ---
    # Minimize final schemas (remove subsets)
    minimal_schemas = []
    decomposed_schemas.sort(key=len) # Process smaller sets first
    for s1 in decomposed_schemas:
        is_subset = False
        for s2 in minimal_schemas: # Compare against already added minimal ones
            if s1 != s2 and s1.issubset(s2):
                is_subset = True
                break
        if not is_subset:
             # Also remove any existing minimal schemas that are SUPERSETS of s1
             minimal_schemas = [s for s in minimal_schemas if not s1.issubset(s)]
             minimal_schemas.append(s1) # Add the new minimal schema
    decomposed_schemas = minimal_schemas

    # Check for lost dependencies using original FDs
    lost_fds_display = check_fd_preservation(processed_fds, decomposed_schemas)

    # --- Prepare response - *** CORRECTED PK Logic *** ---
    final_schemas_details = []
    for i, schema_set in enumerate(decomposed_schemas):
        new_table_name = f"{table_name}_BCNF_{i+1}"
        current_attributes_list = sorted(list(schema_set))

        # 1. Project Original FDs onto the current schema_set
        projected_fds = {}
        for det_fset, deps_set in processed_fds.items():
            # Determinant must be subset of current schema
            if det_fset.issubset(schema_set):
                # Keep only dependents that are also in current schema
                relevant_deps = deps_set.intersection(schema_set)
                # Ensure it's non-trivial within this projection
                if relevant_deps and not relevant_deps.issubset(det_fset):
                    projected_fds[det_fset] = relevant_deps

        # 2. Find Candidate Keys for the current schema using projected FDs
        # Pass attributes as list and FDs as dict {frozenset: set}
        candidate_keys_tuples = find_candidate_keys(current_attributes_list, projected_fds)

        # 3. Select the Primary Key
        schema_pk = set()
        if candidate_keys_tuples:
            # Choose the smallest candidate key (or first if multiple smallest)
            schema_pk = set(min(candidate_keys_tuples, key=len))
            print(f"DEBUG: Found CKs for {new_table_name}: {candidate_keys_tuples}. Chosen PK: {schema_pk}")
        else:
            # Should not happen in BCNF if decomposition is correct, but handle defensively
            print(f"ERROR: Could not determine candidate keys for BCNF table {new_table_name} with attributes {schema_set} and projected FDs {projected_fds}. Defaulting PK to all attributes.")
            schema_pk = schema_set # Fallback ONLY if CK finding fails unexpectedly

        final_schemas_details.append({
            "new_table_name": new_table_name,
            "attributes": current_attributes_list,
            "primary_key": sorted(list(schema_pk)) # Assign the correctly determined PK
        })

    return jsonify({
        "decomposition_type": "BCNF",
        "original_table": table_name,
        "decomposed_tables": final_schemas_details,
        "lost_fds": lost_fds_display
    }), 200



@app.route('/api/save_decomposition', methods=['POST'])
def save_decomposition():
    """
    Applies the decomposition: creates new tables, migrates data, drops old table.
    Performs operations within a transaction.
    """
    if not request.is_json: return jsonify({"error": "Request must be JSON"}), 400
    payload = request.get_json()
    if not payload: return jsonify({"error": "No JSON data received"}), 400

    original_table_name = payload.get('original_table')
    decomposed_tables_info = payload.get('decomposed_tables') # List of {new_table_name, attributes, primary_key}

    if not original_table_name or not decomposed_tables_info:
        return jsonify({"error": "Missing original table name or decomposition details"}), 400

    # Get detailed attribute info (types) for the original table
    try:
        _, _, original_attributes_info = get_table_schema_details(original_table_name)
    except Exception as e:
         return jsonify({"error": f"Failed to get original table details: {e}"}), 500

    conn = None
    cursor = None
    created_tables = []
    migrated_tables = []
    sql_executed = []

    try:
        conn = get_db_connection()
        if not conn or not conn.is_connected():
            raise ConnectionError("Database connection failed")
        conn.start_transaction()
        cursor = conn.cursor()
        print(f"--- Starting Decomposition Save for {original_table_name} ---")

        # 1. Create New Tables
        for table_info in decomposed_tables_info:
            new_name = table_info['new_table_name']
            attrs = set(table_info['attributes'])
            pk = set(table_info['primary_key'])

            # Ensure PK attributes are actually in the table's attributes
            if not pk.issubset(attrs):
                 raise ValueError(f"Primary key {pk} for table {new_name} contains attributes not in its schema {attrs}")

            # Drop existing table if it exists (handle reruns)
            drop_sql = f"DROP TABLE IF EXISTS `{sanitize_identifier(new_name)}`;"
            print(f"Executing: {drop_sql}")
            cursor.execute(drop_sql)
            sql_executed.append(drop_sql)


            create_sql = generate_create_table_sql(new_name, attrs, pk, original_attributes_info)
            print(f"Executing: {create_sql}")
            cursor.execute(create_sql)
            created_tables.append(new_name)
            sql_executed.append(create_sql)

        # 2. Migrate Data
        for table_info in decomposed_tables_info:
            new_name = table_info['new_table_name']
            attrs = set(table_info['attributes'])
            migrate_sql = generate_data_migration_sql(original_table_name, new_name, attrs)
            print(f"Executing: {migrate_sql}")
            cursor.execute(migrate_sql)
            migrated_tables.append(new_name)
            sql_executed.append(migrate_sql)

        # 3. Drop Original Table
        drop_original_sql = f"DROP TABLE `{sanitize_identifier(original_table_name)}`;"
        print(f"Executing: {drop_original_sql}")
        cursor.execute(drop_original_sql)
        sql_executed.append(drop_original_sql)


        # 4. Commit Transaction
        conn.commit()
        print(f"--- Decomposition for {original_table_name} committed successfully ---")
        return jsonify({
            "message": f"Decomposition of '{original_table_name}' applied successfully.",
            "created_tables": created_tables,
            "data_migrated_to": migrated_tables,
            "original_table_dropped": True
        }), 200

    except (Error, ValueError, ConnectionError) as e:
        print(f"--- ERROR during decomposition save for {original_table_name} ---")
        print(f"Error: {e}")
        print("Executed SQL before error:")
        for sql in sql_executed: print(sql)
        if conn:
            print("Rolling back transaction...")
            conn.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to save decomposition: {e}", "details": traceback.format_exc()}), 500
    except Exception as ex:
         print(f"--- UNEXPECTED ERROR during decomposition save for {original_table_name} ---")
         print(f"Error: {ex}")
         if conn:
            print("Rolling back transaction...")
            conn.rollback()
         import traceback
         traceback.print_exc()
         return jsonify({"error": f"An unexpected server error occurred: {ex}", "details": traceback.format_exc()}), 500

    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()




if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000)