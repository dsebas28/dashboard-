-- titulo: Tablas del almacén en PostgreSQL
-- descripcion: Filas y tamaño en disco (datos más índices) de las tablas de los esquemas core y mart, según las estadísticas de PostgreSQL.
SELECT schemaname || '.' || relname                    AS tabla,
       n_live_tup                                      AS filas,
       pg_size_pretty(pg_total_relation_size(relid))   AS tamano
FROM pg_stat_user_tables
WHERE schemaname IN ('core', 'mart')
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 14;
