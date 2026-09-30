-- Migration 001: Add index on orders(customer_id)
-- Optimizes customer order lookup from Parallel Seq Scan to Index Scan
CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);
