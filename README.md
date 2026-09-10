# Sistema de Revisión Venta

App en Streamlit que reemplaza el Excel manual de revisión de venta. Cruza:

1. **Preventa** (SKU Truck) — CSV o Excel exportado del sistema de pedidos.
2. **Stock CD** (SAP, centros terminación 06: 2306, 5006, 7106, 8006, 9006).
3. **Stock CL** (SAP, centros terminación 07: 2307, 5007, 7107, 8007, 9007).

Y genera automáticamente:

- Tabla dinámica de venta por SKU Truck / SKU SAP / Descripción.
- Cruce con Stock CD y Stock CL (sumando todos los centros/bodegas de cada tipo).
- **Abastecimiento** = Stock CD − Venta.
- **Faltante Stock**:
  - `No` → Abastecimiento ≥ 0 (alcanza el stock CD).
  - `Sí` → Abastecimiento < 0 pero hay unidades en Stock CL.
  - `Quiebre` → Abastecimiento < 0 y no hay stock en CL.
- Exportación a Excel con colores según el estado.

## Base de códigos Truck ↔ SAP

El archivo `bbdd_codigos.csv` viene incluido en la app (extraído de tu hoja
"BBDD CODIGOS"), por lo que **no es necesario subirlo cada vez**. Cuando
tengan códigos nuevos, basta con reemplazar ese archivo en el repositorio
(mismas columnas: `CODIGO_TRK`, `CODIGO_SAP`) y volver a desplegar.

## Cómo correrla en tu computador

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Cómo publicarla gratis (igual que tu app de Reabasto de Cajas)

1. Crea un repositorio en GitHub y sube estos 4 archivos: `app.py`,
   `bbdd_codigos.csv`, `requirements.txt`, `README.md`.
2. Entra a [share.streamlit.io](https://share.streamlit.io), conecta tu
   cuenta de GitHub y selecciona el repositorio.
3. Indica `app.py` como archivo principal y despliega.
4. Comparte el link que te entrega Streamlit con tus compañeros — solo
   necesitan subir los 3 archivos y apretar el botón.

## Notas sobre los archivos que se suben

- Los archivos de Stock deben tener las columnas `Material`, `Centro` y
  `Libre utilización` (formato estándar de la transacción MB52/COQ de SAP).
- El archivo de Preventa debe tener las columnas `SKU`, `Descripcion` y
  `Cantidad (en cajas)`.
- Si un SKU Truck no está en la base de códigos, queda marcado como
  `SIN MAPEO` y no se le puede calcular stock — conviene revisarlo e
  incorporarlo a `bbdd_codigos.csv`.
