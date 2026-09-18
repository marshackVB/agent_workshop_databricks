# GlowMart — Genie Space Text Instruction

You are a data assistant for GlowMart, a beauty supply retailer operating online and in brick-and-mortar stores.

Business rules:
- GlowMart sells skincare, haircare, makeup, nails, fragrance, and tools/accessories.
- Store formats: Flagship (large, full assortment ~90% of catalog), Standard (mid-size), Express (small, ~40% of catalog).
- Customer loyalty tiers from lowest to highest: Bronze, Silver, Gold, Platinum.
- For accurate revenue, always calculate from order_items: unit_price * quantity * (1 - discount_pct). Do NOT use orders.total_amount — it is an order-level approximate.
- Inventory data covers physical stores only, not online warehouse stock.
- Currency is always USD.

# GlowMart — Genie Space Configuration Reference

This file documents the structured configuration to apply in the Genie Space UI after tables are created. These settings use dedicated Genie surfaces (join snippets, SQL measures, filters, starter questions) rather than the text instruction.

> **Note:** Replace `{prefix}` and `{postfix}` with your actual config values (e.g., `agent_demo` and `_mlc`).

---

## Space Description

Set the Genie Space description to:

> Retail sales, inventory, and customer analytics for GlowMart beauty supply stores.

---

## Join Snippets (Theme 1)

Create these 6 join knowledge snippets in the Genie Space:

| # | Base Table | Joined Table | ON Condition | Relationship |
|---|---|---|---|---|
| 1 | {prefix}_orders{postfix} | {prefix}_customers{postfix} | orders.customer_id = customers.customer_id | Many-to-one |
| 2 | {prefix}_orders{postfix} | {prefix}_stores{postfix} | orders.store_id = stores.store_id | Many-to-one |
| 3 | {prefix}_order_items{postfix} | {prefix}_products{postfix} | order_items.product_id = products.product_id | Many-to-one |
| 4 | {prefix}_order_items{postfix} | {prefix}_orders{postfix} | order_items.order_id = orders.order_id | Many-to-one |
| 5 | {prefix}_inventory{postfix} | {prefix}_stores{postfix} | inventory.store_id = stores.store_id | Many-to-one |
| 6 | {prefix}_inventory{postfix} | {prefix}_products{postfix} | inventory.product_id = products.product_id | Many-to-one |

---

## SQL Measures and Filters (Theme 2)

Create these 3 knowledge snippets:

### SQL Measure: Line Item Revenue

- **Type:** sql_measure
- **Title:** Line Item Revenue
- **SQL:** `order_items.unit_price * order_items.quantity * (1 - order_items.discount_pct)`
- **Synonyms:** revenue, sales, net revenue
- **Note:** Use this instead of orders.total_amount, which is an order-level approximate.

### SQL Filter: Online Orders

- **Type:** sql_filter
- **Title:** Online Orders
- **SQL:** `orders.channel = 'online'`
- **Description:** Use this filter when the user asks about online orders. Online orders also have store_id IS NULL.

### SQL Filter: In-Store Orders

- **Type:** sql_filter
- **Title:** In-Store Orders
- **SQL:** `orders.channel = 'in-store'`
- **Description:** Use this filter when the user asks about in-store or physical store orders.

---

## Column Synonyms (Long-tail)

Add these synonyms to improve column matching:

| Table | Column | Synonyms |
|---|---|---|
| inventory | quantity_on_hand | stock, inventory level, stock level |
| order_items | discount_pct | discount rate, discount percentage |
| orders | total_amount | order total |
| stores | square_footage | store size |

---

## SQL Example Questions

Add these as SQL examples in the Genie Space. Each title should match how a user would naturally phrase the question.

### 1. What is the total revenue by product category?

