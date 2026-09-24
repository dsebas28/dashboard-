# Dashboard comercial · Online Retail II

Análisis end-to-end sobre **1.067.371 transacciones reales** de un minorista
online británico: desde el fichero crudo hasta un tablero interactivo, pasando
por un almacén dimensional en DuckDB con el SQL versionado.

No es un dataset de juguete ni datos sintéticos. Son las ventas reales de una
empresa de artículos de regalo del Reino Unido entre el **1 de diciembre de 2009
y el 9 de diciembre de 2011**, publicadas por el *UCI Machine Learning
Repository*, con toda la suciedad que eso implica: facturas duplicadas,
devoluciones, ajustes contables y un cuarto de las líneas sin identificar al
cliente.

---

## El hallazgo que justifica el proyecto

El libro de Excel original trae una hoja por ejercicio. Sus rangos **se solapan**:

| Hoja | Desde | Hasta |
|---|---|---|
| `Year 2009-2010` | 2009-12-01 | **2010-12-09** |
| `Year 2010-2011` | **2010-12-01** | 2011-12-09 |

Del 1 al 9 de diciembre de 2010 las mismas **22.523 líneas están en las dos
hojas**: £377.488 contados dos veces. Cargar el fichero con un `concat` directo
deja diciembre de 2010 en £1.126.445 cuando la cifra real es £748.957: un
**50,4 % de facturación inflada** en ese mes, y el doble exacto en los nueve
días afectados.

El pipeline lo detecta, lo documenta y lo corrige, y el propio tablero publica
la traza completa de qué se descartó y por qué en su pestaña *Modelo y calidad
del dato*. Un tablero que no se puede auditar no debería usarse para decidir.

---

## Qué dicen los datos

| Indicador | Valor |
|---|---|
| Facturación neta | **£20,09 M** |
| Facturas | 39.678 |
| Clientes identificados | 5.854 en 43 países |
| Referencias con venta | 4.899 SKU |
| Ticket medio | £506 |
| Tasa de devolución | 3,64 % (£731.978) |

**Cuatro conclusiones de negocio:**

1. **El negocio es mayorista disfrazado de tienda online.** El 20 % de los
   clientes genera el **77 % de la facturación**, y solo 1.324 «Campeones»
   —el 22,6 % del padrón— aportan el 68,7 %. Perder veinte cuentas duele más
   que perder mil compradores ocasionales.
2. **La estacionalidad manda.** Septiembre a diciembre son 4 de 12 meses pero
   concentran el **46,7 %** de la facturación. Noviembre de 2011 cerró en
   £1,50 M frente a los £521 K de febrero: un factor de 2,9.
3. **La retención se cae de golpe.** Solo el **21,1 %** de los clientes vuelve
   a comprar al mes siguiente de darse de alta. Lo que sobrevive al primer mes,
   sin embargo, aguanta bien: las cohortes de 2010 siguen activas un año después.
4. **Hay afinidades explotables.** Las tazas *Green Regency* y *Roses Regency*
   aparecen juntas en 1.034 facturas, con un **lift de 21,2**: veintiún veces
   más de lo que explicaría el azar. Son familias de producto que se venden
   como colección, no como unidad.

> Dos advertencias que el tablero señala solo: diciembre de 2011 llega solo
> hasta el día 9, así que aparece atenuado y no debe leerse como una caída; y
> el 22,8 % de las líneas no identifica al cliente, por lo que quedan fuera de
> RFM y cohortes aunque sí computen como ingreso.

---

## Arquitectura

```
Excel (UCI)  ──►  Parquet  ──►  DuckDB  ──►  Streamlit
   45 MB          ingesta      almacén       tablero
                              dimensional
```

```
stg  ── limpieza y tipado
 │    retail_crudo · descripcion_canonica
 │
core ── modelo dimensional (esquema estrella)
 │    fact_lineas ──┬── dim_fecha     calendario continuo
 │    fact_facturas ├── dim_cliente   (-1 = no identificado)
 │                  ├── dim_producto  descripción canónica
 │                  └── dim_pais      región, mercado local
 │
mart ── capa publicada
      kpis · ventas_mensuales · rfm · cohortes · pareto_clientes
      productos · cesta · resumen_paises · calidad_dato
```

El hecho está al **grano de línea de factura** y conserva *todas* las líneas,
incluidas devoluciones y ajustes: filtrar es responsabilidad de cada consulta,
no de la carga. Perder la trazabilidad de una devolución impediría calcular la
tasa de devolución, que es uno de los KPI del tablero.

