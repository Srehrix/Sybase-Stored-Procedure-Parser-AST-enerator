import json
import sys
from jsonschema import Draft7Validator, ValidationError
from pathlib import Path

def loadjson(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"File not found: {filepath}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"JSON parsing error in {filepath}: {e}")
        sys.exit(1)

def validate_ast(astpath, schemapath):
    astarray = loadjson(astpath)
    schema = loadjson(schemapath)

    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(astarray), key=lambda e: e.path)
    if errors:
        print("\nValidation errors in AST:")
        for err in errors:
            print(f"  - Error: {err.message}")
            print(f"    Path : {' -> '.join(str(p) for p in err.path)}")
        print("\nOne or more procedures failed schema validation.")
        sys.exit(1)
    else:
        print("\nAll procedures are valid according to schema.")

if __name__ == "__main__":
    astfile = sys.argv[1] if len(sys.argv) > 1 else "../output_data/ast.json"
    schemafile = sys.argv[2] if len(sys.argv) > 2 else "../Tool2/fixedSchema/fixedSchema.json"

    print(f"Validating AST: {astfile}")
    print(f"Using Schema : {schemafile}\n")

    validate_ast(astfile, schemafile)


