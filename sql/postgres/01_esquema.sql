-- =============================================================================
-- PostgreSQL - ESQUEMA DEL ALMACEN PUBLICADO
--
-- DuckDB construye y limpia el almacen (sql/01..03 y sql/marts). Este archivo
-- define como queda servido en PostgreSQL: el mismo esquema en estrella, pero
-- con lo que un servidor de base de datos aporta y un archivo analitico no:
-- claves primarias, claves foraneas, restricciones CHECK e indices.
--
-- Lo ejecuta src/publish_postgres.py antes de copiar los datos.
-- =============================================================================

DROP SCHEMA IF EXISTS mart CASCADE;
DROP SCHEMA IF EXISTS core CASCADE;
CREATE SCHEMA core;
CREATE SCHEMA mart;

-- -----------------------------------------------------------------------------
-- Dimensiones
-- -----------------------------------------------------------------------------
CREATE TABLE core.dim_fecha (
    fecha              DATE         PRIMARY KEY,
    anio               SMALLINT     NOT NULL,
    mes                SMALLINT     NOT NULL CHECK (mes BETWEEN 1 AND 12),
    trimestre          SMALLINT     NOT NULL CHECK (trimestre BETWEEN 1 AND 4),
    inicio_mes         DATE         NOT NULL,
    anio_mes           CHAR(7)      NOT NULL,
    dia_semana         SMALLINT     NOT NULL CHECK (dia_semana BETWEEN 0 AND 6),   -- 0 = domingo
    nombre_dia         VARCHAR(10)  NOT NULL,
    nombre_mes         VARCHAR(10)  NOT NULL,
    es_fin_semana      BOOLEAN      NOT NULL,
    es_temporada_alta  BOOLEAN      NOT NULL
);

-- cliente_id = -1 es el centinela del cliente no identificado (nunca NULL).
CREATE TABLE core.dim_cliente (
    cliente_id      BIGINT       PRIMARY KEY,
    pais            VARCHAR(40)  NOT NULL,
    primera_compra  DATE,
    ultima_compra   DATE,
    dias_de_vida    INTEGER      CHECK (dias_de_vida >= 0),
    identificado    BOOLEAN      NOT NULL,
    CONSTRAINT dim_cliente_centinela CHECK ((cliente_id = -1) = NOT identificado),
    CONSTRAINT dim_cliente_fechas    CHECK (ultima_compra >= primera_compra)
);

CREATE TABLE core.dim_producto (
    sku             VARCHAR(20)    PRIMARY KEY,
    descripcion     TEXT           NOT NULL,
    tipo_linea      VARCHAR(10)    NOT NULL CHECK (tipo_linea IN ('producto', 'envio', 'ajuste', 'voucher', 'prueba')),
    precio_mediano  NUMERIC(10, 2) CHECK (precio_mediano >= 0),
    primera_venta   DATE,
    ultima_venta    DATE
);

CREATE TABLE core.dim_pais (
    pais              VARCHAR(40)  PRIMARY KEY,
    region            VARCHAR(30)  NOT NULL,
    es_mercado_local  BOOLEAN      NOT NULL
);

-- -----------------------------------------------------------------------------
-- Hechos
-- -----------------------------------------------------------------------------
-- Cabecera: una fila por factura.
CREATE TABLE core.fact_facturas (
    factura         VARCHAR(10)     PRIMARY KEY,
    cliente_id      BIGINT          NOT NULL REFERENCES core.dim_cliente (cliente_id),
    fecha           DATE            NOT NULL REFERENCES core.dim_fecha (fecha),
    fecha_hora      TIMESTAMP       NOT NULL,
    pais            VARCHAR(40)     NOT NULL REFERENCES core.dim_pais (pais),
    lineas          INTEGER         NOT NULL CHECK (lineas > 0),
    skus_distintos  INTEGER         NOT NULL CHECK (skus_distintos > 0),
    unidades        BIGINT,
    importe         NUMERIC(14, 2),
    es_devolucion   BOOLEAN         NOT NULL
);

-- Detalle: una fila por linea de factura. La fuente no trae un identificador de
-- linea, asi que se genera una clave sustituta.
CREATE TABLE core.fact_lineas (
    linea_id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    factura          VARCHAR(10)     NOT NULL REFERENCES core.fact_facturas (factura),
    sku              VARCHAR(20)     NOT NULL REFERENCES core.dim_producto (sku),
    cliente_id       BIGINT          NOT NULL REFERENCES core.dim_cliente (cliente_id),
    fecha            DATE            NOT NULL REFERENCES core.dim_fecha (fecha),
    fecha_hora       TIMESTAMP       NOT NULL,
    hora             SMALLINT        NOT NULL CHECK (hora BETWEEN 0 AND 23),
    pais             VARCHAR(40)     NOT NULL REFERENCES core.dim_pais (pais),
    cantidad         INTEGER         NOT NULL,
    precio_unitario  NUMERIC(12, 3)  NOT NULL,
    importe          NUMERIC(14, 2)  NOT NULL,
    tipo_linea       VARCHAR(10)     NOT NULL CHECK (tipo_linea IN ('producto', 'envio', 'ajuste', 'voucher', 'prueba')),
    naturaleza       VARCHAR(16)     NOT NULL CHECK (naturaleza IN ('venta', 'devolucion', 'baja_inventario')),
    precio_valido    BOOLEAN         NOT NULL,
    computa_ingreso  BOOLEAN         NOT NULL,
    -- Una devolucion es siempre una factura con prefijo C.
    CONSTRAINT fact_lineas_devolucion CHECK (naturaleza <> 'devolucion' OR factura LIKE 'C%'),
    CONSTRAINT fact_lineas_fecha_hora CHECK (fecha = fecha_hora::date)
);

-- Ventas netas de producto con cliente identificado: base de RFM, cohortes y CLV.
CREATE VIEW core.ventas_identificadas AS
SELECT *
FROM core.fact_lineas
WHERE computa_ingreso
  AND cliente_id <> -1
  AND naturaleza = 'venta';
