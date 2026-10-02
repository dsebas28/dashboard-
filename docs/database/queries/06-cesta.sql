-- titulo: Productos que se compran juntos
-- descripcion: Análisis de cesta publicado en mart.cesta: pares de productos que aparecen en las mismas facturas. El lift mide cuántas veces más de lo esperado por azar coinciden.
SELECT producto_a, producto_b, juntas AS facturas_juntas, confianza_pct, ROUND(lift::numeric, 1) AS lift
FROM mart.cesta
ORDER BY juntas DESC
LIMIT 10;
