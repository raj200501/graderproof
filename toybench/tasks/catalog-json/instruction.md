# Product catalog to JSON

The online shop exports its catalog as `products.csv` in the working directory. The new storefront needs the same data as JSON.

Write `products.json` in the working directory. It must contain a JSON array with one object per data row of `products.csv`, in the same order as the rows. Each object has exactly these four keys:

- `sku`: the SKU, as a string, unchanged.
- `name`: the product name, as a string, unchanged. The CSV uses standard quoting, so a quoted value such as `"Braided Cable, 2 m"` is a single field.
- `price`: the price as a JSON number (for example `39.5` for `39.50`).
- `in_stock`: `true` if the `in_stock` column is `yes`, `false` if it is `no`.

Indentation, spacing, and the order of keys inside each object are up to you.
