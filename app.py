import streamlit as st
import pandas as pd
import numpy as np
import re
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode
import plotly.express as px
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io
import json

# Configuración de la página
st.set_page_config(
    page_title="Dashboard Control de Avance",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Título principal
st.title("📊 Dashboard Control de Avance - Hormigones, Moldajes y Enfierraduras")

# Configuración de Google Drive
@st.cache_resource
def get_drive_service():
    """Obtiene el servicio de Google Drive usando las credenciales"""
    try:
        # Crear credenciales desde los secretos
        creds_dict = st.secrets["GOOGLE_CREDENTIALS"]
        creds = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        service = build('drive', 'v3', credentials=creds)
        return service
    except Exception as e:
        st.error(f"Error al conectar con Google Drive: {e}")
        return None

def download_file(service, file_id):
    """Descarga un archivo de Google Drive"""
    try:
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        fh.seek(0)
        return fh
    except Exception as e:
        st.error(f"Error al descargar archivo: {e}")
        return None

def list_files_in_folder(service, folder_id):
    """Lista archivos en una carpeta de Google Drive"""
    try:
        results = service.files().list(
            q=f"'{folder_id}' in parents",
            pageSize=1000,
            fields="files(id, name, modifiedTime)"
        ).execute()
        return results.get('files', [])
    except Exception as e:
        st.error(f"Error al listar archivos: {e}")
        return []

# Cargar datos desde Google Drive
@st.cache_data(ttl=3600)  # Cache por 1 hora
def cargar_datos():
    """Carga el archivo AO_GENERAL.txt desde Google Drive"""
    service = get_drive_service()
    if not service:
        return None
    
    try:
        file_id = st.secrets["FILE_ID_GENERAL"]
        fh = download_file(service, file_id)
        if not fh:
            return None
            
        df = pd.read_csv(fh, sep="\t", header=1, dtype=str)
        df = df.dropna(how="all")
        
        # Limpiar columnas
        df = df.rename(columns=lambda x: x.strip().replace('"', ''))
        
        # Convertir tipos de datos
        for col in ["VolumenHA", "AreaMoldaje", "Cuantia"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].str.replace(",", ".", regex=False), errors='coerce')
        
        if "FC_CON_FECHA EJECUCION" in df.columns:
            df["FC_CON_FECHA EJECUCION"] = pd.to_datetime(
                df["FC_CON_FECHA EJECUCION"], 
                dayfirst=True, 
                errors='coerce'
            )
        
        return df
    except Exception as e:
        st.error(f"Error al cargar datos: {e}")
        return None

@st.cache_data(ttl=3600)  # Cache por 1 hora
def cargar_archivos_semanales():
    """Carga archivos semanales desde Google Drive"""
    service = get_drive_service()
    if not service:
        return [], None
    
    try:
        folder_id = st.secrets["FOLDER_ID_SEMANAL"]
        files = list_files_in_folder(service, folder_id)
        
        # Filtrar solo archivos *_AO_GENERAL.txt
        archivos = [f for f in files if f['name'].endswith('_AO_GENERAL.txt')]
        
        def extraer_fecha(nombre):
            m = re.match(r"(\d{2}-\d{2}-\d{4})_AO_GENERAL.txt", nombre)
            return pd.to_datetime(m.group(1), dayfirst=True) if m else None
        
        archivos_fechas = [(f, extraer_fecha(f['name'])) for f in archivos]
        archivos_fechas = sorted(
            [x for x in archivos_fechas if x[1] is not None], 
            key=lambda x: x[1]
        )
        
        return archivos_fechas, service
    except Exception as e:
        st.error(f"Error al cargar archivos semanales: {e}")
        return [], None

