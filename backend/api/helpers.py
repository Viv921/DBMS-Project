from collections import defaultdict  # For grouping columns by table
from itertools import chain, combinations  # For closure/key algorithms
from copy import deepcopy

ALLOWED_AGGREGATES = {'COUNT', 'SUM', 'AVG', 'MIN', 'MAX'}
ALLOWED_JOIN_TYPES = {'INNER', 'LEFT', 'RIGHT'}
ALLOWED_OPERATORS = {'=', '!=', '>', '<', '>=', '<=', 'LIKE', 'NOT LIKE', 'IS NULL', 'IS NOT NULL'}
ALLOWED_ORDER_DIRECTIONS = {'ASC', 'DESC'}

MYSQL_TYPE_MAP = {
    'INT': 'INT',
    'VARCHAR(255)': 'VARCHAR(255)',
    'TEXT': 'TEXT',
    'DATE': 'DATE',
    'BOOLEAN': 'BOOLEAN',  # Or TINYINT(1)
    'DECIMAL(10,2)': 'DECIMAL(10, 2)',
    'TIMESTAMP': 'TIMESTAMP',
    'FLOAT': 'FLOAT',
}


def sanitize_identifier(name):
    if not name:
        return None
    # Allow '.' for qualified names initially, handle splitting later if needed
    sanitized = "".join(c if c.isalnum() or c == '_' or c == '.' else '_' for c in str(name).replace(' ', '_'))
    # Basic check for leading character validity (adjust if needed for aliases)
    if not sanitized or not (sanitized[0].isalpha() or sanitized[0] == '_'):
        sanitized = f"col_{sanitized}" # Generic prefix if needed

    # Check against a broader list of reserved keywords if identifier could be simple
    # Note: This might be too broad if aliases can intentionally match keywords, adjust if needed.
    # A more robust approach checks context (e.g., is it an alias definition vs. usage).
    RESERVED_KEYWORDS = {
        'TABLE', 'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'WHERE', 'FROM', 'CREATE',
        'ALTER', 'DROP', 'INDEX', 'KEY', 'PRIMARY', 'FOREIGN', 'GROUP', 'BY', 'ORDER',
        'ASC', 'DESC', 'HAVING', 'JOIN', 'LEFT', 'RIGHT', 'INNER', 'ON', 'AS',
        'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'AND', 'OR', 'NOT', 'NULL', 'IS', 'LIKE'
        # Add more if necessary
    }
    if '.' not in sanitized and sanitized.upper() in RESERVED_KEYWORDS:
        sanitized = f"col_{sanitized}"

    # Escape backticks within the identifier itself if they somehow exist
    sanitized = sanitized.replace('`', '``')

    return sanitized

def build_where_clause(conditions_list):
    where_clause_parts = []
    where_params = []
    if not isinstance(conditions_list, list):
        raise ValueError("WHERE conditions must be a list")

    for index, condition in enumerate(conditions_list):
        # Expecting fully qualified 'table.column' or just 'column' if unambiguous
        # Backend route should qualify if needed before passing here.
        column_ref = condition.get('column') # Let route handle table qualification
        operator = str(condition.get('operator', '=')).strip().upper()
        value = condition.get('value')
        connector = str(condition.get('connector', 'AND')).strip().upper() if index > 0 else None

        # Basic validation - route should do more comprehensive checks
        if not column_ref:
            raise ValueError(f"Incomplete where condition (missing column): {condition}")
        if operator not in ALLOWED_OPERATORS:
            raise ValueError(f"Invalid where operator: {operator}")
        if connector and connector not in ('AND', 'OR'):
            raise ValueError(f"Invalid connector: {connector}")

        # Sanitize parts - assume column_ref might be "table.column" or just "column" or alias
        # Proper quoting handles most cases. If it's an alias, it shouldn't have '.'
        parts = column_ref.split('.', 1)
        if len(parts) == 2:
            safe_col_ref = f"`{sanitize_identifier(parts[0])}`.`{sanitize_identifier(parts[1])}`"
        else:
            safe_col_ref = f"`{sanitize_identifier(column_ref)}`" # Simple column or alias

        if connector:
            where_clause_parts.append(connector)

        if operator in ('IS NULL', 'IS NOT NULL'):
            where_clause_parts.append(f"{safe_col_ref} {operator}")
            # Optional: Log warning if value is provided for IS NULL/IS NOT NULL
            if value is not None and str(value).strip() != '':
                 print(f"Warning: Value '{value}' provided for WHERE operator '{operator}' on column '{column_ref}' will be ignored.")
        else:
            where_clause_parts.append(f"{safe_col_ref} {operator} %s")
            where_params.append(value)

    if not where_clause_parts:
        return "", []

    final_where_sql = " ".join(where_clause_parts)
    return final_where_sql, where_params


