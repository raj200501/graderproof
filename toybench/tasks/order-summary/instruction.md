# Daily order summary

`orders.jsonl` contains one JSON object per line, one per order, with the fields `order_id`, `product`, `quantity`, and `unit_price`.

Write `summary.json` containing a single JSON object with exactly these keys:

- `orders`: the number of orders (an integer);
- `units`: the total quantity over all orders (an integer);
- `revenue`: the sum of quantity × unit_price over all orders, rounded to 2 decimal places (a number);
- `top_product`: the product with the largest total quantity (a string; there is no tie in this data).