def crear_tabla_interactiva(df, titulo, columna_volumen="VolumenHA"):
    """Crea una tabla interactiva con AgGrid"""
    if df.empty:
        st.warning("No hay datos para mostrar")
        return
    
    # Solo mostrar filas con Nivel no vacío
    df_filtrado = df[df["Nivel"].notna() & (df["Nivel"].astype(str).str.strip() != "")]
    
    if df_filtrado.empty:
        st.warning("No hay datos con niveles válidos")
        return
    
    # Crear tabla pivot
    pivot_table = df_filtrado.pivot_table(
        values=columna_volumen,
        index=["Nivel", "Elementos"],
        columns="FC_CON_ESTADO",
        aggfunc="sum",
        fill_value=0
    ).reset_index()
    
    # Calcular totales
    pivot_table["Total"] = pivot_table.select_dtypes(include=[np.number]).sum(axis=1)
    
    # Calcular porcentaje de avance
    if "Total" in pivot_table.columns:
        pivot_table["% Avance"] = (pivot_table["Total"] / pivot_table["Total"].sum() * 100).round(2)
    
    # Configurar AgGrid
    gb = GridOptionsBuilder.from_dataframe(pivot_table)
    gb.configure_grid_options(
        domLayout='normal',
        rowGroupPanelShow='always',
        pivotPanelShow='always'
    )
    gb.configure_column("Nivel", rowGroup=True, hide=True)
    gb.configure_column("Elementos", rowGroup=True, hide=True)
    
    # Configurar columnas numéricas
    for col in pivot_table.select_dtypes(include=[np.number]).columns:
        gb.configure_column(
            col,
            type=["numericColumn", "numberColumnFilter"],
            valueFormatter="value.toLocaleString('es-CL', {minimumFractionDigits: 2, maximumFractionDigits: 2})"
        )
    
    grid_options = gb.build()
    
    # Mostrar tabla
    st.subheader(titulo)
    grid_response = AgGrid(
        pivot_table,
        gridOptions=grid_options,
        data_return_mode='AS_INPUT',
        update_mode='MODEL_CHANGED',
        fit_columns_on_grid_load=True,
        theme='streamlit',
        height=400,
        allow_unsafe_jscode=True
    )

def mostrar_avance_semanal():
    """Muestra el avance semanal de hormigones"""
    archivos_fechas, service = cargar_archivos_semanales()
    
    if not archivos_fechas:
        st.warning("No se encontraron archivos semanales")
        return
    
    # Procesar archivos
    lista_df = []
    for f, fecha in archivos_fechas:
        fh = download_file(service, f['id'])
        if not fh:
            continue
            
        dfw = pd.read_csv(fh, sep='\t', header=1, dtype=str)
        dfw = dfw.dropna(how="all")
        dfw = dfw.rename(columns=lambda x: x.strip().replace('"', ''))
        
        if "VolumenHA" in dfw.columns:
            dfw["VolumenHA"] = pd.to_numeric(
                dfw["VolumenHA"].str.replace(",", ".", regex=False), 
                errors='coerce'
            )
        
        # Solo Hormigonado = 'Sí'
        dfw = dfw[dfw["Hormigonado"] == "Sí"]
        
        # Solo filas con Nivel y Elementos válidos
        dfw = dfw[dfw["Nivel"].notna() & (dfw["Nivel"].astype(str).str.strip() != "")]
        dfw = dfw[dfw["Elementos"].notna() & (dfw["Elementos"].astype(str).str.strip() != "")]
        
        # Agrupar por Nivel y Elementos
        resumen = dfw.groupby(["Nivel", "Elementos"])["VolumenHA"].sum().reset_index()
        resumen["Fecha"] = fecha
        lista_df.append(resumen)
    
    if not lista_df:
        st.warning("No hay datos de hormigones para mostrar")
        return
    
    # Unir todos los resultados
    df_semana = pd.concat(lista_df, ignore_index=True)
    
    # Crear tabla pivot para comparación
    pivot_semanal = df_semana.pivot_table(
        values="VolumenHA",
        index=["Nivel", "Elementos"],
        columns="Fecha",
        aggfunc="sum",
        fill_value=0
    ).reset_index()
    
    # Calcular diferencias entre semanas
    fechas = sorted(df_semana["Fecha"].unique())
    if len(fechas) >= 2:
        for i in range(1, len(fechas)):
            col_actual = fechas[i]
            col_anterior = fechas[i-1]
            if col_actual in pivot_semanal.columns and col_anterior in pivot_semanal.columns:
                pivot_semanal[f"Dif_{col_anterior.strftime('%d/%m')}_{col_actual.strftime('%d/%m')}"] = (
                    pivot_semanal[col_actual] - pivot_semanal[col_anterior]
                )
    
    # Configurar AgGrid
    gb = GridOptionsBuilder.from_dataframe(pivot_semanal)
    gb.configure_grid_options(
        domLayout='normal',
        rowGroupPanelShow='always'
    )
    gb.configure_column("Nivel", rowGroup=True, hide=True)
    gb.configure_column("Elementos", rowGroup=True, hide=True)
    
    # Configurar columnas numéricas
    for col in pivot_semanal.select_dtypes(include=[np.number]).columns:
        gb.configure_column(
            col,
            type=["numericColumn", "numberColumnFilter"],
            valueFormatter="value.toLocaleString('es-CL', {minimumFractionDigits: 2, maximumFractionDigits: 2})"
        )
    
    grid_options = gb.build()
    
    # Mostrar tabla
    st.subheader("Avance Semanal Hormigones")
    grid_response = AgGrid(
        pivot_semanal,
        gridOptions=grid_options,
        data_return_mode='AS_INPUT',
        update_mode='MODEL_CHANGED',
        fit_columns_on_grid_load=True,
        theme='streamlit',
        height=400,
        allow_unsafe_jscode=True
    )

