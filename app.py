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
# ESTILOS (tema oscuro, acento rojo, igual línea que Reabasto de Cajas)
# ------------------------------------------------------------------
st.markdown(
    """
    <style>
    .stApp { background-color: #0e1117; }
    div.stButton > button {
        background-color: #ff4b4b;
        color: white;
        font-weight: 700;
        font-size: 1.1rem;
        padding: 0.75rem 0;
        border: none;
        border-radius: 8px;
        width: 100%;
    }
    div.stButton > button:hover { background-color: #ff6b6b; color: white; }
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
    # normalizar nombres de columnas esperadas
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
        # Si el archivo trae centros que no corresponden al tipo esperado, avisamos
        # pero igual filtramos y seguimos con los válidos.
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
        if stock_cl > 0:
            return "Sí"
        else:
            return "Quiebre"


def construir_tabla(df_venta, df_stock_cd, df_stock_cl, bbdd):
    # 1. Cruzar venta (truck) con BBDD para obtener SKU SAP
    tabla = df_venta.merge(bbdd, left_on="SKU_TRUCK", right_on="CODIGO_TRK", how="left")
    tabla["SKU_SAP"] = tabla["CODIGO_SAP"]
    tabla.loc[tabla["SKU_SAP"].isna(), "SKU_SAP"] = "SIN MAPEO"
    tabla = tabla.drop(columns=["CODIGO_TRK", "CODIGO_SAP"])

    # 2. Cruzar con Stock CD y Stock CL por SKU SAP
    tabla = tabla.merge(df_stock_cd, on="SKU_SAP", how="left")
    tabla = tabla.merge(df_stock_cl, on="SKU_SAP", how="left")
    tabla["STOCK_CD"] = tabla["STOCK_CD"].fillna(0)
    tabla["STOCK_CL"] = tabla["STOCK_CL"].fillna(0)

    # 3. Calcular abastecimiento y faltante
    tabla["ABASTECIMIENTO"] = tabla["STOCK_CD"] - tabla["VENTA"]
    tabla["FALTANTE_STOCK"] = tabla.apply(calcular_faltante, axis=1)

    # 4. Orden final de columnas
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


def to_excel_bytes(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Revision Venta")
        workbook = writer.book
        worksheet = writer.sheets["Revision Venta"]

        header_fmt = workbook.add_format(
            {"bold": True, "bg_color": "#1f2630", "font_color": "white", "border": 1}
        )
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_fmt)
            worksheet.set_column(col_num, col_num, 18)

        fmt_si = workbook.add_format({"bg_color": "#fff3b0", "font_color": "#7a5c00"})
        fmt_no = workbook.add_format({"bg_color": "#c6efce", "font_color": "#006100"})
        fmt_quiebre = workbook.add_format({"bg_color": "#ffc7ce", "font_color": "#9c0006"})

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
    color = ""
    if row["FALTANTE_STOCK"] == "Quiebre":
        color = "background-color: #4d1a1a"
    elif row["FALTANTE_STOCK"] == "Sí":
        color = "background-color: #4d4419"
    elif row["FALTANTE_STOCK"] == "No":
        color = "background-color: #1a4d20"
    return [color] * len(row)


# ------------------------------------------------------------------
# INTERFAZ
# ------------------------------------------------------------------
st.markdown("## 📊 Sistema de Revisión Venta")
st.markdown(
    "Cruza **Preventa (SKU Truck)**, **Stock CD** y **Stock CL** contra la base de "
    "códigos Truck ↔ SAP, y genera la tabla de **abastecimiento y faltante de stock** "
    "lista para revisar."
)

st.markdown("---")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("### 1. Preventa")
    st.caption("Archivo con SKU **Truck** (CSV o Excel exportado del sistema de pedidos)")
    file_preventa = st.file_uploader(
        "Sube Preventa:", type=["csv", "xlsx", "xls"], key="preventa"
    )

with col2:
    st.markdown("### 2. Stock CD")
    st.caption("Centros terminación **06** (2306, 5006, 7106, 8006, 9006)")
    file_stock_cd = st.file_uploader(
        "Sube Stock CD:", type=["csv", "xlsx", "xls"], key="stock_cd"
    )

with col3:
    st.markdown("### 3. Stock CL")
    st.caption("Centros terminación **07** (2307, 5007, 7107, 8007, 9007)")
    file_stock_cl = st.file_uploader(
        "Sube Stock CL:", type=["csv", "xlsx", "xls"], key="stock_cl"
    )

st.markdown("---")

procesar = st.button("🚀 Procesar Revisión de Venta")

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
    m1.metric("Total Venta (cajas)", f"{total_venta:,}".replace(",", "."))
    m2.metric("SKU sin faltante", total_no)
    m3.metric("SKU con faltante (hay CL)", total_si)
    m4.metric("SKU en quiebre", total_quiebre)

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
    )
