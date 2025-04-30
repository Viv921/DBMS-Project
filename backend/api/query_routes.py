# query_routes.py

from flask import Blueprint, jsonify, request
from mysql.connector import Error
from .helpers import (
    sanitize_identifier, build_where_clause, build_having_clause, # Added build_having_clause
    ALLOWED_JOIN_TYPES, ALLOWED_AGGREGATES, ALLOWED_OPERATORS,
    ALLOWED_ORDER_DIRECTIONS # Added
)
from db import get_db_connection

query_bp = Blueprint('query', __name__)

@query_bp.route('/api/execute_select', methods=['POST'])
def execute_select_query():
    """
    Handles POST requests to execute a SELECT query based on a JSON definition.
    Builds and executes SQL including SELECT, FROM, JOIN, WHERE, GROUP BY, HAVING, ORDER BY clauses.
    """
    # --- Request validation ---
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    query_def = request.get_json()
    if not query_def:
        return jsonify({"error": "No JSON data received"}), 400
    print(f"Received query definition: {query_def}") # Debugging log

    # --- Extract Query Definition Parts ---
    select_parts = query_def.get('select', [])
    from_tables = query_def.get('from', [])
    join_conditions = query_def.get('joins', [])
    where_conditions = query_def.get('where', [])
    group_by_columns = query_def.get('groupBy', [])
    having_conditions = query_def.get('having', []) # New
    order_by_clauses = query_def.get('orderBy', []) # New

    # --- Basic Validation ---
    if not from_tables:
        return jsonify({"error": "Query must specify at least one table in 'from'"}), 400
    if not select_parts:
        return jsonify({"error": "Query must specify columns or aggregates in 'select'"}), 400
    # Require JOINs if multiple tables are selected
    if len(from_tables) > 1 and not join_conditions:
        return jsonify({"error": f"Multiple tables ({', '.join(from_tables)}) selected. Please define JOIN conditions."}), 400
    # Validate HAVING requires GROUP BY or Aggregates
    has_aggregates_in_select = any(p.get('type') == 'aggregate' for p in select_parts)
    if having_conditions and not (group_by_columns or has_aggregates_in_select):
         return jsonify({"error": "HAVING clause can only be used when GROUP BY or aggregate functions are present in SELECT."}), 400

    # --- Initialization ---
    sql_parts = [] # List to build the SQL query string parts
    params = [] # List for query parameters to prevent injection
    tables_in_query = set() # Track tables accessible via FROM/JOIN
    select_aliases = set() # Track aliases defined in SELECT for use in HAVING/ORDER BY

    # --- 1. Build SELECT Clause ---
    select_clause_items = []
    has_aggregates = False # Flag if any aggregate function is used

    for item in select_parts:
        item_type = item.get('type')
        table = sanitize_identifier(item.get('table'))
        column = item.get('column') # Raw column name or '*'
        safe_column = sanitize_identifier(column) if column != '*' else '*'
        qualify = len(from_tables) > 1 # Qualify column names with table name if multiple tables

        if item_type == 'column':
            if not table or not safe_column: return jsonify({"error": f"Invalid column definition: {item}"}), 400
            select_clause_items.append(f"`{table}`.`{safe_column}`" if qualify else f"`{safe_column}`")

        elif item_type == 'aggregate':
            has_aggregates = True
            func = str(item.get('func', '')).upper()
            alias = sanitize_identifier(item.get('alias'))
            if not table: return jsonify({"error": f"Missing table for aggregate {func}: {item}"}), 400
            if func not in ALLOWED_AGGREGATES: return jsonify({"error": f"Invalid aggregate func: {func}"}), 400
            if not column: return jsonify({"error": f"Missing column for aggregate {func}"}), 400
            if column == '*' and func != 'COUNT': return jsonify({"error": f"'*' only allowed with COUNT"}), 400
            if column != '*' and not safe_column: return jsonify({"error": f"Invalid col name for aggregate {func}: {column}"}), 400

            # Build the aggregate function string (e.g., COUNT(`table`.`col`) or SUM(`col`))
            target_col = f"`{safe_column}`" if column != '*' else '*'
            agg_target = f"`{table}`.{target_col}" if qualify and column != '*' else target_col
            agg_str = f"{func}({agg_target})"

            if alias:
                agg_str += f" AS `{alias}`"
                select_aliases.add(alias) # Store the valid alias
            else:
                # It's good practice to require aliases for aggregates if they might be used later
                return jsonify({"error": f"Aggregate function {func}({column}) must have an alias defined."}), 400
            select_clause_items.append(agg_str)
        else:
            return jsonify({"error": f"Unknown select item type: {item_type}"}), 400

    if not select_clause_items:
        return jsonify({"error": "No valid columns or aggregates found for SELECT clause."}), 400
    sql_parts.append(f"SELECT {', '.join(select_clause_items)}")


    # --- 2. Build FROM and JOIN Clauses ---
    first_table = sanitize_identifier(from_tables[0])
    if not first_table: return jsonify({"error": "Invalid first table name"}), 400
    sql_parts.append(f"FROM `{first_table}`")
    tables_in_query.add(first_table)

    # Add JOIN clauses sequentially
    for join in join_conditions:
        join_type = str(join.get('type', 'INNER')).upper()
        left_table = sanitize_identifier(join.get('leftTable'))
        left_col = sanitize_identifier(join.get('leftCol'))
        right_table = sanitize_identifier(join.get('rightTable'))
        right_col = sanitize_identifier(join.get('rightCol'))

        # Basic validation
        if join_type not in ALLOWED_JOIN_TYPES: return jsonify({"error": f"Invalid join type: {join_type}"}), 400
        if not (left_table and left_col and right_table and right_col): return jsonify({"error": f"Incomplete join definition: {join}"}), 400
        # Ensure tables are part of the overall selection
        if left_table not in from_tables or right_table not in from_tables:
             return jsonify({"error": f"JOIN involves table(s) not selected in 'FROM': {left_table}, {right_table}"}), 400
        # Ensure join connects to existing tables
        if left_table not in tables_in_query and right_table not in tables_in_query:
             return jsonify({"error": f"Join between {left_table} and {right_table} does not connect to the existing query tables ({', '.join(tables_in_query)}). Joins must link sequentially."}), 400

        # Add the join clause, assuming right_table is being joined "onto" the existing structure
        sql_parts.append(f"{join_type} JOIN `{right_table}` ON `{left_table}`.`{left_col}` = `{right_table}`.`{right_col}`")
        tables_in_query.add(right_table) # Mark the joined table as accessible

    # Validation: Check if all 'from_tables' were actually included via FROM/JOIN chain
    unreached_tables = set(from_tables) - tables_in_query
    if unreached_tables:
         return jsonify({"error": f"Table(s) '{', '.join(unreached_tables)}' selected but not reachable via FROM/JOIN chain."}), 400

    # --- Validation: Check if tables used in SELECT/Aggregates are valid ---
    select_tables_used = set()
    for item in select_parts:
        table = sanitize_identifier(item.get('table'))
        if table: select_tables_used.add(table)

    select_tables_not_in_query = select_tables_used - tables_in_query
    if select_tables_not_in_query:
        return jsonify({"error": f"SELECT list uses columns from table(s) '{', '.join(select_tables_not_in_query)}' which are not in FROM or JOIN clauses."}), 400


    # --- 3. Build WHERE Clause ---
    if where_conditions:
        try:
            # Qualify column names before passing to helper if multiple tables involved
            qualified_where = []
            qualify = len(tables_in_query) > 1
            for cond in where_conditions:
                table = sanitize_identifier(cond.get('table'))
                column = sanitize_identifier(cond.get('column'))
                if not table or not column: raise ValueError(f"Incomplete WHERE condition details: {cond}")
                if table not in tables_in_query: raise ValueError(f"Table '{table}' used in WHERE condition not found in FROM/JOIN clauses.")
                # Use qualified 'table.column' if needed, otherwise just 'column'
                column_ref = f"{table}.{column}" if qualify else column
                qualified_where.append({**cond, 'column': column_ref}) # Use updated column ref

            where_clause_sql, where_params = build_where_clause(qualified_where)
            if where_clause_sql:
                sql_parts.append(f"WHERE {where_clause_sql}")
                params.extend(where_params)
        except ValueError as ve:
             return jsonify({"error": f"Invalid WHERE clause: {ve}"}), 400


    # --- 4. Build GROUP BY Clause ---
    group_by_clause_items = []
    if group_by_columns:
        # Standard SQL requires that if you use aggregates and select non-aggregated columns,
        # you must group by ALL non-aggregated columns.
        non_aggregated_select_cols_map = {} # Store 'input_ref': '`sql_ref`'
        qualify = len(tables_in_query) > 1
        for item in select_parts:
             if item.get('type') == 'column':
                  table = sanitize_identifier(item.get('table'))
                  column = sanitize_identifier(item.get('column'))
                  if table and column:
                       input_ref = f"{table}.{column}" # Frontend sends this format
                       sql_ref = f"`{table}`.`{column}`" if qualify else f"`{column}`"
                       non_aggregated_select_cols_map[input_ref] = sql_ref

        for col_ref in group_by_columns: # Expecting "table.column" format from frontend
             parts = col_ref.split('.', 1)
             if len(parts) != 2: return jsonify({"error": f"Invalid GROUP BY format (expect 'table.column'): {col_ref}"}), 400
             table, column = sanitize_identifier(parts[0]), sanitize_identifier(parts[1])

             if not (table and column): return jsonify({"error": f"Invalid GROUP BY identifiers: {col_ref}"}), 400
             if table not in tables_in_query: return jsonify({"error": f"GROUP BY column '{col_ref}' uses table not in query."}), 400

             # Check if this grouped column corresponds to a non-aggregated column in SELECT
             # The key in the map should match the format from the frontend 'table.column'
             if has_aggregates and col_ref not in non_aggregated_select_cols_map:
                  return jsonify({"error": f"GROUP BY column '{col_ref}' must correspond to a non-aggregated column in the SELECT list when aggregate functions are used."}), 400

             # Use qualified name in the actual SQL GROUP BY clause
             group_by_clause_items.append(f"`{table}`.`{column}`")

        if group_by_clause_items:
             sql_parts.append(f"GROUP BY {', '.join(group_by_clause_items)}")

        # Additional validation: If aggregates and non-aggregates are selected, all non-aggregates MUST be in group by
        if has_aggregates and non_aggregated_select_cols_map:
            selected_non_agg_refs = set(non_aggregated_select_cols_map.keys())
            grouped_refs = set(group_by_columns)
            if selected_non_agg_refs != grouped_refs:
                missing_group_by = selected_non_agg_refs - grouped_refs
                extra_group_by = grouped_refs - selected_non_agg_refs
                error_parts = []
                if missing_group_by: error_parts.append(f"columns not grouped: {', '.join(missing_group_by)}")
                # Extra group by columns are less common error, usually allowed if they exist in table
                # if extra_group_by: error_parts.append(f"extra columns grouped: {', '.join(extra_group_by)}")
                if error_parts:
                    return jsonify({"error": f"Mismatch between non-aggregated SELECT columns and GROUP BY clause. Details: {'; '.join(error_parts)}"}), 400


    # --- 5. Build HAVING Clause ---
    if having_conditions:
        # HAVING comes after GROUP BY
        if not (group_by_columns or has_aggregates):
             # This check is also done earlier, but good to be robust
             return jsonify({"error": "HAVING clause requires GROUP BY or aggregate functions."}), 400
        try:
            # Pass the collected aliases for validation within the helper
            having_clause_sql, having_params = build_having_clause(having_conditions, select_aliases)
            print("Having clause:", having_clause_sql)
            if having_clause_sql:
                sql_parts.append(f"HAVING {having_clause_sql}")
                params.extend(having_params)
        except ValueError as ve:
            return jsonify({"error": f"Invalid HAVING clause: {ve}"}), 400


    # --- 6. Build ORDER BY Clause ---
    order_by_items = []
    if order_by_clauses:
        # ORDER BY comes last (before LIMIT, if any)
        # Determine valid terms for ordering: non-aggregated selected columns and aliases
        orderable_terms = {} # Store as 'term_identifier': '`quoted_sql_term`'
        qualify = len(tables_in_query) > 1
        for item in select_parts:
            if item.get('type') == 'column':
                table = sanitize_identifier(item.get('table'))
                column = sanitize_identifier(item.get('column'))
                if table and column:
                    # Identifier used in frontend: 'table.column'
                    input_key = f"{table}.{column}"
                    # SQL term: `table`.`column` or `column`
                    sql_term = f"`{table}`.`{column}`" if qualify else f"`{column}`"
                    orderable_terms[input_key] = sql_term
            elif item.get('type') == 'aggregate' and item.get('alias'):
                alias = sanitize_identifier(item.get('alias'))
                if alias:
                    # Identifier used in frontend: 'alias'
                    input_key = alias
                    # SQL term: `alias`
                    sql_term = f"`{alias}`"
                    orderable_terms[input_key] = sql_term

        for clause in order_by_clauses:
            term_ref = clause.get('term') # Expecting 'table.column' or 'alias' from frontend
            direction = str(clause.get('direction', 'ASC')).upper()

            if not term_ref: return jsonify({"error": f"Missing column/alias reference in ORDER BY clause: {clause}"}), 400
            if direction not in ALLOWED_ORDER_DIRECTIONS: return jsonify({"error": f"Invalid ORDER BY direction: {direction}"}), 400

            # The term_ref from frontend should directly match a key in orderable_terms
            sql_term_to_order = orderable_terms.get(term_ref)

            if not sql_term_to_order:
                 # Error if the term isn't found in the map of selectable/aliased terms
                 allowed_keys = list(orderable_terms.keys())
                 return jsonify({"error": f"ORDER BY term '{term_ref}' is not found in the SELECT list columns or aliases. Allowed terms: {allowed_keys if allowed_keys else 'None'}"}), 400

            order_by_items.append(f"{sql_term_to_order} {direction}")

        if order_by_items:
            sql_parts.append(f"ORDER BY {', '.join(order_by_items)}")


    # --- Combine and Execute ---
    final_sql = "\n".join(sql_parts) + ";"
    print(f"--- Generated SQL ({len(params)} params) ---")
    print(final_sql)
    print(f"Parameters: {params}")
    print(f"---------------------")

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn or not conn.is_connected(): return jsonify({"error": "Database connection failed"}), 500
        # Use dictionary=False to get tuples, matching frontend expectation
        cursor = conn.cursor(dictionary=False)
        cursor.execute(final_sql, tuple(params)) # Ensure params is a tuple for execution
        results_tuples = cursor.fetchall()
        column_names = cursor.column_names
        print(f"Query executed successfully. Columns: {column_names}, Rows fetched: {len(results_tuples)}")
        return jsonify({"columns": column_names, "rows": results_tuples}), 200

    except Error as e:
        # Provide more informative error messages based on MySQL error codes
        print(f"Database Error executing query: {e}")
        print(f"SQL attempted: {final_sql}")
        print(f"Params: {params}")
        error_msg = f"Database error ({e.errno}): {e.msg}" if hasattr(e, 'errno') and hasattr(e, 'msg') else f"Database error: {e}"
        if hasattr(e, 'errno'):
             if e.errno == 1054: error_msg = f"DB Error: Unknown column specified. Check spelling/tables/aliases. (Details: {e.msg})"
             elif e.errno == 1146: error_msg = f"DB Error: Table does not exist. (Details: {e.msg})"
             elif e.errno == 1064: error_msg = f"DB Error: Syntax error in generated SQL. Check query builder logic. (Details: {e.msg})"
             elif e.errno == 1055: # Error related to non-aggregated columns not in GROUP BY
                 error_msg = f"DB Error: A selected column is not in GROUP BY clause and depends on non-aggregated columns. Adjust SELECT or GROUP BY. (Details: {e.msg})"
             # Add more specific error mappings if needed

        return jsonify({"error": error_msg, "sql_attempted": final_sql}), 500 # Consider removing sql_attempted in production
    except Exception as ex:
         # Catch any other unexpected errors
         print(f"Unexpected Error executing query: {ex}")
         return jsonify({"error": f"An unexpected server error occurred: {ex}"}), 500
    finally:
        # Ensure database resources are closed
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()