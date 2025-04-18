from collections import defaultdict  # For grouping columns by table
from itertools import chain, combinations  # For closure/key algorithms
from copy import deepcopy

ALLOWED_AGGREGATES = {'COUNT', 'SUM', 'AVG', 'MIN', 'MAX'}
ALLOWED_JOIN_TYPES = {'INNER', 'LEFT', 'RIGHT'}
ALLOWED_OPERATORS = {'=', '!=', '>', '<', '>=', '<=', 'LIKE', 'NOT LIKE', 'IS NULL', 'IS NOT NULL'}

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
    sanitized = "".join(c if c.isalnum() or c == '_' else '_' for c in name.replace(' ', '_'))
    if not sanitized or not (sanitized[0].isalpha() or sanitized[0] == '_'):
        sanitized = f"tbl_{sanitized}"
    if sanitized.upper() in ['TABLE', 'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'WHERE', 'FROM', 'CREATE', 'ALTER', 'DROP', 'INDEX', 'KEY', 'PRIMARY', 'FOREIGN']:
        sanitized = f"tbl_{sanitized}"
    return sanitized


def build_where_clause(conditions_list):
    where_clause_parts = []
    where_params = []
    if not isinstance(conditions_list, list):
        raise ValueError("WHERE conditions must be a list")

    for index, condition in enumerate(conditions_list):
        column = sanitize_identifier(condition.get('column'))
        operator = str(condition.get('operator', '=')).strip().upper()
        value = condition.get('value')
        connector = str(condition.get('connector', 'AND')).strip().upper() if index > 0 else None

        if not column:
            raise ValueError(f"Incomplete where condition (missing column): {condition}")
        if operator not in ALLOWED_OPERATORS:
            raise ValueError(f"Invalid where operator: {operator}")
        if connector and connector not in ('AND', 'OR'):
            raise ValueError(f"Invalid connector: {connector}")

        if connector:
            where_clause_parts.append(connector)

        safe_col_ref = f"`{column}`"
        if operator in ('IS NULL', 'IS NOT NULL'):
            where_clause_parts.append(f"{safe_col_ref} {operator}")
            if value is not None and value != '':
                print(f"Warning: Value '{value}' provided for operator '{operator}' will be ignored.")
        else:
            where_clause_parts.append(f"{safe_col_ref} {operator} %s")
            where_params.append(value)

    if not where_clause_parts:
        return "", []

    final_where_sql = " ".join(where_clause_parts)
    return final_where_sql, where_params