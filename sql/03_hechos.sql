-- =============================================================================
-- 03 - HECHOS
-- Dos granos: la linea de factura (detalle) y la factura (cabecera).
-- =============================================================================

-- -----------------------------------------------------------------------------
-- fact_lineas - grano: una linea de factura
--
-- Se conservan TODAS las lineas, incluidas devoluciones, ajustes y bajas de
-- inventario. El filtrado es responsabilidad de cada consulta, no de la carga:
-- perder la trazabilidad de una devolucion impediria calcular la tasa de
-- devolucion, que es uno de los KPI del tablero.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE core.fact_lineas AS
SELECT
    factura,
    sku,
    COALESCE(CAST(cliente_id AS BIGINT), -1)    AS cliente_id,
    fecha,
    fecha_hora,
    EXTRACT(HOUR FROM fecha_hora)               AS hora,
    pais,
    cantidad,
    precio_unitario,
    importe,
    tipo_linea,
    naturaleza,
    precio_valido,
    -- Marca de conveniencia: la linea entra en el calculo de ingresos solo si
    -- es producto o envio facturado a precio positivo.
    (tipo_linea IN ('producto', 'envio') AND precio_valido) AS computa_ingreso
FROM stg.retail_clasificado;


-- -----------------------------------------------------------------------------
-- fact_facturas - grano: una factura (cabecera agregada)
-- Evita repetir la agregacion por factura en cada consulta del dashboard.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE core.fact_facturas AS
SELECT
    factura,
    ANY_VALUE(cliente_id)                       AS cliente_id,
    MIN(fecha)                                  AS fecha,
    MIN(fecha_hora)                             AS fecha_hora,
    ANY_VALUE(pais)                             AS pais,
    COUNT(*)                                    AS lineas,
    COUNT(DISTINCT sku)                         AS skus_distintos,
    SUM(cantidad) FILTER (WHERE computa_ingreso)            AS unidades,
    ROUND(SUM(importe) FILTER (WHERE computa_ingreso), 2)   AS importe,
    MAX(naturaleza = 'devolucion')              AS es_devolucion
FROM core.fact_lineas
GROUP BY factura;


-- -----------------------------------------------------------------------------
-- Vista de trabajo: ventas netas de producto con cliente identificado.
-- Es la base de RFM, cohortes y CLV, donde una linea sin cliente distorsiona.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW core.ventas_identificadas AS
SELECT *
FROM core.fact_lineas
WHERE computa_ingreso
  AND cliente_id <> -1
  AND naturaleza = 'venta';
