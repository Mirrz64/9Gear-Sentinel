-- Demo data with deliberate problems, so a first `sentinel run` shows passes and failures.
-- Timestamps are relative to when the container was first created.

CREATE SCHEMA IF NOT EXISTS analytics;

-- customers: healthy table, every check should pass
CREATE TABLE analytics.customers (
    id          integer PRIMARY KEY,
    email       text NOT NULL,
    country     text,
    created_at  timestamptz NOT NULL
);

INSERT INTO analytics.customers (id, email, country, created_at)
SELECT
    g,
    'customer' || g || '@example.com',
    (ARRAY['GB', 'NG', 'CA', 'US'])[1 + (g % 4)],
    now() - (g || ' minutes')::interval
FROM generate_series(1, 200) AS g;

-- orders: stale, has null customer_ids and duplicate order_ids
CREATE TABLE analytics.orders (
    order_id     integer,
    customer_id  integer,
    status       text,
    amount       numeric(10, 2),
    updated_at   timestamptz
);

INSERT INTO analytics.orders (order_id, customer_id, status, amount, updated_at)
SELECT
    g,
    CASE WHEN g % 40 = 0 THEN NULL ELSE 1 + (g % 200) END,
    (ARRAY['pending', 'paid', 'shipped', 'refunded'])[1 + (g % 4)],
    round((5 + random() * 195)::numeric, 2),
    now() - interval '3 days' - (g || ' minutes')::interval
FROM generate_series(1, 1000) AS g;

-- three duplicated order_ids
INSERT INTO analytics.orders (order_id, customer_id, status, amount, updated_at)
SELECT order_id, customer_id, status, amount, updated_at
FROM analytics.orders
WHERE order_id IN (10, 20, 30);
