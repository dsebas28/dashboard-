-- titulo: Facturación mensual con media móvil
-- descripcion: Ventas netas de producto y envío por mes sobre el millón de líneas del hecho, con una media móvil de 3 meses (ventana ROWS BETWEEN). Diciembre de 2011 solo llega hasta el día 9.
SELECT f.anio_mes                                                    AS mes,
       COUNT(DISTINCT l.factura)                                     AS facturas,
       ROUND(SUM(l.importe) / 1000, 1)                               AS miles_gbp,
       ROUND(AVG(SUM(l.importe)) OVER (ORDER BY f.anio_mes
             ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) / 1000, 1)    AS media_movil_3m
FROM core.fact_lineas l
JOIN core.dim_fecha f USING (fecha)
WHERE l.computa_ingreso AND l.naturaleza = 'venta'
GROUP BY f.anio_mes
ORDER BY f.anio_mes;
