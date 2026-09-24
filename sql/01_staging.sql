-- =============================================================================
-- 01 - STAGING
-- Limpieza y tipado de la fuente cruda. Cada regla aqui responde a un problema
-- que se encontro perfilando los datos, no a una suposicion.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS stg;

-- -----------------------------------------------------------------------------
-- Carga cruda desde el Parquet generado por src/ingest.py
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE stg.retail_crudo AS
SELECT * FROM read_parquet(getvariable('ruta_parquet'));


-- -----------------------------------------------------------------------------
-- REGLA 1 - Solape entre hojas del Excel
--
-- El libro original trae dos hojas por ejercicio, pero los rangos se pisan:
--   'Year 2009-2010' cubre 2009-12-01 -> 2010-12-09
--   'Year 2010-2011' cubre 2010-12-01 -> 2011-12-09
-- Los 9 primeros dias de diciembre de 2010 estan en AMBAS, con 22.523 filas y
-- 377.488 GBP identicos en cada una. Nos quedamos con la copia de la hoja mas
-- reciente y recortamos la hoja antigua en su frontera real.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW stg.sin_solape AS
SELECT *
FROM stg.retail_crudo
WHERE NOT (source_sheet = 'Year 2009-2010' AND InvoiceDate >= DATE '2010-12-01');


-- -----------------------------------------------------------------------------
-- REGLA 2 - Duplicados exactos
--
-- Quedan ~11.800 filas identicas en los seis campos que definen una linea de
-- factura (misma factura, mismo SKU, misma cantidad, mismo timestamp al minuto
-- y mismo precio). En un TPV esto es reescaneo de la misma linea, no ventas
-- distintas: una venta real de 20 unidades se registra como Quantity = 20.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW stg.sin_duplicados AS
SELECT DISTINCT
    Invoice, StockCode, Description, Quantity, InvoiceDate, Price, Customer_ID, Country
FROM stg.sin_solape;


-- -----------------------------------------------------------------------------
-- REGLA 3 - Descripcion canonica por SKU
--
-- 1.212 SKUs arrastran mas de una descripcion (erratas, cambios de nombre y
-- anotaciones del almacen como 'check', 'found', 'damages'). Elegimos como
-- canonica la variante mas frecuente de cada SKU.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE stg.descripcion_canonica AS
WITH normalizadas AS (
    SELECT
        StockCode,
        UPPER(TRIM(REGEXP_REPLACE(Description, '\s+', ' ', 'g'))) AS descripcion,
        COUNT(*) AS apariciones
    FROM stg.sin_duplicados
    WHERE Description IS NOT NULL
      AND TRIM(Description) <> ''
      -- Anotaciones internas del almacen: no son nombres de producto.
      AND NOT REGEXP_MATCHES(Description, '(?i)^\s*(check|\?+|found|missing|lost|damage|smashed|broken|wet|mould|test|adjust|thrown|sold as)')
    GROUP BY 1, 2
)
SELECT StockCode, descripcion
FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY StockCode ORDER BY apariciones DESC, descripcion) AS rn
    FROM normalizadas
)
WHERE rn = 1;


-- -----------------------------------------------------------------------------
-- REGLA 4 - Clasificacion de la linea
--
-- No todo lo facturado es producto. El catalogo mezcla codigos de servicio que
-- hay que poder aislar: si no, los 260.000 GBP negativos de 'AMAZONFEE' o los
-- 147.000 GBP de 'Adjust bad debt' contaminan cualquier KPI de ventas.
-- No se borran: se etiquetan, para que el analisis decida en cada caso.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW stg.retail_clasificado AS
SELECT
    t.Invoice                                   AS factura,
    t.StockCode                                 AS sku,
    COALESCE(d.descripcion, 'SIN DESCRIPCION')  AS descripcion,
    t.Quantity                                  AS cantidad,
    t.Price                                     AS precio_unitario,
    t.InvoiceDate                               AS fecha_hora,
    CAST(t.InvoiceDate AS DATE)                 AS fecha,
    t.Customer_ID                               AS cliente_id,
    TRIM(t.Country)                             AS pais,
    ROUND(t.Quantity * t.Price, 2)              AS importe,

    CASE
        WHEN UPPER(t.StockCode) IN ('POST', 'DOT', 'C2')            THEN 'envio'
        WHEN UPPER(t.StockCode) LIKE 'GIFT\_%' ESCAPE '\'           THEN 'voucher'
        WHEN UPPER(t.StockCode) IN ('M', 'D', 'B', 'S', 'ADJUST', 'PADS',
                                    'BANK CHARGES', 'AMAZONFEE', 'CRUK')  THEN 'ajuste'
        WHEN UPPER(t.StockCode) LIKE 'TEST%'                        THEN 'prueba'
        ELSE 'producto'
    END                                         AS tipo_linea,

    -- Las facturas con prefijo 'C' son notas de credito. Pero hay 3.457 lineas
    -- con cantidad negativa SIN ese prefijo: son bajas de inventario que el
    -- almacen registra como si fueran ventas negativas.
    CASE
        WHEN t.Invoice LIKE 'C%'  THEN 'devolucion'
        WHEN t.Quantity < 0       THEN 'baja_inventario'
        ELSE 'venta'
    END                                         AS naturaleza,

    (t.Customer_ID IS NOT NULL)                 AS cliente_identificado,
    (t.Price > 0)                               AS precio_valido
FROM stg.sin_duplicados t
LEFT JOIN stg.descripcion_canonica d USING (StockCode);
