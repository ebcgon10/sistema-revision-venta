import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import os

# ------------------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA
# ------------------------------------------------------------------
st.set_page_config(
    page_title="Sistema de Revisión Venta",
    page_icon="📊",
    layout="wide",
)

# ------------------------------------------------------------------
# PALETA DE COLORES CCU (Manual de Identidad de Marca CCU, pág. 57)
# ------------------------------------------------------------------
COLOR_369C = "#64A70B"   # Verde - Primario - "Sin Faltante"
COLOR_554C = "#205C40"   # Verde oscuro - Primario - "Total Venta"
COLOR_1235C = "#FFB81C"  # Ámbar - Secundario - "Con Faltante"
COLOR_7461C = "#007DBA"  # Azul - Secundario - Texto tabla
COLOR_1945C = "#A6093D"  # Vino - Secundario - "En Quiebre"
COLOR_BLANCO = "#FFFFFF"
COLOR_NEGRO = "#000000"

# ------------------------------------------------------------------
# ESTILOS (tema oscuro de la app, acento rojo, tarjetas y tabla en blanco/marca CCU)
# ------------------------------------------------------------------
st.markdown(
    f"""
    <style>
    .stApp {{ background-color: #0e1117; }}
    div.stButton > button {{
        background-color: #ff4b4b;
        color: white;
        font-weight: 700;
        font-size: 1.1rem;
        padding: 0.75rem 0;
        border: none;
        border-radius: 8px;
        width: 100%;
    }}
    div.stButton > button:hover {{ background-color: #ff6b6b; color: white; }}

    .ccu-metric-card {{
        background-color: {COLOR_BLANCO};
        border-radius: 10px;
        padding: 1rem 1rem 0.8rem 1rem;
        text-align: left;
        height: 100%;
    }}
    .ccu-metric-label {{
        font-size: 0.85rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.02em;
        margin-bottom: 0.3rem;
    }}
    .ccu-metric-value {{
        font-size: 2.1rem;
        font-weight: 800;
        line-height: 1.1;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BBDD_PATH = os.path.join(BASE_DIR, "bbdd_codigos.csv")

CENTROS_CD = {"2306", "5006", "7106", "8006", "9006"}  # terminación 06
CENTROS_CL = {"2307", "5007", "7107", "8007", "9007"}  # terminación 07


# ------------------------------------------------------------------
# FUNCIONES DE CARGA
# ------------------------------------------------------------------
def leer_archivo(uploaded_file):
    """Lee CSV o Excel (cualquiera de las dos extensiones) y devuelve un DataFrame."""
    nombre = uploaded_file.name.lower()
    if nombre.endswith(".csv"):
        return pd.read_csv(uploaded_file, sep=None, engine="python", dtype=str)
    else:
        return pd.read_excel(uploaded_file, sheet_name=0, dtype=str)


@st.cache_data
def cargar_bbdd_codigos():
    bbdd = pd.read_csv(BBDD_PATH, dtype=str)
    bbdd["CODIGO_TRK"] = bbdd["CODIGO_TRK"].astype(str).str.strip()
    bbdd["CODIGO_SAP"] = bbdd["CODIGO_SAP"].astype(str).str.strip()
    bbdd = bbdd.drop_duplicates(subset=["CODIGO_TRK"])
    return bbdd


def procesar_preventa(df_preventa):
    """Agrupa la preventa (SKU truck) sumando Cantidad (en cajas)."""
    df = df_preventa.copy()
    df.columns = [c.strip() for c in df.columns]
    col_sku = "SKU"
    col_desc = "Descripcion" if "Descripcion" in df.columns else "Descripción"
    col_cant = "Cantidad (en cajas)"

    df[col_sku] = df[col_sku].astype(str).str.strip()
    df[col_cant] = pd.to_numeric(df[col_cant], errors="coerce").fillna(0)

    agrupado = (
        df.groupby(col_sku, as_index=False)
        .agg({col_desc: "first", col_cant: "sum"})
        .rename(columns={col_sku: "SKU_TRUCK", col_desc: "DESCRIPCION", col_cant: "VENTA"})
    )
    return agrupado


def procesar_stock(df_stock, centros_validos, nombre_stock):
    """Suma 'Libre utilización' agrupado por Material, validando que el centro
    corresponda al tipo de stock (CD termina en 06, CL termina en 07)."""
    df = df_stock.copy()
    df.columns = [c.strip() for c in df.columns]

    col_mat = "Material"
    col_centro = "Centro"
    col_libre = "Libre utilización"

    df[col_mat] = df[col_mat].astype(str).str.strip()
    df[col_centro] = df[col_centro].astype(str).str.strip()
    df[col_libre] = pd.to_numeric(df[col_libre], errors="coerce").fillna(0)

    centros_encontrados = set(df[col_centro].unique())
    centros_invalidos = centros_encontrados - centros_validos
    if centros_invalidos and not centros_encontrados.issubset(centros_validos):
        df = df[df[col_centro].isin(centros_validos)]

    agrupado = (
        df.groupby(col_mat, as_index=False)[col_libre]
        .sum()
        .rename(columns={col_mat: "SKU_SAP", col_libre: nombre_stock})
    )
    return agrupado, centros_invalidos


def calcular_faltante(row):
    abastecimiento = row["ABASTECIMIENTO"]
    stock_cl = row["STOCK_CL"]
    if abastecimiento >= 0:
        return "No"
    else:
        return "Sí" if stock_cl > 0 else "Quiebre"


def construir_tabla(df_venta, df_stock_cd, df_stock_cl, bbdd):
    tabla = df_venta.merge(bbdd, left_on="SKU_TRUCK", right_on="CODIGO_TRK", how="left")
    tabla["SKU_SAP"] = tabla["CODIGO_SAP"]
    tabla.loc[tabla["SKU_SAP"].isna(), "SKU_SAP"] = "SIN MAPEO"
    tabla = tabla.drop(columns=["CODIGO_TRK", "CODIGO_SAP"])

    tabla = tabla.merge(df_stock_cd, on="SKU_SAP", how="left")
    tabla = tabla.merge(df_stock_cl, on="SKU_SAP", how="left")
    tabla["STOCK_CD"] = tabla["STOCK_CD"].fillna(0)
    tabla["STOCK_CL"] = tabla["STOCK_CL"].fillna(0)

    tabla["ABASTECIMIENTO"] = tabla["STOCK_CD"] - tabla["VENTA"]
    tabla["FALTANTE_STOCK"] = tabla.apply(calcular_faltante, axis=1)

    tabla = tabla[
        [
            "SKU_TRUCK",
            "SKU_SAP",
            "DESCRIPCION",
            "VENTA",
            "STOCK_CD",
            "STOCK_CL",
            "ABASTECIMIENTO",
            "FALTANTE_STOCK",
        ]
    ]
    tabla = tabla.sort_values("VENTA", ascending=False).reset_index(drop=True)
    return tabla


def to_excel_bytes(df, nombre_hoja="Revision Venta"):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name=nombre_hoja)
        workbook = writer.book
        worksheet = writer.sheets[nombre_hoja]

        header_fmt = workbook.add_format(
            {"bold": True, "bg_color": COLOR_7461C, "font_color": "white", "border": 1}
        )
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_fmt)
            worksheet.set_column(col_num, col_num, 18)

        if "FALTANTE_STOCK" in df.columns:
            fmt_si = workbook.add_format({"bg_color": COLOR_1235C, "font_color": "#3a2a00"})
            fmt_no = workbook.add_format({"bg_color": COLOR_369C, "font_color": "white"})
            fmt_quiebre = workbook.add_format({"bg_color": COLOR_1945C, "font_color": "white"})

            n_rows = len(df)
            col_idx = df.columns.get_loc("FALTANTE_STOCK")
            worksheet.conditional_format(
                1, col_idx, n_rows, col_idx,
                {"type": "text", "criteria": "containing", "value": "Sí", "format": fmt_si},
            )
            worksheet.conditional_format(
                1, col_idx, n_rows, col_idx,
                {"type": "text", "criteria": "containing", "value": "No", "format": fmt_no},
            )
            worksheet.conditional_format(
                1, col_idx, n_rows, col_idx,
                {"type": "text", "criteria": "containing", "value": "Quiebre", "format": fmt_quiebre},
            )
    return output.getvalue()


def estilo_filas(row):
    """Fondo por estado (paleta CCU) + texto legible según el color de fondo."""
    if row["FALTANTE_STOCK"] == "Quiebre":
        return [f"background-color: {COLOR_1945C}; color: white"] * len(row)
    elif row["FALTANTE_STOCK"] == "Sí":
        return [f"background-color: {COLOR_1235C}; color: #3a2a00"] * len(row)
    elif row["FALTANTE_STOCK"] == "No":
        return [f"background-color: {COLOR_369C}; color: white"] * len(row)
    return [f"background-color: white; color: {COLOR_7461C}"] * len(row)


# ------------------------------------------------------------------
# INTERFAZ
# ------------------------------------------------------------------
st.markdown("## 📊 Sistema de Revisión Venta")
st.markdown(
    "**Cruce y Análisis de Abastecimiento (Preventa vs. Inventario CD-CL):** "
    "Conciliación sistemática entre la demanda proyectada por preventa y las "
    "existencias físicas e intangibles registradas en los Centros de Distribución "
    "(CD) y Logísticos (CL), con el propósito de optimizar el plan de abastecimiento, "
    "identificar brechas de inventario y mitigar de forma proactiva el riesgo de "
    "faltantes y quiebres de stock."
)

st.markdown("---")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("### 1. Módulo de Preventa")
    st.caption(
        "Carga de Datos de Demanda: importación del reporte consolidado de "
        "preventa, exportado directamente desde el sistema operacional Truck."
    )
    file_preventa = st.file_uploader(
        "Sube Preventa:", type=["csv", "xlsx", "xls"], key="preventa"
    )

with col2:
    st.markdown("### 2. Módulo de Inventario CD")
    st.caption(
        "Carga de Stock Centros Coquimbo: importación del informe de existencias "
        "extraído mediante la transacción MB52 en SAP, correspondiente a los "
        "Centros Operativos de Coquimbo (terminación 06)."
    )
    file_stock_cd = st.file_uploader(
        "Sube Stock CD:", type=["csv", "xlsx", "xls"], key="stock_cd"
    )

with col3:
    st.markdown("### 3. Módulo de Inventario CL")
    st.caption(
        "Carga de Stock Centros Coquimext: importación del informe de existencias "
        "extraído mediante la transacción MB52 en SAP, correspondiente a los "
        "Centros Operativos de Coquimext (terminación 07)."
    )
    file_stock_cl = st.file_uploader(
        "Sube Stock CL:", type=["csv", "xlsx", "xls"], key="stock_cl"
    )

st.markdown("---")

procesar = st.button("🚀 Procesar Revisión de Venta", use_container_width=True)

if procesar:
    if not (file_preventa and file_stock_cd and file_stock_cl):
        st.error("⚠️ Debes subir los 3 archivos: Preventa, Stock CD y Stock CL.")
    else:
        with st.spinner("Procesando..."):
            try:
                bbdd = cargar_bbdd_codigos()

                df_preventa_raw = leer_archivo(file_preventa)
                df_stock_cd_raw = leer_archivo(file_stock_cd)
                df_stock_cl_raw = leer_archivo(file_stock_cl)

                df_venta = procesar_preventa(df_preventa_raw)
                df_stock_cd, centros_raros_cd = procesar_stock(
                    df_stock_cd_raw, CENTROS_CD, "STOCK_CD"
                )
                df_stock_cl, centros_raros_cl = procesar_stock(
                    df_stock_cl_raw, CENTROS_CL, "STOCK_CL"
                )

                tabla = construir_tabla(df_venta, df_stock_cd, df_stock_cl, bbdd)

                st.session_state["tabla_resultado"] = tabla
                st.session_state["centros_raros_cd"] = centros_raros_cd
                st.session_state["centros_raros_cl"] = centros_raros_cl

            except KeyError as e:
                st.error(
                    f"⚠️ No se encontró la columna {e} en uno de los archivos. "
                    "Revisa que los archivos subidos correspondan al tipo correcto "
                    "(Preventa / Stock CD / Stock CL) y que no hayan sido modificados."
                )
            except Exception as e:
                st.error(f"⚠️ Ocurrió un error procesando los archivos: {e}")

if "tabla_resultado" in st.session_state:
    tabla = st.session_state["tabla_resultado"]

    if st.session_state.get("centros_raros_cd"):
        st.warning(
            f"El archivo de Stock CD contiene centros no reconocidos como CD (06): "
            f"{sorted(st.session_state['centros_raros_cd'])}. Fueron excluidos del cálculo."
        )
    if st.session_state.get("centros_raros_cl"):
        st.warning(
            f"El archivo de Stock CL contiene centros no reconocidos como CL (07): "
            f"{sorted(st.session_state['centros_raros_cl'])}. Fueron excluidos del cálculo."
        )

    sin_mapeo = (tabla["SKU_SAP"] == "SIN MAPEO").sum()
    if sin_mapeo > 0:
        st.warning(
            f"⚠️ {sin_mapeo} SKU(s) Truck no se encontraron en la base de códigos "
            "Truck ↔ SAP y quedaron marcados como 'SIN MAPEO'. No fue posible cruzar su stock."
        )

    total_venta = int(tabla["VENTA"].sum())
    total_quiebre = int((tabla["FALTANTE_STOCK"] == "Quiebre").sum())
    total_si = int((tabla["FALTANTE_STOCK"] == "Sí").sum())
    total_no = int((tabla["FALTANTE_STOCK"] == "No").sum())

    m1, m2, m3, m4 = st.columns(4)
    tarjetas = [
        (m1, "Total Venta (cajas)", f"{total_venta:,}".replace(",", "."), COLOR_554C),
        (m2, "SKU sin faltante", str(total_no), COLOR_369C),
        (m3, "SKU con faltante (hay CL)", str(total_si), COLOR_1235C),
        (m4, "SKU en quiebre", str(total_quiebre), COLOR_1945C),
    ]
    for col, label, valor, color in tarjetas:
        with col:
            st.markdown(
                f"""
                <div class="ccu-metric-card">
                    <div class="ccu-metric-label" style="color:{color};">{label}</div>
                    <div class="ccu-metric-value" style="color:{color};">{valor}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("")

    # --------------------------------------------------------------
    # Tabla rápida: productos a traer desde CL + sin mapeo
    # --------------------------------------------------------------
    a_traer = tabla[tabla["FALTANTE_STOCK"] == "Sí"].copy()
    a_traer["MOTIVO"] = "Con faltante — traer desde CL"
    sin_mapeo_tabla = tabla[tabla["SKU_SAP"] == "SIN MAPEO"].copy()
    sin_mapeo_tabla["MOTIVO"] = "Sin mapeo — revisar código"
    tabla_rapida = pd.concat([a_traer, sin_mapeo_tabla], ignore_index=True)

    st.markdown("### 🔎 Productos a traer y sin mapeo")
    st.caption(
        "Vista rápida solo con los SKU que requieren traslado desde CL y los que "
        "no se pudieron mapear — para agilizar la búsqueda antes de revisar la tabla completa."
    )
    if len(tabla_rapida) > 0:
        st.dataframe(
            tabla_rapida.style.apply(estilo_filas, axis=1).format(
                {"VENTA": "{:.0f}", "STOCK_CD": "{:.0f}", "STOCK_CL": "{:.0f}", "ABASTECIMIENTO": "{:.0f}"}
            ),
            use_container_width=True,
            height=300,
        )
        excel_rapida = to_excel_bytes(tabla_rapida, nombre_hoja="A Traer y Sin Mapeo")
        st.download_button(
            label="⬇️ Descargar Excel (a traer / sin mapeo)",
            data=excel_rapida,
            file_name="Productos_A_Traer_Sin_Mapeo.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="descarga_rapida",
        )
    else:
        st.success("No hay productos con faltante ni sin mapeo. 🎉")

    st.markdown("---")

    st.markdown("### Resultado — Revisión de Venta")
    st.dataframe(
        tabla.style.apply(estilo_filas, axis=1).format(
            {"VENTA": "{:.0f}", "STOCK_CD": "{:.0f}", "STOCK_CL": "{:.0f}", "ABASTECIMIENTO": "{:.0f}"}
        ),
        use_container_width=True,
        height=600,
    )

    excel_bytes = to_excel_bytes(tabla)
    st.download_button(
        label="⬇️ Descargar Excel",
        data=excel_bytes,
        file_name="Revision_Venta.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="descarga_completa",
    )
