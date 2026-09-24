-- =============================================================================
-- 02 - DIMENSIONES
-- Esquema en estrella: cuatro dimensiones conformadas alrededor del hecho de
-- ventas. El cliente no identificado recibe la clave centinela -1 en lugar de
-- NULL, para que los JOIN del dashboard nunca pierdan filas en silencio.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS core;

-- -----------------------------------------------------------------------------
-- dim_fecha - calendario continuo, incluidos los dias sin ventas
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE core.dim_fecha AS
WITH rango AS (
    SELECT MIN(fecha) AS desde, MAX(fecha) AS hasta FROM stg.retail_clasificado
)
SELECT
    fecha,
    EXTRACT(YEAR    FROM fecha)                         AS anio,
    EXTRACT(MONTH   FROM fecha)                         AS mes,
    EXTRACT(QUARTER FROM fecha)                         AS trimestre,
    DATE_TRUNC('month', fecha)                          AS inicio_mes,
    strftime(fecha, '%Y-%m')                            AS anio_mes,
    EXTRACT(DOW FROM fecha)                             AS dia_semana,
    CASE EXTRACT(DOW FROM fecha)
        WHEN 0 THEN 'Domingo'   WHEN 1 THEN 'Lunes'  WHEN 2 THEN 'Martes'
        WHEN 3 THEN 'Miercoles' WHEN 4 THEN 'Jueves' WHEN 5 THEN 'Viernes'
        WHEN 6 THEN 'Sabado'
    END                                                 AS nombre_dia,
    CASE EXTRACT(MONTH FROM fecha)
        WHEN 1 THEN 'Enero'      WHEN 2 THEN 'Febrero'   WHEN 3 THEN 'Marzo'
        WHEN 4 THEN 'Abril'      WHEN 5 THEN 'Mayo'      WHEN 6 THEN 'Junio'
        WHEN 7 THEN 'Julio'      WHEN 8 THEN 'Agosto'    WHEN 9 THEN 'Septiembre'
        WHEN 10 THEN 'Octubre'   WHEN 11 THEN 'Noviembre' WHEN 12 THEN 'Diciembre'
    END                                                 AS nombre_mes,
    EXTRACT(DOW FROM fecha) IN (0, 6)                   AS es_fin_semana,
    -- El negocio es estacional: regalo navideno concentrado en el Q4.
    EXTRACT(MONTH FROM fecha) IN (9, 10, 11, 12)        AS es_temporada_alta
FROM rango, UNNEST(generate_series(rango.desde, rango.hasta, INTERVAL 1 DAY)) AS t(fecha);


-- -----------------------------------------------------------------------------
-- dim_cliente
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE core.dim_cliente AS
WITH identificados AS (
    SELECT
        CAST(cliente_id AS BIGINT)                      AS cliente_id,
        -- Un cliente puede facturar desde varios paises; asignamos aquel donde
        -- concentra mas gasto.
        ARG_MAX(pais, importe_pais)                     AS pais,
        MIN(primera)                                    AS primera_compra,
        MAX(ultima)                                     AS ultima_compra
    FROM (
        SELECT cliente_id, pais,
               SUM(importe) AS importe_pais,
               MIN(fecha)   AS primera,
               MAX(fecha)   AS ultima
        FROM stg.retail_clasificado
        WHERE cliente_identificado
        GROUP BY 1, 2
    )
    GROUP BY 1
)
SELECT
    cliente_id,
    pais,
    primera_compra,
    ultima_compra,
    DATE_DIFF('day', primera_compra, ultima_compra)     AS dias_de_vida,
    TRUE                                                AS identificado
FROM identificados

UNION ALL

-- Centinela: el 22,8% de las lineas no trae identificador de cliente. Son
-- ventas reales (mostrador y web sin registro) que no se pueden descartar,
-- pero tampoco deben entrar en analisis por cliente como RFM o cohortes.
SELECT -1, 'Desconocido', NULL, NULL, NULL, FALSE;


-- -----------------------------------------------------------------------------
-- dim_producto
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE core.dim_producto AS
SELECT
    sku,
    ANY_VALUE(descripcion)                                          AS descripcion,
    ANY_VALUE(tipo_linea)                                           AS tipo_linea,
    ROUND(MEDIAN(precio_unitario) FILTER (WHERE precio_valido), 2)   AS precio_mediano,
    MIN(fecha) FILTER (WHERE naturaleza = 'venta')                   AS primera_venta,
    MAX(fecha) FILTER (WHERE naturaleza = 'venta')                   AS ultima_venta
FROM stg.retail_clasificado
GROUP BY sku;


-- -----------------------------------------------------------------------------
-- dim_pais - agrupacion geografica para el analisis de mercados
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE core.dim_pais AS
SELECT
    pais,
    CASE
        WHEN pais IN ('United Kingdom', 'Channel Islands')                      THEN 'Reino Unido'
        WHEN pais IN ('EIRE', 'France', 'Germany', 'Netherlands', 'Belgium', 'Spain',
                      'Portugal', 'Italy', 'Austria', 'Switzerland', 'Sweden', 'Norway',
                      'Denmark', 'Finland', 'Iceland', 'Poland', 'Greece', 'Cyprus',
                      'Malta', 'Czech Republic', 'Lithuania', 'European Community')  THEN 'Resto de Europa'
        WHEN pais IN ('USA', 'Canada', 'Brazil', 'Bermuda', 'West Indies')          THEN 'America'
        WHEN pais IN ('Australia', 'Japan', 'Singapore', 'Hong Kong', 'Korea', 'Thailand') THEN 'Asia-Pacifico'
        WHEN pais IN ('Israel', 'United Arab Emirates', 'Bahrain', 'Lebanon',
                      'Saudi Arabia', 'Nigeria', 'RSA')                             THEN 'Oriente Medio y Africa'
        ELSE 'Sin clasificar'
    END                                         AS region,
    pais = 'United Kingdom'                     AS es_mercado_local
FROM (SELECT DISTINCT pais FROM stg.retail_clasificado);
