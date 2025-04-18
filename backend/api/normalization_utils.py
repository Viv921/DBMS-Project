from itertools import chain, combinations
from collections import defaultdict
from copy import deepcopy
from mysql.connector import Error
from .helpers import MYSQL_TYPE_MAP, sanitize_identifier
from db import get_db_connection


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