# db.py
import mysql.connector
from mysql.connector import pooling
import logging
from config import Config

logger = logging.getLogger(__name__)

_pool = None

def get_pool():
    global _pool
    if _pool is None:
       _pool = pooling.MySQLConnectionPool(
    pool_name="invoice_pool",
    pool_size=5,
    host=Config.MARIADB_HOST,
    port=3306,  # or Config.MARIADB_PORT if you add it
    user=Config.MARIADB_USER,
    password=Config.MARIADB_PASSWORD,
    database=Config.MARIADB_DATABASE,
    charset="utf8mb4"
)

    return _pool

def get_connection():
    return get_pool().get_connection()

def save_invoice(data: dict, filename: str) -> int:
    """Insert invoice header and items into DB. Returns invoice id."""
    import json
    conn = get_connection()
    cursor = conn.cursor()
    try:
        invoice_sql = """
            INSERT INTO invoices (
                filename, invoice_no, invoice_date, supplier_name,
                customer_name, grand_total, raw_extracted_json, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        raw_json = json.dumps(data, ensure_ascii=False)
        cursor.execute(invoice_sql, (
            filename,
            data.get("invoice_no"),
            data.get("invoice_date"),
            data.get("supplier_name"),
            data.get("customer_name"),
            data.get("grand_total"),
            raw_json,
            "processed"
        ))
        invoice_id = cursor.lastrowid

        # Insert items if present
        items = data.get("items", [])
        if items:
            item_sql = """
                INSERT INTO invoice_items (
                    invoice_id, sl_no, description, hsn_sac_code,
                    quantity, unit_price, total_amount
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            for item in items:
                cursor.execute(item_sql, (
                    invoice_id,
                    item.get("sl_no"),
                    item.get("description"),
                    item.get("hsn_sac_code"),
                    item.get("quantity"),
                    item.get("unit_price"),
                    item.get("total_amount"),
                ))

        conn.commit()
        logger.info(f"Saved invoice id={invoice_id}")
        return invoice_id
    except Exception as e:
        conn.rollback()
        logger.error(f"DB error saving invoice: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def mark_invoice_failed(filename: str, error: str):
    """Record a failed invoice in DB for retry later."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO invoices (filename, status, error_message) VALUES (%s, 'failed', %s)",
            (filename, str(error)[:1000])
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()
