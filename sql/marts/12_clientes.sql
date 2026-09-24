-- =============================================================================
-- MART - Cliente: RFM, concentracion de ingresos y cohortes de retencion
-- =============================================================================

-- -----------------------------------------------------------------------------
-- RFM (Recencia, Frecuencia, Monetario)
--
-- La fecha de referencia es el dia siguiente a la ultima transaccion del
-- dataset (2011-12-09). Usar CURRENT_DATE daria recencias de mas de una decada
-- para todos los clientes y volveria inservible la segmentacion.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE mart.rfm AS
WITH referencia AS (
    SELECT MAX(fecha) + INTERVAL 1 DAY AS hoy FROM core.ventas_identificadas
),
metricas AS (
    SELECT
        v.cliente_id,
        DATE_DIFF('day', MAX(v.fecha), (SELECT hoy FROM referencia))    AS recencia_dias,
        COUNT(DISTINCT v.factura)                                       AS frecuencia,
        ROUND(SUM(v.importe), 2)                                        AS monetario,
        MIN(v.fecha)                                                    AS primera_compra,
        MAX(v.fecha)                                                    AS ultima_compra,
        ROUND(SUM(v.importe) / COUNT(DISTINCT v.factura), 2)            AS ticket_medio
    FROM core.ventas_identificadas v
    GROUP BY 1
),
puntuado AS (
    SELECT
        *,
        -- Quintiles. En recencia el orden se invierte: haber comprado hace
        -- poco es lo bueno, asi que 5 corresponde a la menor recencia.
        6 - NTILE(5) OVER (ORDER BY recencia_dias)  AS r,
        NTILE(5) OVER (ORDER BY frecuencia)         AS f,
        NTILE(5) OVER (ORDER BY monetario)          AS m
    FROM metricas
)
SELECT
    p.*,
    c.pais,
    p.r * 100 + p.f * 10 + p.m                      AS codigo_rfm,
    ROUND((p.r + p.f + p.m) / 3.0, 2)               AS rfm_medio,
    CASE
        WHEN p.r >= 4 AND p.f >= 4 AND p.m >= 4 THEN 'Campeones'
        WHEN p.r >= 4 AND p.f <= 2              THEN 'Nuevos prometedores'
        WHEN p.r >= 3 AND p.f >= 3              THEN 'Leales'
        WHEN p.r >= 3 AND p.m >= 4              THEN 'Gran gasto reciente'
        WHEN p.r <= 2 AND p.f >= 4              THEN 'No se pueden perder'
        WHEN p.r =  2 AND p.f >= 3              THEN 'En riesgo'
        WHEN p.r <= 2 AND p.f <= 2 AND p.m <= 2 THEN 'Hibernando'
        WHEN p.r <= 1                           THEN 'Perdidos'
        ELSE 'Atencion requerida'
    END                                             AS segmento
FROM puntuado p
JOIN core.dim_cliente c USING (cliente_id);


CREATE OR REPLACE TABLE mart.resumen_segmentos AS
SELECT
    segmento,
    COUNT(*)                                                        AS clientes,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)              AS pct_clientes,
    ROUND(SUM(monetario), 2)                                        AS facturacion,
    ROUND(100.0 * SUM(monetario) / SUM(SUM(monetario)) OVER (), 1)  AS pct_facturacion,
    ROUND(AVG(recencia_dias), 0)                                    AS recencia_media,
    ROUND(AVG(frecuencia), 1)                                       AS frecuencia_media,
    ROUND(AVG(monetario), 2)                                        AS gasto_medio
FROM mart.rfm
GROUP BY 1
ORDER BY facturacion DESC;


-- -----------------------------------------------------------------------------
-- Curva de Pareto: que porcentaje de clientes acumula que porcentaje de la
-- facturacion. En mayorista la respuesta suele estar lejos del 80/20 teorico.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE mart.pareto_clientes AS
WITH ordenados AS (
    SELECT cliente_id, pais, monetario, frecuencia, segmento,
           ROW_NUMBER() OVER (ORDER BY monetario DESC) AS posicion
    FROM mart.rfm
)
SELECT
    *,
    ROUND(100.0 * posicion / COUNT(*) OVER (), 3)                                       AS pct_clientes_acum,
    ROUND(100.0 * SUM(monetario) OVER (ORDER BY posicion) / SUM(monetario) OVER (), 3)  AS pct_facturacion_acum
FROM ordenados
ORDER BY posicion;


-- -----------------------------------------------------------------------------
-- Cohortes de retencion: se agrupa cada cliente por el mes de su PRIMERA
-- compra y se mide cuantos vuelven a comprar N meses despues.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE mart.cohortes AS
WITH primera AS (
    SELECT cliente_id, DATE_TRUNC('month', MIN(fecha)) AS cohorte
    FROM core.ventas_identificadas
    GROUP BY 1
),
actividad AS (
    SELECT DISTINCT
        v.cliente_id,
        p.cohorte,
        DATE_TRUNC('month', v.fecha) AS mes_actividad
    FROM core.ventas_identificadas v
    JOIN primera p USING (cliente_id)
),
conteo AS (
    SELECT
        cohorte,
        DATE_DIFF('month', cohorte, mes_actividad) AS mes_indice,
        COUNT(DISTINCT cliente_id)                 AS clientes
    FROM actividad
    GROUP BY 1, 2
),
tamanos AS (
    SELECT cohorte, clientes AS tamano_cohorte
    FROM conteo
    WHERE mes_indice = 0
)
SELECT
    c.cohorte,
    strftime(c.cohorte, '%Y-%m')                    AS etiqueta_cohorte,
    c.mes_indice,
    c.clientes,
    t.tamano_cohorte,
    ROUND(100.0 * c.clientes / t.tamano_cohorte, 1) AS retencion_pct
FROM conteo c
JOIN tamanos t USING (cohorte)
ORDER BY c.cohorte, c.mes_indice;