def build_having_clause(conditions_list, allowed_select_aliases):
    """
    Builds the HAVING clause SQL string and parameters.
    Handles conditions involving aggregate functions or columns present in GROUP BY.

    Args:
        conditions_list: List of condition dictionaries from the frontend.
                         Each dict expects keys like: 'column', 'operator', 'value', 'connector',
                         and optionally 'func' if applying an aggregate within HAVING.
                         'column' here can be a direct column name (assumed grouped),
                         an alias from the SELECT list, or a column to apply 'func' on.
        allowed_select_aliases: A set of aliases defined in the SELECT clause.

    Returns:
        A tuple: (sql_string, params_list)
    """
    having_clause_parts = []
    having_params = []
    if not isinstance(conditions_list, list):
        raise ValueError("HAVING conditions must be a list")

    for index, condition in enumerate(conditions_list):
        column_ref = condition.get('column') # Can be alias, grouped column, or target for aggregate
        func = str(condition.get('func', '')).strip().upper() # Aggregate func (COUNT, SUM, etc.)
        operator = str(condition.get('operator', '=')).strip().upper()
        value = condition.get('value')
        connector = str(condition.get('connector', 'AND')).strip().upper() if index > 0 else None

        # --- Validation ---
        if not column_ref:
            raise ValueError(f"Incomplete having condition (missing column/alias reference): {condition}")
        if func and func not in ALLOWED_AGGREGATES:
             raise ValueError(f"Invalid aggregate function in HAVING: {func}")
        if operator not in ALLOWED_OPERATORS:
            raise ValueError(f"Invalid having operator: {operator}")
        if connector and connector not in ('AND', 'OR'):
            raise ValueError(f"Invalid connector: {connector}")
        # Specific HAVING validation (e.g., ensuring column is grouped or aggregated)
        # should ideally happen in the calling route based on query context.

        # --- Build Condition Term ---
        term = ""
        safe_column_ref = sanitize_identifier(column_ref) # Sanitize column/alias name

        if func: # Aggregate function used in HAVING condition (e.g., HAVING COUNT(col) > 5)
            if column_ref == '*': # Handle COUNT(*) case
                if func != 'COUNT': raise ValueError(f"HAVING: '*' only allowed with COUNT")
                target_col = '*'
            else:
                # Assume column_ref might be qualified 'table.column' if used with func
                parts = column_ref.split('.', 1)
                if len(parts) == 2:
                     target_col = f"`{sanitize_identifier(parts[0])}`.`{sanitize_identifier(parts[1])}`"
                else:
                     # This case (aggregate on a non-qualified column in HAVING) might be ambiguous
                     # Best practice is usually to aggregate in SELECT and use alias in HAVING
                     # Or ensure the non-qualified column is unambiguously groupable.
                     # We'll assume it refers to a column in one of the FROM/JOIN tables.
                     # More robust validation needed in route if strictness required.
                     target_col = f"`{safe_column_ref}`"

            term = f"{func}({target_col})"
        else: # Direct reference to a grouped column or a SELECT alias
            # Check if it's a known alias, otherwise treat as a potentially grouped column
            is_alias = safe_column_ref in allowed_select_aliases
            # If it's an alias or a simple identifier, quote it simply.
            # If it contains '.', assume it's a qualified grouped column 'table.column'.
            if is_alias or '.' not in safe_column_ref:
                 term = f"`{safe_column_ref}`"
            else:
                 parts = safe_column_ref.split('.', 1) # Re-split sanitized name
                 if len(parts) == 2:
                      term = f"`{parts[0]}`.`{parts[1]}`"
                 else: # Should not happen if '.' is present, but fallback
                      term = f"`{safe_column_ref}`"

        # --- Append to Clause ---
        if connector:
            having_clause_parts.append(connector)

        if operator in ('IS NULL', 'IS NOT NULL'):
            having_clause_parts.append(f"{term} {operator}")
            if value is not None and str(value).strip() != '':
                 print(f"Warning: Value '{value}' provided for HAVING operator '{operator}' on term '{term}' will be ignored.")
        else:
            having_clause_parts.append(f"{term} {operator} %s")
            having_params.append(value)

    if not having_clause_parts:
        return "", []

    final_having_sql = " ".join(having_clause_parts)
    return final_having_sql, having_params