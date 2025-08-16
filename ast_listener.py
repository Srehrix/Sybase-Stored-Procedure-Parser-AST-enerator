import re
from antlr4 import ParseTreeListener
from TSqlParserListener import TSqlParserListener
from TSqlParser import TSqlParser


def normalize_sql(sql_text):
    sql_text = re.sub(r"([<>!=]=|[<>]|=|\+|-|\*|/)", r" \1 ", sql_text)
    sql_text = re.sub(r"<\s*>", "<>", sql_text)  # normalize < >
    sql_text = re.sub(r"!\s*=", "!=", sql_text)  # normalize ! =
    sql_text = re.sub(r"\bIS\s*NOT\s*NULL\b", "IS NOT NULL",
                      sql_text, flags=re.IGNORECASE)
    sql_text = re.sub(r"\bIS\s*NULL\b", "IS NULL",
                      sql_text, flags=re.IGNORECASE)
    sql_text = re.sub(r",(?=\S)", ", ", sql_text)
    sql_text = re.sub(r"\s+", " ", sql_text)
    return sql_text.strip().rstrip(";")


class ASTBuilder(TSqlParserListener):
    def __init__(self):
        self.ast = []
        self.proc_stack = []
        self.current_proc = None
        self.current_block_body = None
        self.statement_stack = []  # stack for statements
        self.in_catch_block = False
        self.cursor_blocks = {}
        self.block_stack = []
        self.last_if_block = None
        self.schema_registry = {}
        self.schema_metadata = {}

    def _append_statement(self, stmt):
        try:
            if self.statement_stack:
                self.statement_stack[-1].append(stmt)
            elif self.current_proc:
                self.current_proc["statements"].append(stmt)
            else:
                return

            # ✅ Special handling for IF: Add DROP as RAW_SQL to last_if_block
            if self.last_if_block and stmt.get("type") in ["DROP_TABLE", "DROP_PROCEDURE"]:
                raw_sql = {
                    "type": "RAW_SQL",
                    "query": f"DROP {'TABLE' if stmt['type'] == 'DROP_TABLE' else 'PROCEDURE'} {stmt.get('table') or stmt.get('procedure')}"
                }
                if raw_sql not in self.last_if_block["then"]:
                    self.last_if_block["then"].append(raw_sql)

        except Exception as e:
            print(f"❌ Error in _append_statement: {e}")

    def _enter_block(self, block_type):
        if self.block_stack:
            current_block = self.block_stack[-1]
            new_block = []
            current_block[block_type] = new_block
            self.statement_stack.append(new_block)

    def _exit_block(self):
        if self.statement_stack:
            self.statement_stack.pop()

    def enterCreate_or_alter_procedure(self, ctx):
        try:
            # Get full text from the input stream
            text = ctx.start.getInputStream().getText(ctx.start.start, ctx.stop.stop)
            flat = " ".join(text.replace("\n", " ").split())

            # Extract procedure name using regex (handles schema and brackets)
            m = re.search(
                r"\b(?:CREATE|ALTER)\s+PROCEDURE\s+([^\s(]+)", flat, re.IGNORECASE)
            proc_name = m.group(1) if m else "<UNKNOWN_PROC>"

            self.current_proc = {
                "proc_name": proc_name,
                "params": [],
                "variables": [],
                "return_type": "VOID",
                "statements": []
            }

            # Add to procedure stack
            self.proc_stack.append(self.current_proc)
            self.statement_stack.append(self.current_proc["statements"])

        except Exception as e:
            print(f"❌ Error in enterCreate_or_alter_procedure: {e}")

    def exitCreate_or_alter_procedure(self, ctx):
        try:
            proc_obj = self.proc_stack.pop()
            # Do NOT merge global statements into the procedure
            self.ast.append(proc_obj)
            self.statement_stack.pop()
            self.current_proc = None
        except Exception as e:
            print(f"❌ Error in exitCreate_or_alter_procedure: {e}")

    def enterCreate_schema(self, ctx):
        try:
            ids = ctx.id_()
            if ids:
                schema_name = ids[0].getText()  # Safely access the first ID
                self.ast.append({
                    "type": "CREATE_SCHEMA",
                    "schema_name": schema_name
                })
                print(f"✅ Parsed CREATE SCHEMA: {schema_name}")
        except Exception as e:
            print(f"❌ Error parsing CREATE SCHEMA: {e}")

    def enterDeclare_statement(self, ctx):
        try:
            if getattr(self, "in_catch_block", False):
                return

            if not self.current_proc:
                return

            for decl in ctx.declare_local():
                var_name = decl.LOCAL_ID().getText()
                var_type = decl.data_type().getText() if decl.data_type() else "<UNKNOWN>"
                default_val = decl.expression().getText() if decl.expression() else None

                variable = {
                    "name": var_name,
                    "type": var_type if var_type else "<UNKNOWN>"
                }
                if default_val:
                    variable["default"] = normalize_sql(default_val)

                # Avoid duplicates
                self._ensure_variable_exists(var_name, var_type)
                if default_val:
                    for v in self.current_proc["variables"]:
                        if v["name"] == var_name:
                            v["default"] = normalize_sql(default_val)
                            break

        except Exception as e:
            print(f"❌ Error in enterDeclare_statement: {e}")

    def _ensure_variable_exists(self, var_name, inferred_type=None):
        if not self.current_proc:
            return

        normalized = var_name.upper()

        # ❌ Ignore system variables like @@TRANCOUNT or incorrectly parsed @TRANCOUNT
        if normalized.startswith("@@") or normalized in ["@TRANCOUNT"]:
            return

        # ❌ Ignore pseudo-variables like @ExchangeRateISNULL
        if "ISNULL" in normalized:
            return
        if normalized in ["@ERRORMSG", "@ERRORSEVERITY", "@ERRORSTATE"]:
            return

        # ❌ Ignore variables inside CATCH block
        if getattr(self, "in_catch_block", False):
            return

        # Check if variable already exists
        existing = next(
            (v for v in self.current_proc["variables"] if v["name"] == var_name), None)
        if existing:
            if existing["type"] == "<UNKNOWN>" and inferred_type:
                existing["type"] = inferred_type
            return

        # If new variable, add with inferred or UNKNOWN type
        self.current_proc["variables"].append({
            "name": var_name,
            "type": inferred_type if inferred_type else "<UNKNOWN>"
        })

    def _extract_vars(self, text):
        clean_text = re.sub(r"\bISNULL\s*\(", "(", text, flags=re.IGNORECASE)
        clean_text = re.sub(r"\bIS\s+NULL\b", "",
                            clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"\bIS\s+NOT\s+NULL\b", "",
                            clean_text, flags=re.IGNORECASE)
        all_vars = re.findall(r"@\w+", clean_text)
        return [v for v in all_vars if not v.startswith('@@')]

    def enterTry_catch_statement(self, ctx):
        try_block = {"type": "BEGIN_TRY", "body": []}
        self._append_statement(try_block)
        self.block_stack.append(try_block)
        self.statement_stack.append(try_block["body"])

        # ✅ Add BEGIN_TRANSACTION at start
        try_block["body"].append({"type": "BEGIN_TRANSACTION"})

    def exitTry_catch_statement(self, ctx):
        try:
            if self.statement_stack:
                self.statement_stack.pop()
            if self.block_stack:
                try_block = self.block_stack.pop()
                # ✅ Add COMMIT at the end of TRY block
                try_block["body"].append({"type": "COMMIT"})
        except Exception as e:
            print(f"Error in exitTry_catch_statement: {e}")

    def enterCatch_block(self, ctx):
        try:
            # ✅ Mark that we are inside CATCH
            self.in_catch_block = True

            # Create BEGIN_CATCH node
            catch_block = {"type": "BEGIN_CATCH", "body": []}

            # Attach to current TRY block or global statements
            self._append_statement(catch_block)

            # Push the CATCH block body to the stack
            self.statement_stack.append(catch_block["body"])
        except Exception as e:
            print(f"❌ Error in enterCatch_block: {e}")

    def exitCatch_block(self, ctx):
        try:
            # ✅ Reset the CATCH flag
            self.in_catch_block = False

            # Pop from statement stack if it has elements
            if self.statement_stack:
                self.statement_stack.pop()
        except Exception as e:
            print(f"❌ Error in exitCatch_block: {e}")

    def enterSet_statement(self, ctx):
        try:
            text = ctx.start.getInputStream().getText(ctx.start.start, ctx.stop.stop)
            text = " ".join(text.replace("\n", " ").split())

            if "=" in text:
                parts = text.split("=", 1)
                name = parts[0].replace("SET", "", 1).strip()
                value = normalize_sql(parts[1].strip())

                # Type inference
                inferred_type = None
                if re.match(r"^\d+$", value):
                    inferred_type = "INT"
                elif re.match(r"^\d+\.\d+$", value):
                    inferred_type = "DECIMAL(18,2)"
                elif value.upper().startswith("GETDATE()"):
                    inferred_type = "DATE"
                elif value.startswith("'") and value.endswith("'"):
                    inferred_type = "NVARCHAR"
                elif any(op in value for op in ["*", "/", "+", "-"]):
                    inferred_type = "DECIMAL(18,2)"

                self._ensure_variable_exists(name, inferred_type)

                self._append_statement({
                    "type": "SET",
                    "name": name,
                    "value": value
                })
        except Exception as e:
            print(f"Error in enterSet_statement: {e}")

    def enterReturn_statement(self, ctx):
        text = ctx.start.getInputStream().getText(ctx.start.start, ctx.stop.stop)
        expr = text.strip().split("RETURN", 1)[-1].strip()
        self._append_statement({
            "type": "RETURN",
            "expression": expr if expr else None
        })

    def enterSelect_statement(self, ctx):
        try:
            parent = ctx.parentCtx
            inside_cursor = False
            while parent:
                if type(parent).__name__ == "Declare_set_cursor_commonContext":
                    inside_cursor = True
                    break
                parent = parent.parentCtx

            raw_sql = ctx.start.getInputStream().getText(
                ctx.start.start, ctx.stop.stop).strip()
            normalized_sql = normalize_sql(raw_sql)

            # Detect SELECT assignment → convert to SET
            # Detect SELECT assignment with optional FROM clause
            assign_match = re.match(
                r"SELECT\s+(@\w+)\s*=\s*([^\s,]+)", normalized_sql, re.IGNORECASE)

            if assign_match:
                target_var = assign_match.group(1).strip()
                value_expr = normalize_sql(assign_match.group(2).strip())

                # ✅ Try to find table name for schema inference
                from_match = re.search(
                    r"\bFROM\s+([^\s]+)", normalized_sql, re.IGNORECASE)
                from_table = from_match.group(
                    1).strip() if from_match else None

                # ✅ Extract column name if possible
                col_match = re.match(r"([A-Za-z0-9_]+)", value_expr)
                col_name = col_match.group(1) if col_match else None

                # ✅ Infer type from schema if possible
                inferred_type = None
                if col_name and from_table:
                    inferred_type = self._infer_type_from_schema(
                        from_table, col_name)

                # ✅ Register variable
                self._ensure_variable_exists(target_var, inferred_type)

                self._append_statement({
                    "type": "SET",
                    "name": target_var,
                    "value": f"SELECT {target_var} = {value_expr}"
                })
                return

            # SELECT INTO
            if re.search(r"\bINTO\b", normalized_sql, re.IGNORECASE):
                into_vars = []
                match = re.search(r"\bINTO\s+(.+?)\s+FROM",
                                  normalized_sql, re.IGNORECASE | re.DOTALL)
                if match:
                    into_part = match.group(1)
                    into_vars = [v.strip()
                                 for v in re.split(r",\s*", into_part)]

                for var in into_vars:
                    self._ensure_variable_exists(var, None)

                self._append_statement({
                    "type": "SELECT_INTO",
                    "query": normalized_sql,
                    "into_vars": into_vars
                })
                return

            # ✅ If this SELECT is inside a cursor declaration, store column list
            if inside_cursor:
                self.current_cursor_columns = self._extract_select_columns(
                    normalized_sql)

            # Normal SELECT
            self._append_statement({
                "type": "SELECT_INTO",
                "query": normalized_sql,
                "into_vars": []
            })

        except Exception as e:
            print(f"❌ Error parsing SELECT statement: {e}")

    def _update_variable_type(self, var_name, new_type):
        if not self.current_proc or not new_type:
            return
        for v in self.current_proc["variables"]:
            if v["name"].upper() == var_name.upper():
                if v["type"] == "<UNKNOWN>" or v["type"] == "INT":  # Replace generic type
                    v["type"] = new_type
                return

    def _extract_select_columns(self, sql):
        # Simple extraction for now: split by commas until FROM
        cols = []
        select_part = sql.split("FROM")[0].replace("SELECT", "", 1).strip()
        for col in select_part.split(","):
            col_name = col.strip().split()[-1]  # Take alias or last part
            cols.append(col_name)
        return cols

    def enterInsert_statement(self, ctx):
        try:
            raw_text = ctx.start.getInputStream().getText(ctx.start.start, ctx.stop.stop)
            query = normalize_sql(raw_text)

            # Extract table name
            table_name = ""
            match = re.search(
                r"INSERT\s+INTO\s+([^\s(]+)", query, re.IGNORECASE)
            if match:
                table_name = match.group(1)

            # Extract column list (if present)
            columns = []
            col_match = re.search(
                r"INSERT\s+INTO\s+[^\s(]+\s*\(([^)]+)\)", query, re.IGNORECASE)
            if col_match:
                columns = [c.strip() for c in col_match.group(1).split(",")]

            insert_stmt = {
                "type": "INSERT",
                "query": query,
                "table": table_name,
                "columns": columns
            }

            self._append_statement(insert_stmt)
        except Exception as e:
            print(f"❌ Error parsing INSERT: {e}")

    def enterUpdate_statement(self, ctx):
        try:
            raw_text = ctx.start.getInputStream().getText(ctx.start.start, ctx.stop.stop)
            query = normalize_sql(raw_text)

            # Extract table name after UPDATE
            table_name = ""
            match = re.search(r"UPDATE\s+([^\s]+)", query, re.IGNORECASE)
            if match:
                table_name = match.group(1)

            update_stmt = {
                "type": "UPDATE",
                "query": query,
                "table": table_name
            }

            self._append_statement(update_stmt)
        except Exception as e:
            print(f"❌ Error parsing UPDATE: {e}")

    def enterDelete_statement(self, ctx):
        try:
            raw_text = ctx.start.getInputStream().getText(ctx.start.start, ctx.stop.stop)
            query = normalize_sql(raw_text)

            # Extract table name after FROM or DELETE
            table_name = ""
            match = re.search(
                r"(FROM|DELETE)\s+([^\s]+)", query, re.IGNORECASE)
            if match:
                table_name = match.group(2)

            delete_stmt = {
                "type": "DELETE",
                "query": query,
                "table": table_name
            }

            self._append_statement(delete_stmt)
        except Exception as e:
            print(f"❌ Error parsing DELETE: {e}")

    def enterMerge_statement(self, ctx):
        try:
            raw_text = ctx.start.getInputStream().getText(ctx.start.start, ctx.stop.stop)
            query = normalize_sql(raw_text)

            # Extract target table after MERGE INTO
            table_name = ""
            match = re.search(r"MERGE\s+INTO\s+([^\s]+)", query, re.IGNORECASE)
            if match:
                table_name = match.group(1)

            merge_stmt = {
                "type": "MERGE",
                "query": query,
                "table": table_name
            }

            self._append_statement(merge_stmt)
        except Exception as e:
            print(f"❌ Error parsing MERGE: {e}")

    def _get_full_name(self, id_list):
        return ".".join([id_.getText() for id_ in id_list])

    def enterDrop_procedure(self, ctx):
        try:
            proc_name = ctx.func_proc_name_schema(0).getText()
            self._append_statement({
                "type": "DROP_PROCEDURE",
                "procedure": proc_name  # ✅ Schema requires "procedure"
            })
        except Exception as e:
            print(f"❌ Error in DROP PROCEDURE: {e}")

    def enterIf_statement(self, ctx):
        try:
            condition = normalize_sql(ctx.search_condition().getText(
            )) if ctx.search_condition() else "<UNKNOWN_CONDITION>"
            if_block = {
                "type": "IF",
                "condition": condition,
                "then": [],
                "else": []
            }

            # ✅ Detect and register variables inside condition
            if ctx.search_condition():
                condition_text = ctx.search_condition().getText()
                vars_in_condition = self._extract_vars(condition_text)
                for var in vars_in_condition:
                    self._ensure_variable_exists(var)

            # ✅ Attach IF block to correct context
            if self.statement_stack:
                self.statement_stack[-1].append(if_block)
            else:
                if not hasattr(self, "global_statements"):
                    self.global_statements = []
                self.global_statements.append(if_block)

            # Push THEN branch
            self.block_stack.append(if_block)
            self.statement_stack.append(if_block["then"])

            # Track last IF for potential ELSE handling
            self.last_if_block = if_block
        except Exception as e:
            print(f"❌ Error in enterIf_statement: {e}")

    def exitIf_statement(self, ctx):
        try:
            # If we are finishing THEN and an ELSE exists, switch to ELSE
            if self.last_if_block and ctx.ELSE():
                # Switch to ELSE branch
                if self.statement_stack:
                    self.statement_stack.pop()
                self.statement_stack.append(self.last_if_block["else"])
            else:
                # No ELSE, just pop THEN
                if self.statement_stack:
                    self.statement_stack.pop()
                if self.block_stack:
                    self.block_stack.pop()
                self.last_if_block = None
        except Exception as e:
            print(f"❌ Error in exitIf_statement: {e}")

    def enterElse_statement(self, ctx):
        try:
            if self.block_stack:
                current_if = self.block_stack[-1]
                # Switch to ELSE branch
                self.statement_stack.append(current_if["else"])
        except Exception as e:
            print(f"❌ Error in enterElse_statement: {e}")

    def exitElse_statement(self, ctx):
        try:
            if self.statement_stack:
                self.statement_stack.pop()
        except Exception as e:
            print(f"❌ Error in exitElse_statement: {e}")

    def enterWhile_statement(self, ctx):
        try:
            condition = normalize_sql(ctx.search_condition().getText())

            # ✅ Detect FETCH loop pattern: WHILE @@FETCH_STATUS = 0
            if condition.upper().replace(" ", "") == "@@FETCH_STATUS=0":
                for cursor_name, info in self.cursor_blocks.items():
                    if "fetch_loop" not in info:
                        # Pick fetch_into from last fetch or initial fetch
                        fetch_into = []
                        if "last_fetch_into" in info:
                            fetch_into = info["last_fetch_into"]
                        elif "initial_fetch" in info:
                            fetch_into = info["initial_fetch"].get(
                                "fetch_into", [])

                        # ✅ Create CURSOR_LOOP node
                        cursor_loop = {
                            "type": "CURSOR_LOOP",
                            "cursor_name": cursor_name,
                            "condition": "@@FETCH_STATUS = 0",  # Optional
                            "fetch_into": fetch_into,
                            "body": []
                        }

                        # ✅ Merge initial fetch if present
                        if "initial_fetch" in info:
                            cursor_loop["body"].append(info["initial_fetch"])
                            del info["initial_fetch"]

                        # Save and push
                        info["fetch_loop"] = cursor_loop
                        self._append_statement(cursor_loop)
                        self.statement_stack.append(cursor_loop["body"])
                        return  # ✅ Skip normal WHILE handling

            # ✅ Normal WHILE (not cursor loop)
            while_block = {
                "type": "WHILE",
                "condition": condition,
                "body": []
            }
            self._append_statement(while_block)
            self.block_stack.append(while_block)
            self.statement_stack.append(while_block["body"])

        except Exception as e:
            print(f"Error in enterWhile_statement: {e}")

    def exitWhile_statement(self, ctx):
        try:
            self.statement_stack.pop()
            if self.block_stack:
                self.block_stack.pop()
        except Exception as e:
            print(f"Error in exitWhile_statement: {e}")

    def enterBegin_end_block(self, ctx):
        new_block = []
        self.statement_stack.append(new_block)

    def exitBegin_end_block(self, ctx):
        block = self.statement_stack.pop()
        self._append_statement({
            "type": "BLOCK",
            "statements": block
        })

    def enterPrint_statement(self, ctx):
        try:
            text = ctx.getText()
            match = re.search(r"PRINT\s*'([^']+)'", text, re.IGNORECASE)
            message = match.group(1) if match else text
            self._append_statement({
                "type": "RAISE",
                "level": "INFO",  # PRINT is informational
                "message": message
            })
        except Exception as e:
            print(f"Error in enterPrint_statement: {e}")

    def enterThrow_statement(self, ctx):
        try:
            self._append_statement({
                "type": "RAISE",
                "level": "ERROR",
                "message": "THROW"  # You could parse actual THROW args if needed
            })
        except Exception as e:
            print(f"Error in enterThrow_statement: {e}")

    def enterRaiseerror_statement(self, ctx):
        try:
            full_text = ctx.start.getInputStream().getText(ctx.start.start, ctx.stop.stop)
            raise_stmt = {
                "type": "RAISE",
                "level": "ERROR",
                "message": normalize_sql(full_text)
            }
            self._append_statement(raise_stmt)
        except Exception as e:
            print(f"Error in enterRaiseerror_statement: {e}")

    def enterCommit_transaction(self, ctx):
        try:
            self._append_statement({
                "type": "COMMIT"
            })
        except Exception as e:
            print(f"Error in enterCommit_transaction: {e}")

    def enterRollback_transaction(self, ctx):
        try:
            self._append_statement({
                "type": "ROLLBACK"
            })
        except Exception as e:
            print(f"Error in enterRollback_transaction: {e}")

    def enterDeclare_cursor(self, ctx):
        try:
            cursor_name = ctx.cursor_name().getText() if ctx.cursor_name() else "<UNKNOWN>"

            # ✅ Extract query text from full text (since select_statement() may not exist)
            raw_text = ctx.getText()
            query_match = re.search(
                r"FOR\s+(SELECT.+)", raw_text, re.IGNORECASE)
            query_text = query_match.group(
                1) if query_match else "<MISSING QUERY>"
            query_text = normalize_sql(query_text)

            # ✅ Extract column info (best effort)
            columns = []
            col_match = re.findall(r"\b(\w+)\b", query_text)
            for col_name in col_match:
                # Infer type from simple heuristic
                if "ID" in col_name.upper():
                    col_type = "INT"
                elif "SALARY" in col_name.upper() or "AMOUNT" in col_name.upper():
                    col_type = "DECIMAL(18,2)"
                elif "CURRENCY" in col_name.upper():
                    col_type = "CHAR(3)"
                else:
                    col_type = "<UNKNOWN>"
                columns.append((col_name, col_type))

            self.cursor_blocks[cursor_name] = {
                "declare": {
                    "type": "DECLARE_CURSOR",
                    "name": cursor_name,
                    "query": query_text
                },
                "columns": columns
            }

        except Exception as e:
            print(f"Error in enterDeclare_cursor: {e}")

    def enterOpen_cursor(self, ctx):
        try:
            cursor_name = ctx.cursor_name().getText() if ctx.cursor_name() else "<UNKNOWN>"
            self.cursor_blocks.setdefault(cursor_name, {})["open"] = {
                "type": "OPEN_CURSOR",
                "cursor_name": cursor_name
            }
        except Exception as e:
            print(f"Error in enterOpen_cursor: {e}")

        # --- Add this shared handler once ---
    def _handle_fetch_cursor(self, ctx):
        try:
            # Try to extract cursor name (works for several ctx shapes)
            cursor_name = None
            if hasattr(ctx, "cursor_name") and ctx.cursor_name():
                cursor_name = ctx.cursor_name().getText()
            elif hasattr(ctx, "children"):
                # Fallback: scan tokens around FROM
                txt = ctx.start.getInputStream().getText(ctx.start.start, ctx.stop.stop)
                m = re.search(r"\bFROM\s+([A-Za-z0-9_#]+)", txt, re.IGNORECASE)
                cursor_name = m.group(1) if m else "<UNKNOWN>"
            else:
                cursor_name = "<UNKNOWN>"

            # Extract fetch_into variables
            fetch_into = []
            if hasattr(ctx, "LOCAL_ID") and ctx.LOCAL_ID():
                fetch_into = [v.getText() for v in ctx.LOCAL_ID()]
            else:
                full_text = ctx.start.getInputStream().getText(ctx.start.start, ctx.stop.stop)
                m = re.search(r"\bINTO\s+(.+)", full_text, re.IGNORECASE)
                if m:
                    fetch_into = [v.strip() for v in m.group(1).split(",")]

            # Ensure cursor bucket exists
            if cursor_name not in self.cursor_blocks:
                self.cursor_blocks[cursor_name] = {}

            # Type inference from declared cursor columns (if any)
            columns = self.cursor_blocks[cursor_name].get("columns", [])
            for i, var in enumerate(fetch_into):
                inferred_type = columns[i][1] if i < len(columns) else None
                self._ensure_variable_exists(var, inferred_type)

            # Save the last fetch vars so WHILE can pick them up
            self.cursor_blocks[cursor_name]["last_fetch_into"] = fetch_into

            # If we already created the loop, update it now
            loop = self.cursor_blocks[cursor_name].get("fetch_loop")
            if loop:
                loop["fetch_into"] = fetch_into
                # push loop body so subsequent statements go inside the loop
                self.statement_stack.append(loop["body"])
            else:
                # store initial fetch so we can merge into loop body later
                self.cursor_blocks[cursor_name]["initial_fetch"] = {
                    "type": "FETCH",
                    "cursor_name": cursor_name,
                    "fetch_into": fetch_into
                }

        except Exception as e:
            print(f"Error in _handle_fetch_cursor: {e}")

    # --- Bind the handler to multiple possible rule names ---
    def enterFetch_cursor(self, ctx):           # some grammars use this
        self._handle_fetch_cursor(ctx)

    def enterFetch_cursor_statement(self, ctx):  # your current guess
        self._handle_fetch_cursor(ctx)

    def enterFetch_statement(self, ctx):        # some grammars use this
        self._handle_fetch_cursor(ctx)

    def enterFetch(self, ctx):                  # last-resort catch-all if present
        self._handle_fetch_cursor(ctx)

    def enterClose_cursor(self, ctx):
        try:
            cursor_name = ctx.cursor_name().getText() if ctx.cursor_name() else "<UNKNOWN>"
            self.cursor_blocks.setdefault(cursor_name, {})["close"] = {
                "type": "CLOSE_CURSOR",
                "cursor_name": cursor_name
            }
        except Exception as e:
            print(f"Error in enterClose_cursor: {e}")

    def enterDeallocate_cursor_statement(self, ctx):
        try:
            cursor_name = ctx.cursor_name().getText() if ctx.cursor_name() else "<UNKNOWN>"
            if cursor_name in self.cursor_blocks:
                del self.cursor_blocks[cursor_name]
        except Exception as e:
            print(f"Error in enterDeallocate_cursor_statement: {e}")

    def enterCreate_table(self, ctx):
        try:
            raw_text = ctx.start.getInputStream().getText(ctx.start.start, ctx.stop.stop)

            # Detect table name
            table_name = ""
            if ctx.table_name():
                table_name = ctx.table_name().getText()
            elif ctx.full_table_name():
                table_name = ctx.full_table_name().getText()
            elif ctx.schema_object_name():
                table_name = ctx.schema_object_name().getText()
            elif ctx.id_():
                table_name = ctx.id_().getText()

            # Decide statement type
            if table_name.startswith("#"):
                stmt_type = "DECLARE_TEMP_TABLE"
                table_key = "table"
            else:
                stmt_type = "CREATE_TABLE"
                table_key = "table_name"

            # Prepare statement object (Tool 5 format for columns)
            table_stmt = {
                "type": stmt_type,
                table_key: table_name,
                "columns": [],      # ✅ Strings like "ColumnName DataType"
                "constraints": []   # ✅ Keep constraints for completeness
            }

            # ✅ Initialize schema entry
            normalized_table = table_name.upper()
            self.schema_registry[normalized_table] = {}

            # Parse columns & constraints
            if ctx.column_def_table_constraints():
                for item in ctx.column_def_table_constraints().column_def_table_constraint():
                    col_def = item.column_definition()
                    if col_def:
                        col_name = col_def.id_().getText()
                        col_type = col_def.data_type().getText()
                        col_text = col_def.getText()
                        upper_col_text = col_text.upper()

                        # ✅ For Tool 5: columns as strings
                        column_entry = f"{col_name} {col_type}"
                        table_stmt["columns"].append(column_entry)

                        # ✅ Save to schema registry for inference
                        self.schema_registry[normalized_table][col_name.upper(
                        )] = col_type

                        # ✅ Create variable for temp table column (expected output behavior)
                        if table_name.startswith("#"):
                            var_name = f"@{col_name}"
                            self._ensure_variable_exists(var_name, col_type)

                        # ✅ Constraints parsing
                        if "IDENTITY" in upper_col_text:
                            table_stmt["constraints"].append(
                                {"type": "IDENTITY", "column": col_name})

                        if "NOT NULL" in upper_col_text:
                            table_stmt["constraints"].append(
                                {"type": "NOT_NULL", "column": col_name})

                        if "DEFAULT" in upper_col_text:
                            match = re.search(
                                r"DEFAULT\s+([^\s,)]+)", col_text, re.IGNORECASE)
                            if match:
                                table_stmt["constraints"].append({
                                    "type": "DEFAULT",
                                    "column": col_name,
                                    "value": normalize_sql(match.group(1))
                                })

                        if "CHECK" in upper_col_text:
                            match = re.search(
                                r"CHECK\s*\((.*?)\)", col_text, re.IGNORECASE)
                            if match:
                                table_stmt["constraints"].append({
                                    "type": "CHECK",
                                    "expression": normalize_sql(match.group(1))
                                })

                        # Computed columns
                        if "AS" in upper_col_text and "(" in col_text:
                            match = re.search(
                                r"AS\s*\((.*?)\)\s*(PERSISTED)?", col_text, re.IGNORECASE)
                            if match:
                                expr = normalize_sql(match.group(1))
                                constraint = {
                                    "type": "COMPUTED", "expression": expr}
                                if match.group(2):
                                    constraint["persisted"] = True
                                table_stmt["constraints"].append(constraint)

                    elif item.table_constraint():
                        tcon_text = item.getText()
                        tcon_upper = tcon_text.upper()

                        # Optional constraint name
                        constraint_name = None
                        match_name = re.search(
                            r"CONSTRAINT\s+([^\s]+)", tcon_text, re.IGNORECASE)
                        if match_name:
                            constraint_name = match_name.group(1)

                        # PRIMARY KEY
                        if "PRIMARY" in tcon_upper and "KEY" in tcon_upper:
                            cols = re.findall(r'\((.*?)\)', tcon_text)
                            if cols:
                                col_list = [c.strip()
                                            for c in cols[0].split(',')]
                                constraint = {
                                    "type": "PRIMARY_KEY", "columns": col_list}
                                if constraint_name:
                                    constraint["name"] = constraint_name
                                table_stmt["constraints"].append(constraint)

                        # FOREIGN KEY
                        if "FOREIGN KEY" in tcon_upper and "REFERENCES" in tcon_upper:
                            fk_cols_match = re.search(
                                r'FOREIGN\s+KEY\s*\((.*?)\)', tcon_text, re.IGNORECASE)
                            ref_table_match = re.search(
                                r'REFERENCES\s+([^\s(]+)', tcon_text, re.IGNORECASE)
                            ref_cols_match = re.search(
                                r'REFERENCES\s+[^\s(]+\s*\((.*?)\)', tcon_text, re.IGNORECASE)
                            if fk_cols_match and ref_table_match and ref_cols_match:
                                fk_col_list = [
                                    c.strip() for c in fk_cols_match.group(1).split(',')]
                                ref_table = ref_table_match.group(1)
                                ref_col_list = [
                                    c.strip() for c in ref_cols_match.group(1).split(',')]
                                constraint = {
                                    "type": "FOREIGN_KEY",
                                    "columns": fk_col_list,
                                    "references": {"table": ref_table, "columns": ref_col_list}
                                }
                                if constraint_name:
                                    constraint["name"] = constraint_name
                                table_stmt["constraints"].append(constraint)

                        # CHECK
                        if "CHECK" in tcon_upper:
                            check_expr = re.search(
                                r"CHECK\s*\((.+?)\)", tcon_text, re.IGNORECASE)
                            if check_expr:
                                constraint = {"type": "CHECK", "expression": normalize_sql(
                                    check_expr.group(1).strip())}
                                if constraint_name:
                                    constraint["name"] = constraint_name
                                table_stmt["constraints"].append(constraint)

                        # UNIQUE
                        if "UNIQUE" in tcon_upper:
                            cols = re.findall(r'\((.*?)\)', tcon_text)
                            if cols:
                                col_list = [c.strip()
                                            for c in cols[0].split(',')]
                                constraint = {"type": "UNIQUE",
                                              "columns": col_list}
                                if constraint_name:
                                    constraint["name"] = constraint_name
                                table_stmt["constraints"].append(constraint)

            # ✅ Append to AST safely (respect nesting)
            if self.statement_stack:
                self.statement_stack[-1].append(table_stmt)
            else:
                print(
                    f"⚠️ Table definition found outside procedure: {table_name}")

        except Exception as e:
            print(f"Error parsing CREATE TABLE: {e}")

    def _infer_type_from_schema(self, table_name, column_name):
        # schema_metadata must be preloaded
        schema = self.schema_metadata.get(table_name.lower())
        if schema:
            col_info = schema.get(column_name.lower())
            if col_info:
                return col_info.get("type")  # e.g., "DECIMAL(18,6)"
        return None

    def enterDrop_table(self, ctx):
        try:
            table_name = ctx.table_name(0).getText(
            ) if ctx.table_name(0) else "<UNKNOWN_TABLE>"
            drop_stmt = {"type": "RAW_SQL",
                         "query": f"DROP TABLE {table_name}"}
            self._append_statement(drop_stmt)
        except Exception as e:
            print(f"❌ Error in enterDrop_table: {e}")

    def enterCreate_procedure(self, ctx):
        try:
            # Get procedure name safely
            if ctx.func_proc_name_server_database_schema():
                proc_name = ctx.func_proc_name_server_database_schema().getText()
            elif ctx.procedure_name():
                proc_name = ctx.procedure_name().getText()
            else:
                proc_name = "<UNKNOWN_PROC>"

            self.current_proc = {
                "proc_name": proc_name,
                "params": [],
                "variables": [],
                "return_type": "VOID",
                "statements": []
            }

            # Push to stack
            self.proc_stack.append(self.current_proc)
            self.statement_stack.append(self.current_proc["statements"])

        except Exception as e:
            print(f"❌ Error parsing CREATE PROCEDURE: {e}")

    def exitCreate_procedure(self, ctx):
        try:
            proc_obj = self.proc_stack.pop()
            self.statement_stack.pop()
            self.current_proc = None

            # ✅ Final patch: if any cursor loop still has empty fetch_into, fill it from last_fetch_into
            for cursor_name, info in self.cursor_blocks.items():
                if "fetch_loop" in info:
                    loop = info["fetch_loop"]
                    if not loop.get("fetch_into") or len(loop["fetch_into"]) == 0:
                        if "last_fetch_into" in info:
                            loop["fetch_into"] = info["last_fetch_into"]
                        else:
                            # ✅ Fallback: parse fetch vars from full SQL text if nothing found
                            loop["fetch_into"] = ["<UNKNOWN_VAR>"]

            self.ast.append(proc_obj)

        except Exception as e:
            print(f"❌ Error exiting CREATE PROCEDURE: {e}")

    def enterProcedure_param(self, ctx):
        try:
            if not self.current_proc:
                return

            # Be liberal: LOCAL_ID() is common; fall back to raw text if missing
            name = ctx.LOCAL_ID().getText() if hasattr(
                ctx, "LOCAL_ID") and ctx.LOCAL_ID() else None
            if not name:
                # Fallback: grab first '@...' token from the text span
                raw = ctx.start.getInputStream().getText(ctx.start.start, ctx.stop.stop)
                m = re.search(r"@\w+", raw)
                name = m.group(0) if m else "<UNKNOWN_PARAM>"

            # Data type (keep full precision/length)
            dtype = ctx.data_type().getText().upper() if hasattr(
                ctx, "data_type") and ctx.data_type() else "SQL_VARIANT"

            mode = "IN"
            if hasattr(ctx, "output_clause") and ctx.output_clause():
                mode = "OUT"

            self.current_proc["params"].append({
                "name": name,
                "type": dtype,
                "mode": mode
            })

        except Exception as e:
            print(f"❌ Error in enterProcedure_param: {e}")

    def enterDeclareVariable(self, ctx):
        try:
            if not self.current_proc:
                # Outside proc → ignore silently to avoid noise
                # (Tool 5 expects variables under the procedure)
                return

            # Name
            if hasattr(ctx, "IDENTIFIER") and ctx.IDENTIFIER():
                var_name = ctx.IDENTIFIER().getText()
            elif hasattr(ctx, "LOCAL_ID") and ctx.LOCAL_ID():
                var_name = ctx.LOCAL_ID().getText()
            else:
                # Fallback from raw text
                raw = ctx.start.getInputStream().getText(ctx.start.start, ctx.stop.stop)
                m = re.search(r"@\w+", raw)
                var_name = m.group(0) if m else "<UNKNOWN_VAR>"

            # Type
            data_type = ctx.data_type().getText().strip() if hasattr(
                ctx, "data_type") and ctx.data_type() else "SQL_VARIANT"

            # Default value
            default_value = None
            if hasattr(ctx, "constant") and ctx.constant():
                default_value = ctx.constant().getText()
            elif hasattr(ctx, "expression") and ctx.expression():
                default_value = ctx.getChild(ctx.getChildCount() - 1).getText()

            var_obj = {"name": var_name, "type": data_type}
            if default_value:
                var_obj["default"] = default_value

            self.current_proc["variables"].append(var_obj)

        except Exception as e:
            print(f"❌ Error in enterDeclareVariable: {e}")
