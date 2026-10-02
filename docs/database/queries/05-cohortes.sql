-- titulo: Retención por cohortes
-- descripcion: Porcentaje de cada cohorte (mes de primera compra) que vuelve a comprar 1, 2, 3, 6 y 12 meses después. FILTER pivota los meses en columnas sobre la tabla mart.cohortes.
SELECT etiqueta_cohorte                                                 AS cohorte,
       MAX(clientes) FILTER (WHERE mes_indice = 0)                      AS clientes,
       MAX(retencion_pct) FILTER (WHERE mes_indice = 1)                 AS mes_1,
       MAX(retencion_pct) FILTER (WHERE mes_indice = 2)                 AS mes_2,
       MAX(retencion_pct) FILTER (WHERE mes_indice = 3)                 AS mes_3,
       MAX(retencion_pct) FILTER (WHERE mes_indice = 6)                 AS mes_6,
       MAX(retencion_pct) FILTER (WHERE mes_indice = 12)                AS mes_12
FROM mart.cohortes
WHERE etiqueta_cohorte BETWEEN '2009-12' AND '2010-10'
GROUP BY etiqueta_cohorte
ORDER BY etiqueta_cohorte;
