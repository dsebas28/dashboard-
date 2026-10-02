-- titulo: Traza de limpieza: del Excel al almacén
-- descripcion: La capa mart publica qué se descartó en cada paso y por qué. El solape entre las dos hojas del Excel duplicaba 22.523 líneas del 1 al 9 de diciembre de 2010; una ventana LAG calcula cuántas filas quita cada etapa.
SELECT orden,
       etapa,
       filas,
       filas - LAG(filas) OVER (ORDER BY orden)  AS diferencia,
       detalle
FROM mart.calidad_dato
ORDER BY orden;
