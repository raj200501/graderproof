#!/usr/bin/env bash
set -euo pipefail
cat > schema.sql <<'EOF'
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    total_cents INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
);

CREATE INDEX idx_orders_customer ON orders(customer_id);
EOF
