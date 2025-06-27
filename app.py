import streamlit as st
import pandas as pd
import re
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode
import plotly.express as px
# Agrega aquí otros imports necesarios para tu app, como la API de Google Drive

# --- Avance Semanal Hormigones ---
with tabs[3]:
    st.header("Avance Semanal Hormigones")
    # 1. Listar y ordenar archivos por fecha desde Google Drive
    archivos_fechas, service = cargar_archivos_semanales()
    # 2. Leer y procesar cada archivo
    lista_df = []
    for f, fecha in archivos_fechas:
        fh = download_file(service, f['id'])
        dfw = pd.read_csv(fh, sep='\t', header=1, dtype=str)
        dfw = dfw.dropna(how="all")
        dfw = dfw.rename(columns=lambda x: x.strip().replace('"', ''))
        if "VolumenHA" in dfw.columns:
            dfw["VolumenHA"] = pd.to_numeric(dfw["VolumenHA"].str.replace(",", ".", regex=False), errors='coerce')
        # Solo Hormigonado = 'Sí'
        dfw = dfw[dfw["Hormigonado"] == "Sí"]
        # Solo filas con Nivel y Elementos válidos
        dfw = dfw[dfw["Nivel"].notna() & (dfw["Nivel"].astype(str).str.strip() != "")]
        dfw = dfw[dfw["Elementos"].notna() & (dfw["Elementos"].astype(str).str.strip() != "")]
        # Agrupar por Nivel y Elementos
        resumen = dfw.groupby(["Nivel", "Elementos"])["VolumenHA"].sum().reset_index()
        resumen["Fecha"] = fecha
        lista_df.append(resumen)
    # 3. Unir todos los resultados
    if lista_df:
        df_semana = pd.concat(lista_df, ignore_index=True)
        # ... resto del código igual ...

# --- TRISEMANAL ---
with tabs[4]:
    st.header("TRISEMANAL")
    # 1. Listar y ordenar archivos por fecha desde Google Drive
    archivos_fechas, service = cargar_archivos_semanales()
    archivos_fechas = archivos_fechas[-2:]
    # 2. Leer y procesar cada archivo
    lista_df = []
    for f, fecha in archivos_fechas:
        fh = download_file(service, f['id'])
        dfw = pd.read_csv(fh, sep='\t', header=1, dtype=str)
        dfw = dfw.dropna(how="all")
        dfw = dfw.rename(columns=lambda x: x.strip().replace('"', ''))
        if "VolumenHA" in dfw.columns:
            dfw["VolumenHA"] = pd.to_numeric(dfw["VolumenHA"].str.replace(",", ".", regex=False), errors='coerce')
        # Solo Hormigonado = 'Sí'
        dfw = dfw[dfw["Hormigonado"] == "Sí"]
        # Solo filas con Nivel y Elementos válidos
        dfw = dfw[dfw["Nivel"].notna() & (dfw["Nivel"].astype(str).str.strip() != "")]
        dfw = dfw[dfw["Elementos"].notna() & (dfw["Elementos"].astype(str).str.strip() != "")]
        # Filtrar por FC_CON_TRISEMANAL = 'Semana 01' por defecto
        if "FC_CON_TRISEMANAL" in dfw.columns:
            dfw = dfw[dfw["FC_CON_TRISEMANAL"] == "Semana 01"]
        # Agrupar por Nivel y Elementos
        resumen = dfw.groupby(["Nivel", "Elementos"])["VolumenHA"].sum().reset_index()
        resumen["Fecha"] = fecha
        lista_df.append(resumen)
    # 3. Unir todos los resultados
    if lista_df:
        df_semana = pd.concat(lista_df, ignore_index=True)
        # ... resto del código igual ... 

# --- Cargar AO_GENERAL.txt desde Google Drive ---
def cargar_datos():
    service = get_drive_service()
    file_id = st.secrets["FILE_ID_GENERAL"]
    fh = download_file(service, file_id)
    df = pd.read_csv(fh, sep="\t", header=1, dtype=str)
    df = df.dropna(how="all")
    # Limpiar columnas y convertir tipos
    df = df.rename(columns=lambda x: x.strip().replace('"', ''))
    for col in ["VolumenHA", "AreaMoldaje", "Cuantia"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].str.replace(",", ".", regex=False), errors='coerce')
    if "FC_CON_FECHA EJECUCION" in df.columns:
        df["FC_CON_FECHA EJECUCION"] = pd.to_datetime(df["FC_CON_FECHA EJECUCION"], dayfirst=True, errors='coerce')
    return df

# --- Cargar archivos semanales desde Google Drive ---
def cargar_archivos_semanales():
    service = get_drive_service()
    folder_id = st.secrets["FOLDER_ID_SEMANAL"]
    files = list_files_in_folder(service, folder_id)
    # Filtrar solo archivos *_AO_GENERAL.txt
    archivos = [f for f in files if f['name'].endswith('_AO_GENERAL.txt')]
    def extraer_fecha(nombre):
        m = re.match(r"(\d{2}-\d{2}-\d{4})_AO_GENERAL.txt", nombre)
        return pd.to_datetime(m.group(1), dayfirst=True) if m else None
    archivos_fechas = [(f, extraer_fecha(f['name'])) for f in archivos]
    archivos_fechas = sorted([x for x in archivos_fechas if x[1] is not None], key=lambda x: x[1])
    return archivos_fechas, service 