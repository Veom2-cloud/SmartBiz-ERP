# scripts/delete_all_sales.py
"""
Delete sale invoices from MariaDB using env vars (MARIADB_USER, MARIADB_PASSWORD, MARIADB_HOST, MARIADB_DATABASE).
Usage:
  python scripts/delete_all_sales.py         # interactive: choose all or single id
  python scripts/delete_all_sales.py all     # delete all invoices
  python scripts/delete_all_sales.py id 123  # delete invoice with id 123
"""

import os
import sys
from dotenv import load_dotenv
import pymysql

# Ensure project root is on sys.path if you run script from subfolders
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

load_dotenv()  # loads .env in project root if present

DB_USER = os.getenv("MARIADB_USER")
DB_PASS = os.getenv("MARIADB_PASSWORD")
DB_HOST = os.getenv("MARIADB_HOST", "127.0.0.1")
DB_NAME = os.getenv("MARIADB_DATABASE")

def confirm(prompt):
    ans = input(prompt + " Type YES to continue: ")
    return ans == "YES"

def connect():
    if not DB_USER or not DB_NAME:
        print("Missing DB credentials. Check .env or environment variables for MARIADB_USER and MARIADB_DATABASE.")
        sys.exit(1)
    try:
        conn = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASS or "",
            database=DB_NAME,
            autocommit=False,
            cursorclass=pymysql.cursors.DictCursor,
        )
        return conn
    except Exception as e:
        print("Could not connect to database:", e)
        sys.exit(1)

def delete_all(conn):
    print("About to DELETE ALL rows from sale_item and sale_invoice in database:", DB_NAME)
    if not confirm("This will permanently delete ALL sale invoices and sale items."):
        print("Aborted.")
        return
    try:
        with conn.cursor() as cur:
            # delete child rows first to respect FK constraints
            cur.execute("DELETE FROM sale_item;")
            cur.execute("DELETE FROM sale_invoice;")
        conn.commit()
        print("Deleted all sale_item and sale_invoice.")
    except Exception as e:
        conn.rollback()
        print("Error during deletion:", e)

def delete_one(conn, sale_id):
    print(f"About to DELETE sale invoice id={sale_id} and its sale_items in database: {DB_NAME}")
    if not confirm(f"This will permanently delete invoice id={sale_id}."):
        print("Aborted.")
        return
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sale_item WHERE sale_id = %s;", (sale_id,))
            cur.execute("DELETE FROM sale_invoice WHERE id = %s;", (sale_id,))
        conn.commit()
        print(f"Deleted invoice id={sale_id} (and related items).")
    except Exception as e:
        conn.rollback()
        print("Error during deletion:", e)


def main():
    args = sys.argv[1:]
    conn = connect()
    try:
        if not args:
            print("No arguments provided. Choose an action:")
            print("  1) Delete all invoices")
            print("  2) Delete a single invoice by id")
            choice = input("Enter 1 or 2: ").strip()
            if choice == "1":
                delete_all(conn)
            elif choice == "2":
                sid = input("Enter sale invoice id to delete: ").strip()
                if sid.isdigit():
                    delete_one(conn, int(sid))
                else:
                    print("Invalid id.")
            else:
                print("Nothing done.")
        elif args[0].lower() == "all":
            delete_all(conn)
        elif args[0].lower() == "id" and len(args) > 1 and args[1].isdigit():
            delete_one(conn, int(args[1]))
        elif args[0].isdigit():
            delete_one(conn, int(args[0]))
        else:
            print("Unknown arguments. Usage examples:")
            print("  python scripts/delete_all_sales.py all")
            print("  python scripts/delete_all_sales.py id 123")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
