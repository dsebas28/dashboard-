-- titulo: Segmentos RFM
-- descripcion: La capa mart publica la segmentación por recencia, frecuencia y valor monetario. Los Campeones son pocos clientes y la mayor parte del negocio.
SELECT segmento,
       COUNT(*)                                              AS clientes,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)    AS clientes_pct,
       ROUND(SUM(monetario)::numeric / 1000, 0)              AS miles_gbp,
       ROUND((100 * SUM(monetario) / SUM(SUM(monetario)) OVER ())::numeric, 1) AS facturacion_pct,
       ROUND(AVG(recencia_dias))                             AS recencia_media_dias
FROM mart.rfm
GROUP BY segmento
ORDER BY miles_gbp DESC;
