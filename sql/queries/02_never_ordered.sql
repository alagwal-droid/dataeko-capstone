-- Answer:
-- 3 drinks have never been ordered:
-- 1. affogato
-- 2. rose cardamom
-- 3. turmeric latte

SELECT d.name
FROM drinks d
LEFT JOIN orders o ON d.id = o.drink_id
WHERE o.id IS NULL
ORDER BY d.name;
