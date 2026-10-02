-- =============================================================================
-- PostgreSQL - INDICES
-- Se crean despues de copiar los datos: construir un indice sobre una tabla ya
-- llena es mucho mas rapido que mantenerlo fila a fila durante la carga.
-- Cada uno responde a un filtro real del tablero.
-- =============================================================================

-- Todas las consultas del tablero filtran por rango de fechas y, opcionalmente, por pais.
CREATE INDEX fact_lineas_fecha_pais ON core.fact_lineas (fecha, pais);

-- RFM y cohortes recorren el historial de cada cliente (excluido el centinela).
CREATE INDEX fact_lineas_cliente ON core.fact_lineas (cliente_id, fecha) WHERE cliente_id <> -1;

-- Ranking ABC y analisis de cesta agrupan por producto.
CREATE INDEX fact_lineas_sku ON core.fact_lineas (sku);

-- Union linea -> factura.
CREATE INDEX fact_lineas_factura ON core.fact_lineas (factura);

CREATE INDEX fact_facturas_cliente_fecha ON core.fact_facturas (cliente_id, fecha);

ANALYZE;