def mostrar_trisemanal():
    """Muestra comparación trisemanal"""
    archivos_fechas, service = cargar_archivos_semanales()
    
    if len(archivos_fechas) < 2:
        st.warning("Se necesitan al menos 2 archivos semanales para la comparación trisemanal")
        return
    
    # Tomar solo los 2 últimos archivos
    archivos_fechas = archivos_fechas[-2:]
    
    # Procesar archivos
    lista_df = []
    for f, fecha in archivos_fechas:
        fh = download_file(service, f['id'])
        if not fh:
            continue
            
        dfw = pd.read_csv(fh, sep='\t', header=1, dtype=str)
        dfw = dfw.dropna(how="all")
        dfw = dfw.rename(columns=lambda x: x.strip().replace('"', ''))
        
        if "VolumenHA" in dfw.columns:
            dfw["VolumenHA"] = pd.to_numeric(
                dfw["VolumenHA"].str.replace(",", ".", regex=False), 
                errors='coerce'
            )
        
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
    
    if not lista_df:
        st.warning("No hay datos para la comparación trisemanal")
        return
    
    # Unir todos los resultados
    df_semana = pd.concat(lista_df, ignore_index=True)
    
    # Crear tabla pivot para comparación
    pivot_trisemanal = df_semana.pivot_table(
        values="VolumenHA",
        index=["Nivel", "Elementos"],
        columns="Fecha",
        aggfunc="sum",
        fill_value=0
    ).reset_index()
    
    # Calcular diferencia entre las dos semanas
    fechas = sorted(df_semana["Fecha"].unique())
    if len(fechas) == 2:
        col_actual = fechas[1]
        col_anterior = fechas[0]
        if col_actual in pivot_trisemanal.columns and col_anterior in pivot_trisemanal.columns:
            pivot_trisemanal["Diferencia"] = pivot_trisemanal[col_actual] - pivot_trisemanal[col_anterior]
    
    # Configurar AgGrid
    gb = GridOptionsBuilder.from_dataframe(pivot_trisemanal)
    gb.configure_grid_options(
        domLayout='normal',
        rowGroupPanelShow='always'
    )
    gb.configure_column("Nivel", rowGroup=True, hide=True)
    gb.configure_column("Elementos", rowGroup=True, hide=True)
    
    # Configurar columnas numéricas
    for col in pivot_trisemanal.select_dtypes(include=[np.number]).columns:
        gb.configure_column(
            col,
            type=["numericColumn", "numberColumnFilter"],
            valueFormatter="value.toLocaleString('es-CL', {minimumFractionDigits: 2, maximumFractionDigits: 2})"
        )
    
    grid_options = gb.build()
    
    # Mostrar tabla
    st.subheader("Comparación Trisemanal")
    grid_response = AgGrid(
        pivot_trisemanal,
        gridOptions=grid_options,
        data_return_mode='AS_INPUT',
        update_mode='MODEL_CHANGED',
        fit_columns_on_grid_load=True,
        theme='streamlit',
        height=400,
        allow_unsafe_jscode=True
    )

# Función principal
def main():
    # Cargar datos
    df = cargar_datos()
    
    if df is None:
        st.error("No se pudieron cargar los datos desde Google Drive")
        st.info("Verifica que las credenciales y IDs de archivo estén configurados correctamente")
        return
    
    # Crear pestañas
    tabs = st.tabs([
        "🏗️ Hormigones", 
        "📐 Moldajes", 
        "🔩 Enfierraduras",
        "📈 Avance Semanal Hormigones",
        "🔄 TRISEMANAL"
    ])
    
    # Pestaña Hormigones
    with tabs[0]:
        st.header("🏗️ Control de Avance - Hormigones")
        crear_tabla_interactiva(df, "Avance de Hormigones", "VolumenHA")
    
    # Pestaña Moldajes
    with tabs[1]:
        st.header("📐 Control de Avance - Moldajes")
        crear_tabla_interactiva(df, "Avance de Moldajes", "AreaMoldaje")
    
    # Pestaña Enfierraduras
    with tabs[2]:
        st.header("🔩 Control de Avance - Enfierraduras")
        crear_tabla_interactiva(df, "Avance de Enfierraduras", "Cuantia")
    
    # Pestaña Avance Semanal Hormigones
    with tabs[3]:
        mostrar_avance_semanal()
    
    # Pestaña TRISEMANAL
    with tabs[4]:
        mostrar_trisemanal()

# Ejecutar aplicación
if __name__ == "__main__":
    main() 