import json
from antlr4 import *
from TSqlLexer import TSqlLexer
from TSqlParser import TSqlParser
from ast_listener import ASTBuilder  # Make sure this is the correct class name

# Helper to pretty-print SQL from ctx


def get_clean_query(ctx):
    try:
        tokens = ctx.start.getInputStream().getText(ctx.start.start, ctx.stop.stop)
        return " ".join(tokens.replace("\n", " ").split())
    except Exception as e:
        print("Error cleaning query:", e)
        return ""


input_file = "input/08_sp_ProcessFullPayrollCycle.sql"

# Load SQL from file
input_stream = FileStream(input_file, encoding="utf-8")

# Lexer and Parser
lexer = TSqlLexer(input_stream)
stream = CommonTokenStream(lexer)
parser = TSqlParser(stream)

tree = parser.tsql_file()        # Use if SQL contains full batch
# tree = parser.sql_clauses()      # Use if SQL has only one procedure
# tree = parser.batch()             # Most reliable for Sybase procedures

# === Walk the Parse Tree ===
listener = ASTBuilder()
walker = ParseTreeWalker()
walker.walk(listener, tree)

# === Dump AST to JSON ===
output_path = r"C:\Users\SreeHariP\OneDrive - McLaren Strategic Solutions US Inc\Documents\tool2_parser\output\ast_08_sp_ProcessFullPayrollCycle.json"

with open(output_path, "w") as f:
    json.dump(listener.ast, f, indent=2)

print(f"\n✅ AST generated and saved to: {output_path}")
