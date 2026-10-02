-- titulo: Las restricciones protegen el almacén
-- descripcion: En PostgreSQL el esquema en estrella tiene claves foráneas: una línea de venta hacia un producto que no existe en dim_producto se rechaza (la sentencia se ejecuta en una transacción que se revierte).
INSERT INTO core.fact_lineas
    (factura, sku, cliente_id, fecha, fecha_hora, hora, pais, cantidad, precio_unitario,
     importe, tipo_linea, naturaleza, precio_valido, computa_ingreso)
VALUES ('489434', 'NO-EXISTE', -1, '2009-12-01', '2009-12-01 07:45', 7, 'United Kingdom',
        1, 1.00, 1.00, 'producto', 'venta', TRUE, TRUE);
