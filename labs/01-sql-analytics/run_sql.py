"""Run a SQL file against the lab database and print every result.

Usage:
    python run_sql.py setup.sql          # create the database and views (run once)
    python run_sql.py exercises.sql      # run your answers
    python run_sql.py solutions.sql      # compare with the reference solutions
"""
import os
import sys
from pathlib import Path

import duckdb

LAB_DIR = Path(__file__).resolve().parent


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    os.chdir(LAB_DIR)                                    # paths in the SQL files are relative to the lab
    sql_path = Path(sys.argv[1])
    con = duckdb.connect("lab.duckdb")
    for statement in [s.strip() for s in sql_path.read_text().split(";") if s.strip()]:
        header = next((line for line in statement.splitlines() if line.startswith("-- Q")), None)
        if header:
            print(f"\n{header}")
        body = "\n".join(l for l in statement.splitlines() if not l.strip().startswith("--")).strip()
        if not body:
            continue
        result = con.sql(body)
        if result is not None:
            result.show(max_rows=15)


if __name__ == "__main__":
    main()
