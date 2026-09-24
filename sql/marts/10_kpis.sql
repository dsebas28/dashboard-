-- =============================================================================
-- MART - Indicadores de cabecera y resumen de calidad del dato
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS mart;

CREATE OR REPLACE TABLE mart.kpis AS
WITH ingresos AS (
    SELECT
        ROUND(SUM(importe), 2)                          AS facturacion,
        SUM(cantidad)                                   AS unidades,
        COUNT(DISTINCT factura)                         AS facturas,
        COUNT(DISTINCT cliente_id) FILTER (WHERE cliente_id <> -1) AS clientes,
        COUNT(DISTINCT sku)                             AS skus,
        COUNT(DISTINCT pais)                            AS paises,
        MIN(fecha)                                      AS desde,
        MAX(fecha)                                      AS hasta
    FROM core.fact_lineas
    WHERE computa_ingreso AND naturaleza = 'venta'
),
devoluciones AS (
    SELECT ROUND(ABS(SUM(importe)), 2) AS importe_devuelto,
           COUNT(DISTINCT factura)     AS notas_credito
    FROM core.fact_lineas
    WHERE naturaleza = 'devolucion' AND tipo_linea IN ('producto', 'envio')
)
SELECT
    i.facturacion,
    i.unidades,
    i.facturas,
    i.clientes,
    i.skus,
    i.paises,
    i.desde,
    i.hasta,
    ROUND(i.facturacion / i.facturas, 2)                        AS ticket_medio,
    ROUND(i.facturacion / i.clientes, 2)                        AS ingreso_por_cliente,
    ROUND(i.unidades / i.facturas, 1)                           AS unidades_por_factura,
    d.importe_devuelto,
    d.notas_credito,
    -- Tasa de devolucion sobre facturacion bruta: el KPI que mas duele en un
    -- negocio de regalo mayorista, donde el producto es fragil y estacional.
    ROUND(100.0 * d.importe_devuelto / i.facturacion, 2)        AS tasa_devolucion_pct
FROM ingresos i, devoluciones d;


-- -----------------------------------------------------------------------------
-- Trazabilidad de la limpieza: cuanto se descarto y por que.
-- Se publica en el dashboard para que el tablero sea auditable.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE mart.calidad_dato AS
SELECT 1 AS orden, 'Filas en el Excel original'            AS etapa,
       (SELECT COUNT(*) FROM stg.retail_crudo)             AS filas,
       'Fuente UCI sin tocar'                              AS detalle
UNION ALL SELECT 2, 'Tras eliminar el solape entre hojas',
       (SELECT COUNT(*) FROM stg.sin_solape),
       'El 1-9 dic 2010 aparecia en las dos hojas del libro'
UNION ALL SELECT 3, 'Tras eliminar duplicados exactos',
       (SELECT COUNT(*) FROM core.fact_lineas),
       'Misma factura, SKU, cantidad, precio y minuto'
UNION ALL SELECT 4, 'Lineas que computan como ingreso',
       (SELECT COUNT(*) FROM core.fact_lineas WHERE computa_ingreso AND naturaleza = 'venta'),
       'Producto o envio, precio positivo, no devolucion'
UNION ALL SELECT 5, 'Lineas de devolucion',
       (SELECT COUNT(*) FROM core.fact_lineas WHERE naturaleza = 'devolucion'),
       'Facturas con prefijo C (notas de credito)'
UNION ALL SELECT 6, 'Bajas de inventario',
       (SELECT COUNT(*) FROM core.fact_lineas WHERE naturaleza = 'baja_inventario'),
       'Cantidad negativa sin nota de credito: roturas y perdidas'
UNION ALL SELECT 7, 'Ajustes, comisiones y vouchers',
       (SELECT COUNT(*) FROM core.fact_lineas WHERE tipo_linea NOT IN ('producto', 'envio')),
       'Codigos de servicio: AMAZONFEE, BANK CHARGES, Manual, Discount'
UNION ALL SELECT 8, 'Lineas sin cliente identificado',
       (SELECT COUNT(*) FROM core.fact_lineas WHERE cliente_id = -1),
       'Se conservan para ingresos, se excluyen de RFM y cohortes'
ORDER BY orden;
