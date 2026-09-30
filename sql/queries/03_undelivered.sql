-- Answer:
-- 80,000 orders have no delivery record in the deliveries table (exactly 20% of orders).

SELECT COUNT(*) AS undelivered_orders
FROM orders o
LEFT JOIN deliveries d ON o.id = d.order_id
WHERE d.id IS NULL;
