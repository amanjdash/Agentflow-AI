"""Generates realistic sample data for AgentFlow's semiconductor & hardware business database."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional

from app.database.connection import get_default_db_path
from app.database.schema import SCHEMA_DDL
from app.services.logging import get_logger

logger = get_logger("agentflow.database.seed")


CUSTOMERS_DATA = [
    ("Apex Robotics Inc.", "procurement@apexrobotics.io", "North America", "Enterprise", "2025-01-15"),
    ("NeuralVision Labs", "tech@neuralvision.de", "Europe", "Mid-Market", "2025-02-10"),
    ("Tokyo Automated Systems", "hardware@tokyoauto.co.jp", "Asia Pacific", "Enterprise", "2025-02-20"),
    ("Solaria Smart Grids", "supply@solariagrids.com", "North America", "Enterprise", "2025-03-05"),
    ("Andes Sensor Tech", "compras@andessensor.cl", "Latin America", "Small Business", "2025-03-22"),
    ("Nordic Autonomous Vehicles", "fleet@nordicauto.se", "Europe", "Enterprise", "2025-04-12"),
    ("SingaDrone Aerospace", "operations@singadrone.sg", "Asia Pacific", "Mid-Market", "2025-05-01"),
    ("BioCompute Systems", "admin@biocompute.com", "North America", "Mid-Market", "2025-06-18"),
    ("Helios IoT Solutions", "iot@helios-iot.gr", "Europe", "Small Business", "2025-07-09"),
    ("Kyoto Quantum Devices", "rd@kyotoquantum.ac.jp", "Asia Pacific", "Enterprise", "2025-08-14"),
    ("São Paulo Embedded Tech", "dev@spembedded.com.br", "Latin America", "Mid-Market", "2025-09-03"),
    ("Sierra Edge Analytics", "orders@sierraedge.ai", "North America", "Small Business", "2025-10-25"),
]

PRODUCTS_DATA = [
    ("SKU-SEMI-001", "Titan AI Tensor Core Accelerator 32GB", "Semiconductor", 1450.00, 820.00, 45),
    ("SKU-SEMI-002", "RTX Embedded Neural Core 16GB", "Semiconductor", 890.00, 490.00, 80),
    ("SKU-COMP-003", "Quantum Edge TPU 8W", "Compute Module", 340.00, 180.00, 150),
    ("SKU-COMP-004", "Silicon RISC-V SoC 2.4GHz Octa-Core", "Compute Module", 220.00, 110.00, 200),
    ("SKU-SENS-005", "HyperDepth LiDAR Photonic Sensor", "Sensor", 560.00, 290.00, 65),
    ("SKU-SENS-006", "MEMS Ultra-Precision IMU Array", "Sensor", 125.00, 55.00, 320),
    ("SKU-EMBD-007", "NeuroDSP Ultra-Low Power MCU", "Embedded AI", 45.00, 18.00, 500),
    ("SKU-EMBD-008", "EdgeVision Smart Camera Core", "Embedded AI", 410.00, 215.00, 95),
    ("SKU-SEMI-009", "Photonic Opto-Coupled Interconnect", "Semiconductor", 780.00, 410.00, 60),
    ("SKU-COMP-010", "Ruggedized Industrial Edge Gateway", "Compute Module", 1250.00, 680.00, 40),
]

# (customer_id, order_date, status, total_amount, discount_amount, items: [(product_id, qty, unit_price)])
ORDERS_SPEC = [
    # 2025-10 Orders
    (1, "2025-10-05", "Completed", 14500.0, 500.0, [(1, 10, 1450.0)]),
    (2, "2025-10-12", "Completed", 4450.0, 0.0, [(2, 5, 890.0)]),
    (3, "2025-10-19", "Completed", 6800.0, 200.0, [(3, 20, 340.0)]),
    (4, "2025-10-28", "Completed", 11200.0, 0.0, [(4, 20, 220.0), (3, 20, 340.0)]),
    
    # 2025-11 Orders
    (5, "2025-11-04", "Completed", 3750.0, 100.0, [(6, 30, 125.0)]),
    (6, "2025-11-10", "Completed", 21750.0, 1000.0, [(1, 15, 1450.0)]),
    (7, "2025-11-18", "Completed", 8200.0, 0.0, [(8, 20, 410.0)]),
    (8, "2025-11-25", "Completed", 14240.0, 300.0, [(2, 16, 890.0)]),
    
    # 2025-12 Orders
    (1, "2025-12-02", "Completed", 29000.0, 1200.0, [(1, 20, 1450.0)]),
    (3, "2025-12-09", "Completed", 15600.0, 400.0, [(9, 20, 780.0)]),
    (9, "2025-12-15", "Completed", 4500.0, 0.0, [(7, 100, 45.0)]),
    (10, "2025-12-22", "Completed", 17400.0, 600.0, [(2, 10, 890.0), (1, 6, 1450.0)]),
    
    # 2026-01 Orders
    (2, "2026-01-08", "Completed", 12500.0, 500.0, [(10, 10, 1250.0)]),
    (4, "2026-01-14", "Completed", 16800.0, 0.0, [(5, 30, 560.0)]),
    (6, "2026-01-20", "Completed", 26100.0, 1000.0, [(1, 18, 1450.0)]),
    (11, "2026-01-27", "Completed", 8900.0, 200.0, [(2, 10, 890.0)]),
    
    # 2026-02 Orders
    (7, "2026-02-03", "Completed", 10250.0, 250.0, [(8, 25, 410.0)]),
    (12, "2026-02-11", "Completed", 6800.0, 0.0, [(3, 20, 340.0)]),
    (1, "2026-02-17", "Completed", 31900.0, 1500.0, [(1, 22, 1450.0)]),
    (3, "2026-02-24", "Completed", 19500.0, 500.0, [(9, 25, 780.0)]),
    
    # 2026-03 Orders
    (8, "2026-03-02", "Completed", 13350.0, 350.0, [(2, 15, 890.0)]),
    (5, "2026-03-08", "Completed", 5600.0, 0.0, [(5, 10, 560.0)]),
    (10, "2026-03-12", "Completed", 21750.0, 750.0, [(1, 15, 1450.0)]),
    (6, "2026-03-15", "Completed", 25000.0, 1000.0, [(10, 20, 1250.0)]),
]

CHANNELS = ["Direct Sales", "Online Enterprise", "Partner OEM"]


def seed_database(db_path: Optional[Path | str] = None) -> Path:
    """Initializes and seeds the database with realistic business records."""
    target_path = Path(db_path).resolve() if db_path else get_default_db_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # If the database file exists, remove to reseed cleanly
    if target_path.exists():
        target_path.unlink()

    # Open standard writable connection for seeding
    conn = sqlite3.connect(str(target_path))
    cursor = conn.cursor()

    try:
        # 1. Execute DDL
        cursor.executescript(SCHEMA_DDL)

        # 2. Insert Customers
        cursor.executemany(
            """INSERT INTO customers (name, email, region, segment, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            CUSTOMERS_DATA,
        )

        # 3. Insert Products
        cursor.executemany(
            """INSERT INTO products (sku, name, category, unit_price, cost_price, stock_quantity)
               VALUES (?, ?, ?, ?, ?, ?)""",
            PRODUCTS_DATA,
        )

        # Query back customers to get their regions for the sales table
        cursor.execute("SELECT id, region FROM customers")
        customer_regions = dict(cursor.fetchall())

        # Query back products to compute cost of goods sold
        cursor.execute("SELECT id, cost_price FROM products")
        product_costs = dict(cursor.fetchall())

        # 4. Insert Orders, Order Items, and Sales records
        for i, order in enumerate(ORDERS_SPEC, start=1):
            cust_id, order_date, status, total_amt, discount, items = order
            cursor.execute(
                """INSERT INTO orders (customer_id, order_date, status, total_amount, discount_amount)
                   VALUES (?, ?, ?, ?, ?)""",
                (cust_id, order_date, status, total_amt, discount),
            )
            order_id = cursor.lastrowid

            total_cogs = 0.0
            for prod_id, qty, unit_price in items:
                subtotal = qty * unit_price
                cursor.execute(
                    """INSERT INTO order_items (order_id, product_id, quantity, unit_price, subtotal)
                       VALUES (?, ?, ?, ?, ?)""",
                    (order_id, prod_id, qty, unit_price, subtotal),
                )
                total_cogs += qty * product_costs.get(prod_id, 0.0)

            # Insert corresponding Sales ledger entry
            channel = CHANNELS[i % len(CHANNELS)]
            gross = total_amt + discount
            net = total_amt
            margin = round(net - total_cogs, 2)
            region = customer_regions.get(cust_id, "North America")

            cursor.execute(
                """INSERT INTO sales (order_id, sale_date, channel, gross_revenue, net_revenue, margin, region)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (order_id, order_date, channel, gross, net, margin, region),
            )

        conn.commit()
        logger.info(f"Successfully seeded database at {target_path} with {len(ORDERS_SPEC)} orders.")
        return target_path

    finally:
        conn.close()
