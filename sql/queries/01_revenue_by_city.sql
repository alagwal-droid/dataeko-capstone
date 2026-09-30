-- Answer:
-- Total collected revenue per city:
-- Bengaluru: 15,600,780 INR
-- Hyderabad: 15,599,610 INR
-- Pune:       9,333,560 INR
-- Chennai:    9,333,100 INR
-- Delhi:      4,666,810 INR
-- Mumbai:     4,666,550 INR

SELECT s.city, SUM(o.qty * d.price_inr) AS revenue
FROM orders o
JOIN stores s ON o.store_id = s.id
JOIN drinks d ON o.drink_id = d.id
WHERE o.status = 'collected'
GROUP BY s.city
ORDER BY revenue DESC;
