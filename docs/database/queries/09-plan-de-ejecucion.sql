-- titulo: Plan de ejecución: historial de un cliente
-- descripcion: RFM y cohortes leen el historial de cada cliente. El índice parcial (cliente_id, fecha) WHERE cliente_id <> -1 deja fuera las 235.000 líneas sin cliente y localiza las compras de uno solo sin recorrer el millón de filas.
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF, SUMMARY OFF, BUFFERS OFF)
SELECT fecha, factura, importe
FROM core.fact_lineas
WHERE cliente_id = 12347
ORDER BY fecha;
