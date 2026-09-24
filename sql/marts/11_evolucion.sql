-- =============================================================================
-- MART - Evolucion temporal: serie mensual, diaria y patron horario
-- =============================================================================

CREATE OR REPLACE TABLE mart.ventas_mensuales AS
WITH base AS (
    SELECT
        f.inicio_mes,
        f.anio_mes,
        f.nombre_mes || ' ' || f.anio                                            AS etiqueta,
        ROUND(SUM(l.importe) FILTER (WHERE l.naturaleza = 'venta'), 2)           AS facturacion,
        ROUND(ABS(SUM(l.importe) FILTER (WHERE l.naturaleza = 'devolucion')), 2) AS devoluciones,
        COUNT(DISTINCT l.factura) FILTER (WHERE l.naturaleza = 'venta')          AS facturas,
        COUNT(DISTINCT l.cliente_id) FILTER (WHERE l.cliente_id <> -1)           AS clientes,
        SUM(l.cantidad) FILTER (WHERE l.naturaleza = 'venta')                    AS unidades
    FROM core.fact_lineas l
    JOIN core.dim_fecha f USING (fecha)
    WHERE l.tipo_linea IN ('producto', 'envio') AND l.precio_valido
    GROUP BY 1, 2, 3
)
SELECT
    *,
    ROUND(facturacion - devoluciones, 2)                        AS facturacion_neta,
    ROUND(facturacion / NULLIF(facturas, 0), 2)                 AS ticket_medio,
    -- Crecimiento intermensual y contra el mismo mes del anio anterior: con una
    -- estacionalidad navidena tan marcada, el dato mes contra mes solo engana.
    ROUND(100.0 * (facturacion - LAG(facturacion) OVER (ORDER BY inicio_mes))
          / NULLIF(LAG(facturacion) OVER (ORDER BY inicio_mes), 0), 1)      AS var_mes_pct,
    ROUND(100.0 * (facturacion - LAG(facturacion, 12) OVER (ORDER BY inicio_mes))
          / NULLIF(LAG(facturacion, 12) OVER (ORDER BY inicio_mes), 0), 1)  AS var_anual_pct,
    ROUND(AVG(facturacion) OVER (ORDER BY inicio_mes
                                 ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 2) AS media_movil_3m
FROM base
ORDER BY inicio_mes;


CREATE OR REPLACE TABLE mart.ventas_diarias AS
SELECT
    f.fecha,
    f.nombre_dia,
    f.es_fin_semana,
    f.es_temporada_alta,
    ROUND(COALESCE(SUM(l.importe) FILTER (WHERE l.naturaleza = 'venta'), 0), 2) AS facturacion,
    COUNT(DISTINCT l.factura) FILTER (WHERE l.naturaleza = 'venta')             AS facturas
FROM core.dim_fecha f
LEFT JOIN core.fact_lineas l
       ON l.fecha = f.fecha AND l.computa_ingreso
GROUP BY 1, 2, 3, 4
ORDER BY 1;


-- -----------------------------------------------------------------------------
-- Patron operativo: dia de la semana x hora del dia.
-- Alimenta el mapa de calor que revela la ventana comercial real del negocio.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE mart.patron_horario AS
SELECT
    f.dia_semana,
    f.nombre_dia,
    l.hora,
    ROUND(SUM(l.importe), 2)        AS facturacion,
    COUNT(DISTINCT l.factura)       AS facturas
FROM core.fact_lineas l
JOIN core.dim_fecha f USING (fecha)
WHERE l.computa_ingreso AND l.naturaleza = 'venta'
GROUP BY 1, 2, 3
ORDER BY 1, 3;