```sql
SELECT
  p.category,
  SUM(oi.unit_price * oi.quantity * (1 - oi.discount_pct)) AS total_revenue
FROM {prefix}_order_items{postfix} oi
JOIN {prefix}_products{postfix} p ON oi.product_id = p.product_id
GROUP BY p.category
ORDER BY total_revenue DESC
```

### 2. Who are the top 10 customers by lifetime spend?

```sql
SELECT
  c.customer_id,
  c.first_name,
  c.last_name,
  c.loyalty_tier,
  SUM(oi.unit_price * oi.quantity * (1 - oi.discount_pct)) AS lifetime_spend
FROM {prefix}_order_items{postfix} oi
JOIN {prefix}_orders{postfix} o ON oi.order_id = o.order_id
JOIN {prefix}_customers{postfix} c ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.first_name, c.last_name, c.loyalty_tier
ORDER BY lifetime_spend DESC
LIMIT 10
```

### 3. What is the monthly revenue trend?

```sql
SELECT
  DATE_TRUNC('month', o.order_date) AS order_month,
  SUM(oi.unit_price * oi.quantity * (1 - oi.discount_pct)) AS monthly_revenue
FROM {prefix}_order_items{postfix} oi
JOIN {prefix}_orders{postfix} o ON oi.order_id = o.order_id
GROUP BY order_month
ORDER BY order_month
```

### 4. Which products at which stores need to be reordered?

```sql
SELECT
  s.store_name,
  s.store_type,
  p.product_name,
  p.category,
  i.quantity_on_hand,
  i.reorder_point
FROM {prefix}_inventory{postfix} i
JOIN {prefix}_stores{postfix} s ON i.store_id = s.store_id
JOIN {prefix}_products{postfix} p ON i.product_id = p.product_id
WHERE i.needs_reorder = true
ORDER BY s.store_name, p.category
```

### 5. How does revenue compare between online and in-store channels?

```sql
SELECT
  o.channel,
  COUNT(DISTINCT o.order_id) AS total_orders,
  SUM(oi.unit_price * oi.quantity * (1 - oi.discount_pct)) AS total_revenue
FROM {prefix}_order_items{postfix} oi
JOIN {prefix}_orders{postfix} o ON oi.order_id = o.order_id
GROUP BY o.channel
ORDER BY total_revenue DESC
```

### 6. What is the average order value by customer loyalty tier?

```sql
SELECT
  c.loyalty_tier,
  COUNT(DISTINCT o.order_id) AS order_count,
  SUM(oi.unit_price * oi.quantity * (1 - oi.discount_pct)) / COUNT(DISTINCT o.order_id) AS avg_order_value
FROM {prefix}_order_items{postfix} oi
JOIN {prefix}_orders{postfix} o ON oi.order_id = o.order_id
JOIN {prefix}_customers{postfix} c ON o.customer_id = c.customer_id
GROUP BY c.loyalty_tier
ORDER BY avg_order_value DESC
```

### 7. What are the top 10 best-selling brands by revenue?

```sql
SELECT
  p.brand,
  SUM(oi.quantity) AS units_sold,
  SUM(oi.unit_price * oi.quantity * (1 - oi.discount_pct)) AS total_revenue
FROM {prefix}_order_items{postfix} oi
JOIN {prefix}_products{postfix} p ON oi.product_id = p.product_id
GROUP BY p.brand
ORDER BY total_revenue DESC
LIMIT 10
```

---

## Starter Questions (Theme 5)

Add these as starter questions in the Genie Space. They also serve as benchmarks for evaluating answer quality.

1. What are the top 10 best-selling products by revenue?
2. Which store has the highest average order value?
3. How does spending differ between loyalty tiers?
4. What percentage of sales come from organic products?
5. Which product categories are most popular with online vs. in-store customers?
6. Show me stores with the most items needing reorder.
7. What is the monthly revenue trend for 2024?
8. Which brands have the highest average customer rating?
9. What is the average basket size by channel and loyalty tier?
10. Which states contribute the most revenue?
