-- =============================================================================
-- MART - Mercados y devoluciones
-- =============================================================================

CREATE OR REPLACE TABLE mart.paises AS
SELECT
    l.pais,
    d.region,
    d.es_mercado_local,
    ROUND(SUM(l.importe) FILTER (WHERE l.naturaleza = 'venta'), 2)          AS facturacion,
    COUNT(DISTINCT l.factura) FILTER (WHERE l.naturaleza = 'venta')         AS facturas,
    COUNT(DISTINCT l.cliente_id) FILTER (WHERE l.cliente_id <> -1)          AS clientes,
    SUM(l.cantidad) FILTER (WHERE l.naturaleza = 'venta')                   AS unidades,
    ROUND(ABS(COALESCE(SUM(l.importe) FILTER (WHERE l.naturaleza = 'devolucion'), 0)), 2) AS devuelto
FROM core.fact_lineas l
JOIN core.dim_pais d USING (pais)
WHERE l.tipo_linea IN ('producto', 'envio') AND l.precio_valido
GROUP BY 1, 2, 3
HAVING SUM(l.importe) FILTER (WHERE l.naturaleza = 'venta') > 0
ORDER BY facturacion DESC;


CREATE OR REPLACE TABLE mart.resumen_paises AS
SELECT
    *,
    ROUND(facturacion / NULLIF(facturas, 0), 2)                         AS ticket_medio,
    ROUND(facturacion / NULLIF(clientes, 0), 2)                         AS ingreso_por_cliente,
    ROUND(100.0 * devuelto / NULLIF(facturacion, 0), 2)                 AS tasa_devolucion_pct,
    ROUND(100.0 * facturacion / SUM(facturacion) OVER (), 2)            AS cuota_pct
FROM mart.paises
ORDER BY facturacion DESC;


-- -----------------------------------------------------------------------------
-- Devoluciones: volumen mensual y productos mas problematicos.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE mart.devoluciones_mensuales AS
SELECT
    f.inicio_mes,
    f.anio_mes,
    ROUND(ABS(SUM(l.importe)), 2)   AS importe_devuelto,
    ABS(SUM(l.cantidad))            AS unidades_devueltas,
    COUNT(DISTINCT l.factura)       AS notas_credito
FROM core.fact_lineas l
JOIN core.dim_fecha f USING (fecha)
WHERE l.naturaleza = 'devolucion' AND l.tipo_linea IN ('producto', 'envio')
GROUP BY 1, 2
ORDER BY 1;


CREATE OR REPLACE TABLE mart.top_devoluciones AS
SELECT
    sku,
    descripcion,
    facturacion,
    devuelto,
    tasa_devolucion_pct,
    clase_abc
FROM mart.productos
WHERE devuelto > 0 AND facturacion > 1000
ORDER BY devuelto DESC
LIMIT 40;
