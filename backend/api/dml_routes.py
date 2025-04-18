from flask import Blueprint, jsonify, request
from mysql.connector import Error
from .helpers import sanitize_identifier, build_where_clause
from db import get_db_connection

dml_bp = Blueprint('dml', __name__)

@dml_bp.route('/api/execute_dml', methods=['POST'])
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
