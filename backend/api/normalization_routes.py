from flask import Blueprint, jsonify, request
from itertools import chain, combinations
from copy import deepcopy
from mysql.connector import Error
from .helpers import sanitize_identifier
from db import get_db_connection
from .normalization_utils import (get_table_schema_details, calculate_closure, find_candidate_keys, get_minimal_cover, check_fd_preservation, generate_create_table_sql, generate_data_migration_sql)

normalization_bp = Blueprint('normalization', __name__)

@normalization_bp.route('/api/analyze_normalization', methods=['POST'])
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

@normalization_bp.route('/api/decompose/3nf', methods=['POST'])
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


@normalization_bp.route('/api/decompose/bcnf', methods=['POST'])
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



@normalization_bp.route('/api/save_decomposition', methods=['POST'])
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