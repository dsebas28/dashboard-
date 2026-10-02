-- titulo: Mercados por región
-- descripcion: Facturación, facturas, clientes y tasa de devolución por región, uniendo el hecho con la dimensión de países. FILTER separa ventas y devoluciones en una sola pasada.
SELECT p.region,
       COUNT(DISTINCT l.pais)                                                    AS paises,
       ROUND(SUM(l.importe) FILTER (WHERE l.naturaleza = 'venta') / 1000, 0)     AS miles_gbp,
       COUNT(DISTINCT l.cliente_id) FILTER (WHERE l.cliente_id <> -1)            AS clientes,
       ROUND(100 * ABS(SUM(l.importe) FILTER (WHERE l.naturaleza = 'devolucion'))
             / SUM(l.importe) FILTER (WHERE l.naturaleza = 'venta'), 2)          AS devolucion_pct
FROM core.fact_lineas l
JOIN core.dim_pais p USING (pais)
WHERE l.tipo_linea IN ('producto', 'envio') AND l.precio_valido
GROUP BY p.region
ORDER BY miles_gbp DESC;
