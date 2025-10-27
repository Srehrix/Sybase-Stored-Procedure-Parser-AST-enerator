import subprocess
import os
import json
from pathlib import Path


# Commands: run local parser and validator 
commands = [
    ["python", "parser.py"],
    ["python", "validator.py", "output_data/ast.json", "fixedSchema/fixedschema.json"],
]


def run_commands():
    for cmd in commands:
        print(f"\n⚡ Running: {' '.join(cmd)} (cwd={os.getcwd()})")
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError:
            print(f"❌ Failed: {' '.join(cmd)}")
            break


if __name__ == "__main__":
    run_commands()
