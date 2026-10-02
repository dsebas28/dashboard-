-- titulo: Concentración de la facturación (Pareto)
-- descripcion: Qué parte de la facturación genera cada tramo de clientes, ordenados por gasto. NTILE(10) reparte los 5.854 clientes identificados en deciles.
WITH gasto AS (
    SELECT cliente_id, SUM(importe) AS gbp
    FROM core.ventas_identificadas
    GROUP BY cliente_id
),
deciles AS (
    SELECT gbp, NTILE(10) OVER (ORDER BY gbp DESC, cliente_id) AS decil
    FROM gasto
)
SELECT decil,
       COUNT(*)                                                  AS clientes,
       ROUND(SUM(gbp) / 1000, 0)                                 AS miles_gbp,
       ROUND(100 * SUM(gbp) / SUM(SUM(gbp)) OVER (), 1)          AS cuota_pct,
       ROUND(100 * SUM(SUM(gbp)) OVER (ORDER BY decil) / SUM(SUM(gbp)) OVER (), 1) AS cuota_acumulada_pct
FROM deciles
GROUP BY decil
ORDER BY decil;
