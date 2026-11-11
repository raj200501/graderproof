# SQLite schema for the orders service

Write `schema.sql` in the working directory: a SQLite script that, run on an empty database, creates exactly the following.

- Table `customers` with columns, in this order: `id INTEGER PRIMARY KEY`, `email TEXT NOT NULL UNIQUE`, `created_at TEXT NOT NULL`.
- Table `orders` with columns, in this order: `id INTEGER PRIMARY KEY`, `customer_id INTEGER NOT NULL` with a foreign key referencing `customers(id)`, `total_cents INTEGER NOT NULL`, `status TEXT NOT NULL DEFAULT 'pending'`.
- An index named `idx_orders_customer` on `orders(customer_id)`.

The script must run without errors and must not create any other table, view, index, or trigger (the automatic index SQLite creates for a `UNIQUE` column does not count).
