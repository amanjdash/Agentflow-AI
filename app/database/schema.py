"""Database schema definitions and metadata documentation for the agent."""

from __future__ import annotations

SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    region TEXT NOT NULL,         -- 'North America', 'Europe', 'Asia Pacific', 'Latin America'
    segment TEXT NOT NULL,        -- 'Enterprise', 'Mid-Market', 'Small Business'
    created_at TEXT NOT NULL      -- ISO-8601 string 'YYYY-MM-DD'
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,       -- 'Semiconductor', 'Compute Module', 'Sensor', 'Embedded AI'
    unit_price REAL NOT NULL,     -- Selling price in USD
    cost_price REAL NOT NULL,     -- Manufacturing cost in USD
    stock_quantity INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    order_date TEXT NOT NULL,     -- 'YYYY-MM-DD'
    status TEXT NOT NULL,         -- 'Completed', 'Shipped', 'Processing'
    total_amount REAL NOT NULL,   -- Net total order price in USD
    discount_amount REAL DEFAULT 0.0,
    FOREIGN KEY(customer_id) REFERENCES customers(id)
);

CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    subtotal REAL NOT NULL,
    FOREIGN KEY(order_id) REFERENCES orders(id),
    FOREIGN KEY(product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    sale_date TEXT NOT NULL,      -- 'YYYY-MM-DD'
    channel TEXT NOT NULL,        -- 'Direct Sales', 'Online Enterprise', 'Partner OEM'
    gross_revenue REAL NOT NULL,
    net_revenue REAL NOT NULL,
    margin REAL NOT NULL,
    region TEXT NOT NULL,
    FOREIGN KEY(order_id) REFERENCES orders(id)
);
"""

SCHEMA_SUMMARY = """
### Database Schema (SQLite)

1. **customers**
   - `id` (INTEGER, PK): Unique customer identifier
   - `name` (TEXT): Customer or company name
   - `email` (TEXT): Primary contact email
   - `region` (TEXT): Geographic region ('North America', 'Europe', 'Asia Pacific', 'Latin America')
   - `segment` (TEXT): Market segment ('Enterprise', 'Mid-Market', 'Small Business')
   - `created_at` (TEXT): Registration date (YYYY-MM-DD)

2. **products**
   - `id` (INTEGER, PK): Unique product identifier
   - `sku` (TEXT): Product SKU code
   - `name` (TEXT): Product title (e.g. 'Nvidia TensorCore Accelerator', 'RTX Embedded Neural Core')
   - `category` (TEXT): 'Semiconductor', 'Compute Module', 'Sensor', 'Embedded AI'
   - `unit_price` (REAL): Catalog selling price in USD
   - `cost_price` (REAL): Unit manufacturing cost
   - `stock_quantity` (INTEGER): Units in stock

3. **orders**
   - `id` (INTEGER, PK): Unique order ID
   - `customer_id` (INTEGER, FK -> customers.id)
   - `order_date` (TEXT): Date order was placed (YYYY-MM-DD)
   - `status` (TEXT): Order status ('Completed', 'Shipped', 'Processing')
   - `total_amount` (REAL): Total order revenue in USD
   - `discount_amount` (REAL): Applied discount amount

4. **order_items**
   - `id` (INTEGER, PK): Unique line item ID
   - `order_id` (INTEGER, FK -> orders.id)
   - `product_id` (INTEGER, FK -> products.id)
   - `quantity` (INTEGER): Number of units purchased
   - `unit_price` (REAL): Price per unit in USD
   - `subtotal` (REAL): Line total (`quantity * unit_price`)

5. **sales**
   - `id` (INTEGER, PK): Sales ledger transaction ID
   - `order_id` (INTEGER, FK -> orders.id)
   - `sale_date` (TEXT): Date of recorded sale (YYYY-MM-DD)
   - `channel` (TEXT): Channel ('Direct Sales', 'Online Enterprise', 'Partner OEM')
   - `gross_revenue` (REAL): Gross transaction revenue in USD
   - `net_revenue` (REAL): Net revenue after discounts
   - `margin` (REAL): Profit margin (`net_revenue - costs`)
   - `region` (TEXT): Sales region
"""


def get_schema_description() -> str:
    """Returns a structured, human-readable description of all tables, columns, and relations."""
    return SCHEMA_SUMMARY.strip()
