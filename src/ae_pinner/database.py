"""MySQL database layer for persisting AliExpress products and Pinterest content."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import mysql.connector
from mysql.connector import pooling

from ae_pinner.ai_generator import PinContent
from ae_pinner.aliexpress import Product


@dataclass
class DBProduct:
    """A product row from the database."""

    id: int
    item_id: str
    main_item_id: str
    title: str
    image_url: str
    all_images: str
    original_price: str
    discount_price: str
    discount_rate: str
    sales_30day: int
    comment_score: str
    commission_rate: str
    item_url: str
    promo_url: str
    raw_json: str
    promo_response: str
    pin_title: str
    pin_description: str
    pin_alt_text: str
    pin_generated: bool
    created_at: datetime
    updated_at: datetime


_CREATE_SETTINGS_TABLE = """
CREATE TABLE IF NOT EXISTS settings (
    setting_key   VARCHAR(128)  NOT NULL PRIMARY KEY,
    setting_value LONGTEXT      NOT NULL,
    updated_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

_CREATE_PRODUCTS_TABLE = """
CREATE TABLE IF NOT EXISTS products (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    item_id         VARCHAR(64)  NOT NULL UNIQUE,
    main_item_id    VARCHAR(64)  NOT NULL DEFAULT '',
    title           VARCHAR(1000) NOT NULL,
    image_url       VARCHAR(2000) NOT NULL DEFAULT '',
    all_images      MEDIUMTEXT   NOT NULL,
    original_price  VARCHAR(32)  NOT NULL DEFAULT '',
    discount_price  VARCHAR(32)  NOT NULL DEFAULT '',
    discount_rate   VARCHAR(16)  NOT NULL DEFAULT '',
    sales_30day     INT          NOT NULL DEFAULT 0,
    comment_score   VARCHAR(16)  NOT NULL DEFAULT '',
    commission_rate VARCHAR(16)  NOT NULL DEFAULT '',
    item_url        VARCHAR(2000) NOT NULL DEFAULT '',
    promo_url       VARCHAR(2000) NOT NULL DEFAULT '',
    raw_json        LONGTEXT     NOT NULL,
    promo_response  LONGTEXT     NOT NULL,
    pin_title       VARCHAR(500) NOT NULL DEFAULT '',
    pin_description VARCHAR(2000) NOT NULL DEFAULT '',
    pin_alt_text    VARCHAR(1000) NOT NULL DEFAULT '',
    pin_generated   BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                 ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""


class Database:
    """MySQL database manager with connection pooling."""

    def __init__(self, host: str, port: int, name: str, user: str, password: str):
        self._pool = pooling.MySQLConnectionPool(
            pool_name="ae_pinner_pool",
            pool_size=5,
            host=host,
            port=port,
            database=name,
            user=user,
            password=password,
            charset="utf8mb4",
            collation="utf8mb4_unicode_ci",
            autocommit=True,
        )

    def _conn(self) -> pooling.PooledMySQLConnection:
        return self._pool.get_connection()

    def init_tables(self) -> None:
        """Create all required tables if they don't exist."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute(_CREATE_SETTINGS_TABLE)
            cur.execute(_CREATE_PRODUCTS_TABLE)
            self._migrate_add_columns(cur)
            cur.close()
        finally:
            conn.close()

    @staticmethod
    def _migrate_add_columns(cur) -> None:
        """Add columns introduced after initial schema."""
        for col, col_def in (
            ("raw_json", "LONGTEXT NOT NULL DEFAULT ''"),
            ("promo_response", "LONGTEXT NOT NULL DEFAULT ''"),
        ):
            try:
                cur.execute(f"ALTER TABLE products ADD COLUMN {col} {col_def}")
            except Exception:
                pass

    def get_setting(self, key: str) -> str:
        """Get a setting value by key. Returns empty string if not found."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT setting_value FROM settings WHERE setting_key = %s", (key,))
            row = cur.fetchone()
            cur.close()
            return row[0] if row else ""
        finally:
            conn.close()

    def set_setting(self, key: str, value: str) -> None:
        """Upsert a setting value."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO settings (setting_key, setting_value)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)
                """,
                (key, value),
            )
            cur.close()
        finally:
            conn.close()

    def product_exists(self, item_id: str) -> bool:
        """Check if a product with this item_id already exists."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM products WHERE item_id = %s LIMIT 1", (item_id,))
            row = cur.fetchone()
            cur.close()
            return row is not None
        finally:
            conn.close()

    def save_product(self, product: Product, pin_content: PinContent | None = None) -> bool:
        """Insert a product into the database. Returns False if duplicate."""
        if self.product_exists(product.item_id):
            return False

        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO products
                    (item_id, main_item_id, title, image_url, all_images,
                     original_price, discount_price, discount_rate,
                     sales_30day, comment_score, commission_rate,
                     item_url, promo_url, raw_json, promo_response,
                     pin_title, pin_description, pin_alt_text, pin_generated)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    product.item_id,
                    product.main_item_id,
                    product.title,
                    product.image_url,
                    ",".join(product.all_images),
                    product.original_price,
                    product.discount_price,
                    product.discount_rate,
                    product.sales_30day,
                    product.comment_score,
                    product.commission_rate,
                    product.item_url,
                    product.promo_url or "",
                    product.raw_json,
                    product.promo_response,
                    pin_content.title if pin_content else "",
                    pin_content.description if pin_content else "",
                    pin_content.alt_text if pin_content else "",
                    pin_content is not None,
                ),
            )
            cur.close()
            return True
        except mysql.connector.IntegrityError:
            return False
        finally:
            conn.close()

    def update_pin_content(self, item_id: str, pin_content: PinContent) -> bool:
        """Update the Pinterest content for an existing product."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE products
                SET pin_title = %s, pin_description = %s, pin_alt_text = %s, pin_generated = TRUE
                WHERE item_id = %s
                """,
                (pin_content.title, pin_content.description, pin_content.alt_text, item_id),
            )
            affected = cur.rowcount
            cur.close()
            return affected > 0
        finally:
            conn.close()

    def get_all_products(self, page: int = 1, per_page: int = 20) -> tuple[list[DBProduct], int]:
        """Get paginated products. Returns (products, total_count)."""
        conn = self._conn()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT COUNT(*) AS cnt FROM products")
            total = cur.fetchone()["cnt"]

            offset = (page - 1) * per_page
            cur.execute(
                "SELECT * FROM products ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (per_page, offset),
            )
            rows = cur.fetchall()
            cur.close()

            products = [self._row_to_dbproduct(r) for r in rows]
            return products, total
        finally:
            conn.close()

    def get_product_by_item_id(self, item_id: str) -> DBProduct | None:
        """Get a single product by its AliExpress item_id."""
        conn = self._conn()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM products WHERE item_id = %s", (item_id,))
            row = cur.fetchone()
            cur.close()
            return self._row_to_dbproduct(row) if row else None
        finally:
            conn.close()

    def get_products_without_pins(self) -> list[DBProduct]:
        """Get all products that don't have Pinterest content generated yet."""
        conn = self._conn()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT * FROM products WHERE pin_generated = FALSE ORDER BY created_at DESC"
            )
            rows = cur.fetchall()
            cur.close()
            return [self._row_to_dbproduct(r) for r in rows]
        finally:
            conn.close()

    def get_stats(self) -> dict[str, int]:
        """Get database statistics."""
        conn = self._conn()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(pin_generated) AS with_pins,
                    COUNT(*) - SUM(pin_generated) AS without_pins
                FROM products
                """
            )
            row = cur.fetchone()
            cur.close()
            return {
                "total": row["total"] or 0,
                "with_pins": int(row["with_pins"] or 0),
                "without_pins": int(row["without_pins"] or 0),
            }
        finally:
            conn.close()

    def delete_product(self, item_id: str) -> bool:
        """Delete a product by item_id."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM products WHERE item_id = %s", (item_id,))
            affected = cur.rowcount
            cur.close()
            return affected > 0
        finally:
            conn.close()

    @staticmethod
    def _row_to_dbproduct(row: dict) -> DBProduct:
        return DBProduct(
            id=row["id"],
            item_id=row["item_id"],
            main_item_id=row["main_item_id"],
            title=row["title"],
            image_url=row["image_url"],
            all_images=row["all_images"],
            original_price=row["original_price"],
            discount_price=row["discount_price"],
            discount_rate=row["discount_rate"],
            sales_30day=row["sales_30day"],
            comment_score=row["comment_score"],
            commission_rate=row["commission_rate"],
            item_url=row["item_url"],
            promo_url=row["promo_url"],
            raw_json=row.get("raw_json", ""),
            promo_response=row.get("promo_response", ""),
            pin_title=row["pin_title"],
            pin_description=row["pin_description"],
            pin_alt_text=row["pin_alt_text"],
            pin_generated=bool(row["pin_generated"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