**Las dos capas se usan para cosas distintas.** `mart.*` es el batch publicado.
Pero el tablero consulta `core.*` **en vivo**: RFM, cohortes y clasificación ABC
se recalculan dentro del periodo que elija el usuario, porque «cliente reciente»
significa algo distinto según la ventana que se mire. Las ocho consultas
interactivas responden por debajo de **270 ms** sobre el millón de líneas.

---

## Reglas de limpieza

Cada una responde a un problema encontrado perfilando los datos, no a una
receta copiada. El impacto de cada paso está cuantificado:

| Etapa | Filas | Facturación |
|---|---|---|
| Excel original | 1.067.371 | £19,29 M |
| Sin solape entre hojas | 1.044.848 | £18,91 M |
| Sin duplicados exactos | 1.033.036 | £18,86 M |

Además:

- **Descripción canónica.** 1.212 SKU arrastraban más de un nombre. Se toma la
  variante más frecuente, descartando anotaciones de almacén (`check`, `found`,
  `damages`, `?`).
- **Clasificación de línea.** El catálogo mezcla producto con códigos de
  servicio. No se borran, se **etiquetan** (`producto`, `envio`, `ajuste`,
  `voucher`, `prueba`): si no, los −£260 K de `AMAZONFEE` o los −£147 K de
  `Adjust bad debt` contaminan cualquier KPI de ventas.
- **Naturaleza de la línea.** Las facturas con prefijo `C` son notas de crédito,
  pero hay 3.457 líneas negativas *sin* ese prefijo: son bajas de inventario
  (roturas, pérdidas) que el almacén registra como ventas negativas. Se separan.
- **Cliente centinela.** El cliente no identificado recibe la clave `-1` en vez
  de `NULL`, para que ningún `JOIN` del tablero pierda filas en silencio.

El almacén se valida al construirse: integridad referencial de las tres
dimensiones, ausencia de nulos en importes, rango de fechas y el invariante del
solape. Si algo falla, la construcción se detiene.

---

## Decisiones de visualización

- Paleta **validada para daltonismo**: separación CVD ΔE 9,1 en el peor par
  adyacente, comprobada con script, no a ojo.
- El **color sigue a la entidad**, nunca al ranking: filtrar mercados no
  repinta las regiones que quedan.
- **Un solo eje por panel.** Donde había dos magnitudes de escala distinta se
  usan dos gráficos, no dos escalas.
- Magnitud continua (mapas de calor) con **rampa de un solo tono**; la escala
  ordenada A/B/C con rampa ordinal; nunca arcoíris.
- Toda vista con color tiene su **tabla equivalente**, porque tres tonos de la
  paleta quedan por debajo de 3:1 de contraste sobre la superficie clara.

---

## Puesta en marcha

```bash
git clone <este-repo>
cd dashboard-v3
pip install -r requirements.txt

python src/ingest.py           # descarga UCI y convierte a Parquet (~3 min)
python src/build_warehouse.py  # construye y valida el almacén (~10 s)
streamlit run app.py
```

Los datos no se versionan: `src/ingest.py` los descarga de la fuente original y
el almacén se reconstruye entero en diez segundos. El repositorio guarda el
**código y el modelo**, que es lo que tiene valor.

---

## Estructura

```
├── app.py                      Tablero Streamlit (5 pestañas)
├── src/
│   ├── ingest.py               Descarga UCI → Parquet
│   ├── build_warehouse.py      Ejecuta el SQL y valida el resultado
│   ├── datos.py                Consultas parametrizadas (filtros en vivo)
│   └── graficos.py             Figuras Plotly, paleta y especificaciones
├── sql/
│   ├── 01_staging.sql          Limpieza, con cada regla documentada
│   ├── 02_dimensiones.sql      dim_fecha · dim_cliente · dim_producto · dim_pais
│   ├── 03_hechos.sql           fact_lineas · fact_facturas
│   └── marts/                  KPIs · evolución · RFM · cohortes · ABC · cesta
└── notebooks/
    └── 01_exploracion.ipynb    El perfilado que originó las reglas de limpieza
```

---

## Stack

`Python 3.14` · `DuckDB 1.5` · `pandas 3.0` · `Streamlit 1.56` · `Plotly 6.7`

DuckDB en lugar de un servidor de base de datos porque el almacén es un único
archivo de 38 MB: quien clone el repositorio ejecuta dos comandos y tiene el
modelo entero funcionando, sin levantar contenedores ni configurar credenciales.

---

## Fuente

Chen, D. (2019). *Online Retail II* [Dataset]. UCI Machine Learning Repository.
<https://doi.org/10.24432/C5CG6D> · Licencia CC BY 4.0
