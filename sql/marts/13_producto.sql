-- =============================================================================
-- MART - Producto: ranking, concentracion ABC y afinidad de cesta
-- =============================================================================

CREATE OR REPLACE TABLE mart.productos AS
WITH ventas AS (
    SELECT
        l.sku,
        ROUND(SUM(l.importe) FILTER (WHERE l.naturaleza = 'venta'), 2)   AS facturacion,
        SUM(l.cantidad)      FILTER (WHERE l.naturaleza = 'venta')       AS unidades,
        COUNT(DISTINCT l.factura) FILTER (WHERE l.naturaleza = 'venta')  AS facturas,
        COUNT(DISTINCT l.cliente_id) FILTER (WHERE l.cliente_id <> -1)   AS clientes,
        ROUND(ABS(COALESCE(SUM(l.importe) FILTER (WHERE l.naturaleza = 'devolucion'), 0)), 2) AS devuelto
    FROM core.fact_lineas l
    WHERE l.tipo_linea = 'producto' AND l.precio_valido
    GROUP BY 1
),
clasificado AS (
    SELECT
        v.*,
        p.descripcion,
        p.precio_mediano,
        ROUND(100.0 * v.devuelto / NULLIF(v.facturacion, 0), 2) AS tasa_devolucion_pct,
        ROUND(100.0 * SUM(v.facturacion) OVER (ORDER BY v.facturacion DESC)
              / SUM(v.facturacion) OVER (), 2)                  AS pct_acumulado
    FROM ventas v
    JOIN core.dim_producto p USING (sku)
    WHERE v.facturacion > 0
)
SELECT
    *,
    -- Clasificacion ABC clasica de gestion de inventario.
    CASE
        WHEN pct_acumulado <= 80 THEN 'A'
        WHEN pct_acumulado <= 95 THEN 'B'
        ELSE 'C'
    END AS clase_abc
FROM clasificado
ORDER BY facturacion DESC;


-- -----------------------------------------------------------------------------
-- Analisis de cesta (market basket)
--
-- El coste de cruzar 5.000 SKU contra si mismos es cuadratico, asi que se
-- limita a los 150 productos mas presentes en facturas. Es donde estan las
-- reglas con soporte suficiente para ser accionables.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE mart.cesta AS
WITH cestas AS (
    SELECT DISTINCT factura, sku
    FROM core.fact_lineas
    WHERE computa_ingreso AND naturaleza = 'venta' AND tipo_linea = 'producto'
),
total AS (
    SELECT COUNT(DISTINCT factura) AS n_facturas FROM cestas
),
frecuentes AS (
    SELECT sku, COUNT(*) AS apariciones
    FROM cestas
    GROUP BY 1
    ORDER BY apariciones DESC
    LIMIT 150
),
cestas_top AS (
    SELECT c.* FROM cestas c JOIN frecuentes f USING (sku)
),
pares AS (
    SELECT
        a.sku AS sku_a,
        b.sku AS sku_b,
        COUNT(*) AS juntas
    FROM cestas_top a
    JOIN cestas_top b ON a.factura = b.factura AND a.sku < b.sku
    GROUP BY 1, 2
    HAVING COUNT(*) >= 30
)
SELECT
    p.sku_a,
    da.descripcion                                              AS producto_a,
    p.sku_b,
    db.descripcion                                              AS producto_b,
    p.juntas,
    ROUND(100.0 * p.juntas / t.n_facturas, 3)                   AS soporte_pct,
    -- Confianza: de las facturas que llevan A, que porcentaje lleva tambien B.
    ROUND(100.0 * p.juntas / fa.apariciones, 1)                 AS confianza_pct,
    -- Lift > 1 significa que aparecen juntos mas de lo que el azar explicaria.
    ROUND((1.0 * p.juntas / t.n_facturas)
          / ((1.0 * fa.apariciones / t.n_facturas) * (1.0 * fb.apariciones / t.n_facturas)), 2) AS lift
FROM pares p
CROSS JOIN total t
JOIN frecuentes fa ON fa.sku = p.sku_a
JOIN frecuentes fb ON fb.sku = p.sku_b
JOIN core.dim_producto da ON da.sku = p.sku_a
JOIN core.dim_producto db ON db.sku = p.sku_b
ORDER BY lift DESC;
