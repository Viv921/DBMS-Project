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

ALLOWED_AGGREGATES = {'COUNT', 'SUM', 'AVG', 'MIN', 'MAX'}
ALLOWED_JOIN_TYPES = {'INNER', 'LEFT', 'RIGHT'}
ALLOWED_OPERATORS = {'=', '!=', '>', '<', '>=', '<=', 'LIKE', 'NOT LIKE', 'IS NULL', 'IS NOT NULL'}

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
    where_clause_items = []
    for condition in where_conditions:
        table = sanitize_identifier(condition.get('table'))
        column = sanitize_identifier(condition.get('column'))
        operator = str(condition.get('operator', '=')).upper()
        value = condition.get('value')

        if not (table and column): return jsonify({"error": f"Incomplete where condition: {condition}"}), 400
        if table not in tables_in_query: return jsonify({"error": f"WHERE condition uses table '{table}' not in FROM/JOIN clauses"}), 400
        if operator not in ALLOWED_OPERATORS: return jsonify({"error": f"Invalid where operator: {operator}"}), 400

        qualified_col = f"`{table}`.`{column}`"
        if operator in ('IS NULL', 'IS NOT NULL'):
            where_clause_items.append(f"{qualified_col} {operator}")
        else:
            where_clause_items.append(f"{qualified_col} {operator} %s")
            params.append(value)

    if where_clause_items:
        sql_parts.append(f"WHERE {' AND '.join(where_clause_items)}")


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

        # --- Helper to build WHERE clause string and params ---
        def build_where_clause(conditions_list):
            where_items = []
            where_params = []
            if not isinstance(conditions_list, list):
                raise ValueError("WHERE conditions must be a list")

            for condition in conditions_list:
                column = sanitize_identifier(condition.get('column'))
                # Ensure operator is uppercase and allowed
                operator = str(condition.get('operator', '=')).strip().upper()
                value = condition.get('value')

                if not column: raise ValueError(f"Incomplete where condition (missing column): {condition}")
                if operator not in ALLOWED_OPERATORS: raise ValueError(f"Invalid where operator: {operator}")

                # No table prefix needed as FROM/UPDATE/DELETE applies to one table
                safe_col_ref = f"`{column}`"

                if operator in ('IS NULL', 'IS NOT NULL'):
                    # Value should be ignored for IS NULL / IS NOT NULL
                    where_items.append(f"{safe_col_ref} {operator}")
                    if value is not None and value != '':
                         print(f"Warning: Value '{value}' provided for operator '{operator}' will be ignored.")
                else:
                    # Use placeholders for values for all other operators
                    where_items.append(f"{safe_col_ref} {operator} %s")
                    where_params.append(value)

            if not where_items:
                 # Safety: Prevent UPDATE/DELETE without WHERE - frontend should also check this
                 raise ValueError("WHERE clause cannot be empty for UPDATE/DELETE operations.")

            return " AND ".join(where_items), where_params
        # --- End Helper ---


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
            if not set_data: return jsonify({"error": "Missing SET data for UPDATE operation"}), 400
            if not where_conditions: return jsonify({"error": "Missing WHERE conditions for UPDATE operation"}), 400

            set_clauses = []
            set_values = []
            for col, val in set_data.items():
                safe_col = sanitize_identifier(col)
                if not safe_col: return jsonify({"error": f"Invalid column name in SET clause: {col}"}), 400
                set_clauses.append(f"`{safe_col}` = %s")
                set_values.append(val)

            try:
                where_clause_sql, where_params = build_where_clause(where_conditions)
            except ValueError as ve:
                 return jsonify({"error": f"Invalid WHERE clause: {ve}"}), 400

            sql = f"UPDATE `{table_name}` SET {', '.join(set_clauses)} WHERE {where_clause_sql};"
            params = set_values + where_params # Order: SET values first, then WHERE values

        elif operation == 'DELETE':
            if not where_conditions: return jsonify({"error": "Missing WHERE conditions for DELETE operation"}), 400

            try:
                where_clause_sql, where_params = build_where_clause(where_conditions)
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




if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000)