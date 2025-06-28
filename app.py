import streamlit as st
import pandas as pd
import numpy as np
import re
import plotly.express as px
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io
import json
import time
import ssl
import urllib3
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
import requests
import os
from datetime import datetime

# Configuración de la página
st.set_page_config(
    page_title="Dashboard Control de Avance",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Título principal
st.title("📊 Dashboard Control de Avance - Hormigones, Moldajes y Enfierraduras")

def clean_private_key(private_key_str):
    """Limpia y formatea correctamente el private_key"""
    # Si ya tiene el formato correcto, devolverlo tal como está
    if "-----BEGIN PRIVATE KEY-----" in private_key_str and "-----END PRIVATE KEY-----" in private_key_str:
        # Reemplazar \\n por \n si es necesario
        cleaned_key = private_key_str.replace("\\n", "\n")
        return cleaned_key
    return private_key_str

# Configuración de Google Drive
@st.cache_resource
def get_drive_service():
    """Obtiene el servicio de Google Drive usando las credenciales"""
    try:
        # Obtener las credenciales de los secretos
        creds_input = st.secrets["GOOGLE_CREDENTIALS"]
        
        # Convertir a diccionario según el tipo de entrada
        if isinstance(creds_input, str):
            # Si es string, intentar parsear como JSON
            try:
                creds_dict = json.loads(creds_input)
            except json.JSONDecodeError as e:
                return None
        elif isinstance(creds_input, dict):
            # Si ya es un diccionario, usarlo directamente
            creds_dict = creds_input
        else:
            return None
        
        # Verificar que tenga los campos necesarios
        required_fields = ["type", "project_id", "private_key", "client_email"]
        missing_fields = [field for field in required_fields if field not in creds_dict]
        
        if missing_fields:
            return None
        
        # Crear una copia limpia de las credenciales
        clean_creds = {
            "type": creds_dict["type"],
            "project_id": creds_dict["project_id"],
            "private_key_id": creds_dict["private_key_id"],
            "client_email": creds_dict["client_email"],
            "client_id": creds_dict["client_id"],
            "auth_uri": creds_dict["auth_uri"],
            "token_uri": creds_dict["token_uri"],
            "auth_provider_x509_cert_url": creds_dict["auth_provider_x509_cert_url"],
            "client_x509_cert_url": creds_dict["client_x509_cert_url"]
        }
        
        # Manejar el private_key de forma especial
        private_key = creds_dict["private_key"]
        
        # Si el private_key tiene \\n, reemplazarlo por \n
        if "\\n" in private_key:
            private_key = private_key.replace("\\n", "\n")
        
        clean_creds["private_key"] = private_key
        
        # Crear las credenciales
        creds = service_account.Credentials.from_service_account_info(
            clean_creds,
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        
        # Construir el servicio
        service = build('drive', 'v3', credentials=creds)
        
        # Probar la conexión
        try:
            service.files().list(pageSize=1).execute()
            return service
        except Exception as e:
            return None
            
    except Exception as e:
        return None

def download_file(service, file_id):
    """Lee directamente el contenido del archivo desde Google Drive"""
    try:
        # Leer el archivo directamente desde Google Drive
        request = service.files().get_media(fileId=file_id)
        file_content = request.execute()
        
        # Convertir el contenido a StringIO para que pandas pueda leerlo
        from io import StringIO
        content_str = file_content.decode('utf-8')
        return StringIO(content_str)
        
    except Exception as e:
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
        return []

# Cargar datos desde Google Drive
@st.cache_data(ttl=3600)  # Cache por 1 hora
def cargar_datos():
    """Carga el archivo AO_GENERAL.txt desde Google Drive o local como fallback"""
    service = get_drive_service()
    
    # Intentar cargar desde Google Drive primero
    if service:
        try:
            file_id = st.secrets["FILE_ID_GENERAL"]
            fh = download_file(service, file_id)
            if fh:
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
            return None
    
    # Fallback: intentar cargar desde archivo local
    try:
        local_file = "AO_GENERAL.txt"
        if os.path.exists(local_file):
            df = pd.read_csv(local_file, sep="\t", header=1, dtype=str)
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
        else:
            return None
    except Exception as e:
        return None
    
    return None

@st.cache_data(ttl=3600)  # Cache por 1 hora
def cargar_archivos_semanales():
    """Carga archivos semanales desde Google Drive o local como fallback"""
    service = get_drive_service()
    
    # Intentar cargar desde Google Drive primero
    if service:
        try:
            folder_id = st.secrets["FOLDER_ID_SEMANAL"]
            files = list_files_in_folder(service, folder_id)
            
            # Filtrar solo archivos *_AO_GENERAL.txt
            archivos = [f for f in files if f['name'].endswith('_AO_GENERAL.txt')]
            
            def extraer_fecha(nombre):
                # Intentar diferentes formatos de fecha
                patterns = [
                    r"(\d{2}-\d{2}-\d{4})_AO_GENERAL\.txt",  # DD-MM-YYYY
                    r"(\d{2}-\d{2}-\d{2})_AO_GENERAL\.txt",  # DD-MM-YY
                    r"(\d{4}-\d{2}-\d{2})_AO_GENERAL\.txt",  # YYYY-MM-DD
                ]
                
                for pattern in patterns:
                    m = re.match(pattern, nombre)
                    if m:
                        fecha_str = m.group(1)
                        try:
                            # Intentar diferentes formatos de fecha
                            if len(fecha_str.split('-')[2]) == 4:  # YYYY
                                if len(fecha_str.split('-')[0]) == 2:  # DD-MM-YYYY
                                    return pd.to_datetime(fecha_str, format='%d-%m-%Y', dayfirst=True)
                                else:  # YYYY-MM-DD
                                    return pd.to_datetime(fecha_str, format='%Y-%m-%d')
                            else:  # DD-MM-YY
                                return pd.to_datetime(fecha_str, format='%d-%m-%y', dayfirst=True)
                        except:
                            continue
                return None
            
            archivos_fechas = [(f, extraer_fecha(f['name'])) for f in archivos]
            archivos_fechas = sorted(
                [x for x in archivos_fechas if x[1] is not None], 
                key=lambda x: x[1]
            )
            
            if archivos_fechas:
                return archivos_fechas, service
        except Exception as e:
            return None
    
    # Fallback: intentar cargar desde carpeta local
    try:
        local_folder = "REPORTE SEMANAL"
        if os.path.exists(local_folder):
            archivos = []
            for filename in os.listdir(local_folder):
                if filename.endswith('_AO_GENERAL.txt'):
                    file_path = os.path.join(local_folder, filename)
                    # Crear un objeto similar al de Google Drive
                    file_obj = {
                        'id': file_path,  # Usar path como ID
                        'name': filename,
                        'local_path': file_path
                    }
                    archivos.append(file_obj)
            
            def extraer_fecha(nombre):
                # Intentar diferentes formatos de fecha
                patterns = [
                    r"(\d{2}-\d{2}-\d{4})_AO_GENERAL\.txt",  # DD-MM-YYYY
                    r"(\d{2}-\d{2}-\d{2})_AO_GENERAL\.txt",  # DD-MM-YY
                    r"(\d{4}-\d{2}-\d{2})_AO_GENERAL\.txt",  # YYYY-MM-DD
                ]
                
                for pattern in patterns:
                    m = re.match(pattern, nombre)
                    if m:
                        fecha_str = m.group(1)
                        try:
                            # Intentar diferentes formatos de fecha
                            if len(fecha_str.split('-')[2]) == 4:  # YYYY
                                if len(fecha_str.split('-')[0]) == 2:  # DD-MM-YYYY
                                    return pd.to_datetime(fecha_str, format='%d-%m-%Y', dayfirst=True)
                                else:  # YYYY-MM-DD
                                    return pd.to_datetime(fecha_str, format='%Y-%m-%d')
                            else:  # DD-MM-YY
                                return pd.to_datetime(fecha_str, format='%d-%m-%y', dayfirst=True)
                        except:
                            continue
                return None
            
            archivos_fechas = [(f, extraer_fecha(f['name'])) for f in archivos]
            archivos_fechas = sorted(
                [x for x in archivos_fechas if x[1] is not None], 
                key=lambda x: x[1]
            )
            
            if archivos_fechas:
                return archivos_fechas, None  # None indica que es local
        else:
            return None
    except Exception as e:
        return None

def crear_tabla_interactiva(df, titulo, columna_volumen="VolumenHA", tab_key=""):
    """Crea una tabla interactiva con AgGrid, jerarquía expandible por Nivel y Elementos como matriz, mostrando solo el valor correspondiente (VolumenHA, AreaMoldaje o Cuantia) según el tipo de tabla. El resumen general muestra solo el total correspondiente y el % de avance real (Si/Total*100 en avance, no en conteo). La columna Total está oculta en la tabla pero se usa para los cálculos y el resumen."""
    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode

    if df.empty:
        return

    # Determinar el parámetro booleano y columna de valor según el tipo de tabla
    if "Hormigon" in titulo or "Hormigon" in columna_volumen:
        param_bool = "Hormigonado"
        valor_col = "VolumenHA"
        valor_label = "VolumenHA"
    elif "Moldaje" in titulo or "Moldaje" in columna_volumen:
        param_bool = "Moldaje"
        valor_col = "AreaMoldaje"
        valor_label = "Area Moldaje"
    elif "Enfierradura" in titulo or "Enfierradura" in columna_volumen:
        param_bool = "Enfierradura"
        valor_col = "Cuantia"
        valor_label = "Cuantía"
    else:
        return

    # Verificar columnas necesarias
    required_columns = ["Nivel", "Elementos", param_bool, valor_col]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        return

    # Filtrar filas válidas
    df_filtrado = df[df["Nivel"].notna() & (df["Nivel"].astype(str).str.strip() != "")]
    df_filtrado = df_filtrado[df_filtrado["Elementos"].notna() & (df_filtrado["Elementos"].astype(str).str.strip() != "")]
    df_filtrado = df_filtrado[df_filtrado[valor_col].notna() & (df_filtrado[valor_col].astype(str).str.strip() != "")]
    if df_filtrado.empty:
        return

    # Normalizar valores del parámetro booleano
    df_filtrado[param_bool] = df_filtrado[param_bool].astype(str).str.strip().str.lower()
    # Considerar 'sí' como positivo, el resto como 'no'
    df_filtrado["Es_Si"] = np.where(df_filtrado[param_bool].isin(["si", "sí", "true", "1"]), 1, 0)
    df_filtrado["Es_No"] = 1 - df_filtrado["Es_Si"]
    df_filtrado[valor_col] = df_filtrado[valor_col].astype(float)

    # Calcular avance real para Si y No
    df_filtrado["Avance_Si"] = np.where(df_filtrado["Es_Si"] == 1, df_filtrado[valor_col], 0)
    df_filtrado["Avance_No"] = np.where(df_filtrado["Es_No"] == 1, df_filtrado[valor_col], 0)

    # Agrupar por Nivel y Elementos
    resumen = df_filtrado.groupby(["Nivel", "Elementos"]).agg(
        Si=("Avance_Si", "sum"),
        No=("Avance_No", "sum"),
        Total=(valor_col, "sum")
    ).reset_index()
    resumen["Si%"] = np.where(resumen["Total"] > 0, (resumen["Si"] / resumen["Total"] * 100).round(2), 0)
    resumen["No%"] = np.where(resumen["Total"] > 0, (resumen["No"] / resumen["Total"] * 100).round(2), 0)
    resumen[valor_col] = resumen["Total"].round(2)
    resumen["Si"] = resumen["Si"].round(2)
    resumen["No"] = resumen["No"].round(2)

    st.subheader(titulo)

    # Filtros
    col1, col2 = st.columns(2)
    with col1:
        niveles = ["Todos"] + sorted(resumen["Nivel"].unique())
        nivel_seleccionado = st.selectbox("Filtrar por Nivel:", niveles, key=f"nivel_{tab_key}")
    with col2:
        elementos = ["Todos"] + sorted(resumen["Elementos"].unique())
        elemento_seleccionado = st.selectbox("Filtrar por Elemento:", elementos, key=f"elemento_{tab_key}")

    df_filtrado_tabla = resumen.copy()
    if nivel_seleccionado != "Todos":
        df_filtrado_tabla = df_filtrado_tabla[df_filtrado_tabla["Nivel"] == nivel_seleccionado]
    if elemento_seleccionado != "Todos":
        df_filtrado_tabla = df_filtrado_tabla[df_filtrado_tabla["Elementos"] == elemento_seleccionado]

    # Configurar AgGrid para jerarquía expandible y columnas visibles
    gb = GridOptionsBuilder.from_dataframe(df_filtrado_tabla)
    gb.configure_default_column(resizable=True, filterable=True, sortable=True, editable=False)
    gb.configure_column("Nivel", rowGroup=True, rowGroupIndex=0)  # visible
    gb.configure_column("Elementos", rowGroup=True, rowGroupIndex=1)  # visible
    gb.configure_column("Si", type=["numericColumn", "numberColumnFilter"], width=100, valueFormatter="value.toFixed(2)")
    gb.configure_column("Si%", type=["numericColumn", "numberColumnFilter"], width=100, valueFormatter="value.toFixed(2) + '%'", cellStyle={"color": "green"})
    gb.configure_column("No", type=["numericColumn", "numberColumnFilter"], width=100, valueFormatter="value.toFixed(2)")
    gb.configure_column("No%", type=["numericColumn", "numberColumnFilter"], width=100, valueFormatter="value.toFixed(2) + '%'", cellStyle={"color": "red"})
    gb.configure_column("Total", type=["numericColumn", "numberColumnFilter"], width=120, valueFormatter="value.toFixed(2)", hide=True)
    gb.configure_column(valor_col, type=["numericColumn", "numberColumnFilter"], width=120, valueFormatter="value.toFixed(2)")
    gb.configure_grid_options(
        domLayout='normal',
        enableRangeSelection=True,
        enableCharts=True,
        groupDisplayType='groupRows',
        groupDefaultExpanded=0  # Colapsado por defecto
    )
    grid_options = gb.build()

    AgGrid(
        df_filtrado_tabla,
        gridOptions=grid_options,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        update_mode=GridUpdateMode.GRID_CHANGED,
        fit_columns_on_grid_load=True,
        theme='streamlit',
        height=400,
        allow_unsafe_jscode=True
    )

    # Métricas generales
    if not df_filtrado_tabla.empty:
        st.subheader("📊 Resumen General")
        cols = st.columns(5)
        with cols[0]:
            st.metric("Total Avance", f"{df_filtrado_tabla['Total'].sum():.2f}")
        with cols[1]:
            st.metric(f"Avance {valor_label} (Sí)", f"{df_filtrado_tabla['Si'].sum():.2f}")
        with cols[2]:
            st.metric(f"Avance {valor_label} (No)", f"{df_filtrado_tabla['No'].sum():.2f}")
        with cols[3]:
            st.metric(valor_label, f"{df_filtrado_tabla[valor_col].sum():.2f}")
        with cols[4]:
            total = df_filtrado_tabla["Total"].sum()
            si = df_filtrado_tabla["Si"].sum()
            if total > 0:
                st.metric("% Avance", f"{(si/total*100):.2f}%")
            else:
                st.metric("% Avance", "0.00%")

def mostrar_avance_semanal(use_local_files=False):
    """Muestra el avance semanal de hormigones"""
    if use_local_files:
        archivos_fechas, service = cargar_archivos_semanales_local()
    else:
        archivos_fechas, service = cargar_archivos_semanales()
    
    if not archivos_fechas:
        st.info("No se encontraron archivos semanales para mostrar. Verifica que existan archivos en la carpeta 'REPORTE SEMANAL' o en Google Drive.")
        return
    
    # Procesar archivos
    lista_df = []
    archivos_procesados = 0
    
    for f, fecha in archivos_fechas:
        try:
            if use_local_files:
                # Para archivos locales, f es el nombre del archivo
                filepath = os.path.join("REPORTE SEMANAL", f)
                fh = leer_archivo_local(filepath)
            else:
                # Para archivos de Google Drive, f es el objeto del archivo
                fh = download_file(service, f['id'])
            
            if not fh:
                continue
                
            # Leer el archivo con el formato correcto
            dfw = pd.read_csv(fh, sep='\t', header=1, dtype=str, quoting=3)  # QUOTE_NONE
            dfw = dfw.dropna(how="all")
            
            if dfw.empty:
                continue
            
            # Limpiar columnas (remover comillas)
            dfw = dfw.rename(columns=lambda x: x.strip().replace('"', '') if isinstance(x, str) else x)
            
            # Limpiar datos (remover comillas de los valores)
            for col in dfw.columns:
                if dfw[col].dtype == 'object':
                    dfw[col] = dfw[col].astype(str).str.replace('"', '')
            
            # Verificar que exista la columna VolumenHA
            if "VolumenHA" not in dfw.columns:
                continue
            
            # Convertir VolumenHA a numérico
            dfw["VolumenHA"] = pd.to_numeric(
                dfw["VolumenHA"].str.replace(",", ".", regex=False), 
                errors='coerce'
            )
            
            # Solo Hormigonado = 'Sí'
            if "Hormigonado" in dfw.columns:
                dfw = dfw[dfw["Hormigonado"] == "Sí"]
            else:
                continue
            
            # Solo filas con Nivel y Elementos válidos
            if "Nivel" in dfw.columns and "Elementos" in dfw.columns:
                dfw = dfw[dfw["Nivel"].notna() & (dfw["Nivel"].astype(str).str.strip() != "")]
                dfw = dfw[dfw["Elementos"].notna() & (dfw["Elementos"].astype(str).str.strip() != "")]
            else:
                continue
            
            # Solo filas con VolumenHA válido
            dfw = dfw[dfw["VolumenHA"].notna() & (dfw["VolumenHA"] > 0)]
            
            if dfw.empty:
                continue
            
            # Agrupar por Nivel y Elementos
            resumen = dfw.groupby(["Nivel", "Elementos"])["VolumenHA"].sum().reset_index()
            resumen["Fecha"] = fecha
            lista_df.append(resumen)
            archivos_procesados += 1
            
        except Exception as e:
            continue
    
    if not lista_df:
        st.info("No se pudieron procesar archivos semanales. Verifica el formato de los archivos.")
        return
    
    if archivos_procesados == 0:
        st.info("No se encontraron datos válidos en los archivos semanales.")
        return
    
    # Unir todos los resultados
    df_semana = pd.concat(lista_df, ignore_index=True)
    
    if df_semana.empty:
        st.info("No hay datos de hormigones para mostrar.")
        return
    
    # Crear tabla pivot para comparación
    try:
        pivot_semanal = df_semana.pivot_table(
            values="VolumenHA",
            index=["Nivel", "Elementos"],
            columns="Fecha",
            aggfunc="sum",
            fill_value=0
        ).reset_index()
    except Exception as e:
        st.info("Error al crear la tabla de comparación semanal.")
        return
    
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
    
    # Calcular totales
    numeric_cols = pivot_semanal.select_dtypes(include=[np.number]).columns
    if len(numeric_cols) > 0:
        pivot_semanal["Total"] = pivot_semanal[numeric_cols].sum(axis=1)
        if pivot_semanal["Total"].sum() > 0:
            pivot_semanal["% Avance"] = (pivot_semanal["Total"] / pivot_semanal["Total"].sum() * 100).round(2)
    
    # Formatear columnas numéricas
    for col in pivot_semanal.select_dtypes(include=[np.number]).columns:
        pivot_semanal[col] = pivot_semanal[col].round(2)
    
    # Ordenar por Nivel y Elemento para jerarquía visual
    pivot_semanal = pivot_semanal.sort_values(["Nivel", "Elementos"]).reset_index(drop=True)
    
    # Mostrar tabla
    st.subheader("Avance Semanal Hormigones")
    
    # Mostrar información de archivos procesados
    st.caption(f"Archivos procesados: {archivos_procesados} de {len(archivos_fechas)}")
    
    # Agregar filtros
    col1, col2 = st.columns(2)
    
    with col1:
        try:
            niveles_raw = df_semana["Nivel"].dropna().unique()
            niveles_clean = [str(n).strip() for n in niveles_raw if str(n).strip()]
            niveles = ["Todos"] + sorted(niveles_clean)
            nivel_seleccionado = st.selectbox("Filtrar por Nivel:", niveles, key="semanal_nivel")
        except Exception as e:
            nivel_seleccionado = "Todos"
    
    with col2:
        try:
            elementos_raw = df_semana["Elementos"].dropna().unique()
            elementos_clean = [str(e).strip() for e in elementos_raw if str(e).strip()]
            elementos = ["Todos"] + sorted(elementos_clean)
            elemento_seleccionado = st.selectbox("Filtrar por Elemento:", elementos, key="semanal_elemento")
        except Exception as e:
            elemento_seleccionado = "Todos"
    
    # Aplicar filtros
    df_filtrado_tabla = pivot_semanal.copy()
    try:
        if nivel_seleccionado != "Todos":
            df_filtrado_tabla = df_filtrado_tabla[df_filtrado_tabla["Nivel"] == nivel_seleccionado]
        if elemento_seleccionado != "Todos":
            df_filtrado_tabla = df_filtrado_tabla[df_filtrado_tabla["Elementos"] == elemento_seleccionado]
    except Exception as e:
        pass
    
    # Mostrar tabla con jerarquías expandibles
    try:
        # Crear configuración de columnas dinámica
        column_config = {
            "Nivel": st.column_config.TextColumn("Nivel", width="medium"),
            "Elementos": st.column_config.TextColumn("Elementos", width="large"),
        }
        
        # Agregar columnas de fechas
        for col in df_filtrado_tabla.columns:
            if col not in ["Nivel", "Elementos", "Total", "% Avance"]:
                if "Dif_" in col:
                    column_config[col] = st.column_config.NumberColumn(col, format="%.2f")
                else:
                    column_config[col] = st.column_config.NumberColumn(col, format="%.2f")
        
        # Agregar columnas de totales
        if "Total" in df_filtrado_tabla.columns:
            column_config["Total"] = st.column_config.NumberColumn("Total", format="%.2f")
        if "% Avance" in df_filtrado_tabla.columns:
            column_config["% Avance"] = st.column_config.NumberColumn("% Avance", format="%.2f%%")
        
        st.dataframe(
            df_filtrado_tabla,
            use_container_width=True,
            hide_index=True,
            column_config=column_config
        )
    except Exception as e:
        st.dataframe(df_filtrado_tabla, use_container_width=True)
    
    # Mostrar métricas
    if not df_filtrado_tabla.empty and "Total" in df_filtrado_tabla.columns:
        try:
            col1, col2, col3 = st.columns(3)
            
            with col1:
                total_sum = df_filtrado_tabla['Total'].sum()
                st.metric("Total General", f"{total_sum:.2f}")
            
            with col2:
                if len(fechas) >= 2:
                    ultima_fecha = fechas[-1]
                    if ultima_fecha in df_filtrado_tabla.columns:
                        ultimo_total = df_filtrado_tabla[ultima_fecha].sum()
                        st.metric(f"Total {ultima_fecha.strftime('%d/%m/%Y')}", f"{ultimo_total:.2f}")
            
            with col3:
                if len(fechas) >= 2:
                    primera_fecha = fechas[0]
                    if primera_fecha in df_filtrado_tabla.columns:
                        primer_total = df_filtrado_tabla[primera_fecha].sum()
                        st.metric(f"Total {primera_fecha.strftime('%d/%m/%Y')}", f"{primer_total:.2f}")
                        
        except Exception as e:
            pass
    
    # Mostrar gráfico de tendencia
    if len(fechas) >= 2:
        st.subheader("Tendencia Semanal")
        try:
            df_tendencia = df_semana.groupby("Fecha")["VolumenHA"].sum().reset_index()
            fig = px.line(df_tendencia, x="Fecha", y="VolumenHA", 
                         title="Evolución del Volumen de Hormigón por Semana")
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.info("No se pudo generar el gráfico de tendencia.")

def mostrar_trisemanal(use_local_files=False):
    """Muestra comparación trisemanal"""
    if use_local_files:
        archivos_fechas, service = cargar_archivos_semanales_local()
    else:
        archivos_fechas, service = cargar_archivos_semanales()
    
    if len(archivos_fechas) < 2:
        st.info("Se necesitan al menos 2 archivos semanales para la comparación trisemanal.")
        return
    
    # Tomar solo los 2 últimos archivos
    archivos_fechas = archivos_fechas[-2:]
    
    # Procesar archivos
    lista_df = []
    archivos_procesados = 0
    
    for f, fecha in archivos_fechas:
        try:
            if use_local_files:
                # Para archivos locales, f es el nombre del archivo
                filepath = os.path.join("REPORTE SEMANAL", f)
                fh = leer_archivo_local(filepath)
            else:
                # Para archivos de Google Drive, f es el objeto del archivo
                fh = download_file(service, f['id'])
            
            if not fh:
                continue
                
            # Leer el archivo con el formato correcto
            dfw = pd.read_csv(fh, sep='\t', header=1, dtype=str, quoting=3)  # QUOTE_NONE
            dfw = dfw.dropna(how="all")
            
            if dfw.empty:
                continue
            
            # Limpiar columnas (remover comillas)
            dfw = dfw.rename(columns=lambda x: x.strip().replace('"', '') if isinstance(x, str) else x)
            
            # Limpiar datos (remover comillas de los valores)
            for col in dfw.columns:
                if dfw[col].dtype == 'object':
                    dfw[col] = dfw[col].astype(str).str.replace('"', '')
            
            # Verificar que exista la columna VolumenHA
            if "VolumenHA" not in dfw.columns:
                continue
            
            # Convertir VolumenHA a numérico
            dfw["VolumenHA"] = pd.to_numeric(
                dfw["VolumenHA"].str.replace(",", ".", regex=False), 
                errors='coerce'
            )
            
            # Solo Hormigonado = 'Sí'
            if "Hormigonado" in dfw.columns:
                dfw = dfw[dfw["Hormigonado"] == "Sí"]
            else:
                continue
            
            # Solo filas con Nivel y Elementos válidos
            if "Nivel" in dfw.columns and "Elementos" in dfw.columns:
                dfw = dfw[dfw["Nivel"].notna() & (dfw["Nivel"].astype(str).str.strip() != "")]
                dfw = dfw[dfw["Elementos"].notna() & (dfw["Elementos"].astype(str).str.strip() != "")]
            else:
                continue
            
            # Solo filas con VolumenHA válido
            dfw = dfw[dfw["VolumenHA"].notna() & (dfw["VolumenHA"] > 0)]
            
            # Filtrar por FC_CON_TRISEMANAL = 'Semana 01' por defecto
            if "FC_CON_TRISEMANAL" in dfw.columns:
                dfw = dfw[dfw["FC_CON_TRISEMANAL"] == "Semana 01"]
            
            if dfw.empty:
                continue
            
            # Agrupar por Nivel y Elementos
            resumen = dfw.groupby(["Nivel", "Elementos"])["VolumenHA"].sum().reset_index()
            resumen["Fecha"] = fecha
            lista_df.append(resumen)
            archivos_procesados += 1
            
        except Exception as e:
            continue
    
    if not lista_df:
        st.info("No se pudieron procesar archivos para la comparación trisemanal.")
        return
    
    if archivos_procesados < 2:
        st.info("Se necesitan al menos 2 archivos válidos para la comparación trisemanal.")
        return
    
    # Unir todos los resultados
    df_semana = pd.concat(lista_df, ignore_index=True)
    
    if df_semana.empty:
        st.info("No hay datos para la comparación trisemanal.")
        return
    
    # Crear tabla pivot para comparación
    try:
        pivot_trisemanal = df_semana.pivot_table(
            values="VolumenHA",
            index=["Nivel", "Elementos"],
            columns="Fecha",
            aggfunc="sum",
            fill_value=0
        ).reset_index()
    except Exception as e:
        st.info("Error al crear la tabla de comparación trisemanal.")
        return
    
    # Calcular diferencia entre las dos semanas
    fechas = sorted(df_semana["Fecha"].unique())
    if len(fechas) == 2:
        col_actual = fechas[1]
        col_anterior = fechas[0]
        if col_actual in pivot_trisemanal.columns and col_anterior in pivot_trisemanal.columns:
            pivot_trisemanal["Diferencia"] = pivot_trisemanal[col_actual] - pivot_trisemanal[col_anterior]
    
    # Calcular totales
    numeric_cols = pivot_trisemanal.select_dtypes(include=[np.number]).columns
    if len(numeric_cols) > 0:
        pivot_trisemanal["Total"] = pivot_trisemanal[numeric_cols].sum(axis=1)
        if pivot_trisemanal["Total"].sum() > 0:
            pivot_trisemanal["% Avance"] = (pivot_trisemanal["Total"] / pivot_trisemanal["Total"].sum() * 100).round(2)
    
    # Formatear columnas numéricas
    for col in pivot_trisemanal.select_dtypes(include=[np.number]).columns:
        pivot_trisemanal[col] = pivot_trisemanal[col].round(2)
    
    # Ordenar por Nivel y Elemento para jerarquía visual
    pivot_trisemanal = pivot_trisemanal.sort_values(["Nivel", "Elementos"]).reset_index(drop=True)
    
    # Mostrar tabla
    st.subheader("Comparación Trisemanal")
    
    # Mostrar información de archivos procesados
    st.caption(f"Archivos procesados: {archivos_procesados} de {len(archivos_fechas)}")
    
    # Agregar filtros
    col1, col2 = st.columns(2)
    
    with col1:
        try:
            niveles_raw = df_semana["Nivel"].dropna().unique()
            niveles_clean = [str(n).strip() for n in niveles_raw if str(n).strip()]
            niveles = ["Todos"] + sorted(niveles_clean)
            nivel_seleccionado = st.selectbox("Filtrar por Nivel:", niveles, key="trisemanal_nivel")
        except Exception as e:
            nivel_seleccionado = "Todos"
    
    with col2:
        try:
            elementos_raw = df_semana["Elementos"].dropna().unique()
            elementos_clean = [str(e).strip() for e in elementos_raw if str(e).strip()]
            elementos = ["Todos"] + sorted(elementos_clean)
            elemento_seleccionado = st.selectbox("Filtrar por Elemento:", elementos, key="trisemanal_elemento")
        except Exception as e:
            elemento_seleccionado = "Todos"
    
    # Aplicar filtros
    df_filtrado_tabla = pivot_trisemanal.copy()
    try:
        if nivel_seleccionado != "Todos":
            df_filtrado_tabla = df_filtrado_tabla[df_filtrado_tabla["Nivel"] == nivel_seleccionado]
        if elemento_seleccionado != "Todos":
            df_filtrado_tabla = df_filtrado_tabla[df_filtrado_tabla["Elementos"] == elemento_seleccionado]
    except Exception as e:
        pass
    
    # Mostrar tabla con jerarquías expandibles
    try:
        # Crear configuración de columnas dinámica
        column_config = {
            "Nivel": st.column_config.TextColumn("Nivel", width="medium"),
            "Elementos": st.column_config.TextColumn("Elementos", width="large"),
        }
        
        # Agregar columnas de fechas
        for col in df_filtrado_tabla.columns:
            if col not in ["Nivel", "Elementos", "Total", "% Avance", "Diferencia"]:
                column_config[col] = st.column_config.NumberColumn(col, format="%.2f")
        
        # Agregar columnas especiales
        if "Diferencia" in df_filtrado_tabla.columns:
            column_config["Diferencia"] = st.column_config.NumberColumn("Diferencia", format="%.2f")
        if "Total" in df_filtrado_tabla.columns:
            column_config["Total"] = st.column_config.NumberColumn("Total", format="%.2f")
        if "% Avance" in df_filtrado_tabla.columns:
            column_config["% Avance"] = st.column_config.NumberColumn("% Avance", format="%.2f%%")
        
        st.dataframe(
            df_filtrado_tabla,
            use_container_width=True,
            hide_index=True,
            column_config=column_config
        )
    except Exception as e:
        st.dataframe(df_filtrado_tabla, use_container_width=True)
    
    # Mostrar resumen de diferencias
    if "Diferencia" in df_filtrado_tabla.columns:
        st.subheader("Resumen de Diferencias")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Diferencia Total", f"{df_filtrado_tabla['Diferencia'].sum():.2f}")
        
        with col2:
            positivas = df_filtrado_tabla[df_filtrado_tabla['Diferencia'] > 0]['Diferencia'].sum()
            st.metric("Diferencias Positivas", f"{positivas:.2f}")
        
        with col3:
            negativas = df_filtrado_tabla[df_filtrado_tabla['Diferencia'] < 0]['Diferencia'].sum()
            st.metric("Diferencias Negativas", f"{negativas:.2f}")
    
    # Mostrar métricas adicionales
    if not df_filtrado_tabla.empty and "Total" in df_filtrado_tabla.columns:
        try:
            col1, col2, col3 = st.columns(3)
            
            with col1:
                total_sum = df_filtrado_tabla['Total'].sum()
                st.metric("Total General", f"{total_sum:.2f}")
            
            with col2:
                if len(fechas) >= 2:
                    ultima_fecha = fechas[-1]
                    if ultima_fecha in df_filtrado_tabla.columns:
                        ultimo_total = df_filtrado_tabla[ultima_fecha].sum()
                        st.metric(f"Total {ultima_fecha.strftime('%d/%m/%Y')}", f"{ultimo_total:.2f}")
            
            with col3:
                if len(fechas) >= 2:
                    primera_fecha = fechas[0]
                    if primera_fecha in df_filtrado_tabla.columns:
                        primer_total = df_filtrado_tabla[primera_fecha].sum()
                        st.metric(f"Total {primera_fecha.strftime('%d/%m/%Y')}", f"{primer_total:.2f}")
                        
        except Exception as e:
            pass

@st.cache_data(ttl=3600)  # Cache por 1 hora
def cargar_datos_local():
    """Carga el archivo AO_GENERAL.txt desde archivo local"""
    try:
        local_file = "AO_GENERAL.txt"
        if os.path.exists(local_file):
            df = pd.read_csv(local_file, sep="\t", header=1, dtype=str)
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
        else:
            return None
    except Exception as e:
        return None

def cargar_archivos_semanales_local():
    """Carga archivos semanales desde la carpeta local"""
    try:
        carpeta = "REPORTE SEMANAL"
        if not os.path.exists(carpeta):
            return [], None
        
        archivos = []
        for filename in os.listdir(carpeta):
            if filename.endswith('.txt') and 'AO_GENERAL' in filename:
                # Extraer fecha del nombre del archivo
                # Buscar el patrón de fecha al inicio del archivo
                fecha = None
                
                # Intentar diferentes patrones de fecha
                patterns = [
                    r"^(\d{2}-\d{2}-\d{4})_AO_GENERAL\.txt$",  # DD-MM-YYYY
                    r"^(\d{2}-\d{2}-\d{2})_AO_GENERAL\.txt$",  # DD-MM-YY
                    r"^(\d{4}-\d{2}-\d{2})_AO_GENERAL\.txt$",  # YYYY-MM-DD
                ]
                
                for pattern in patterns:
                    match = re.match(pattern, filename)
                    if match:
                        fecha_str = match.group(1)
                        try:
                            # Intentar diferentes formatos de fecha
                            if len(fecha_str.split('-')[2]) == 4:  # YYYY
                                if len(fecha_str.split('-')[0]) == 2:  # DD-MM-YYYY
                                    fecha = pd.to_datetime(fecha_str, format='%d-%m-%Y', dayfirst=True)
                                else:  # YYYY-MM-DD
                                    fecha = pd.to_datetime(fecha_str, format='%Y-%m-%d')
                            else:  # DD-MM-YY
                                fecha = pd.to_datetime(fecha_str, format='%d-%m-%y', dayfirst=True)
                            break
                        except:
                            continue
                
                if fecha:
                    archivos.append((filename, fecha))
        
        # Ordenar por fecha
        archivos.sort(key=lambda x: x[1])
        
        if not archivos:
            return [], None
        
        return archivos, None  # None indica que es local
        
    except Exception as e:
        return [], None

def leer_archivo_local(filepath):
    """Lee directamente un archivo local"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        from io import StringIO
        return StringIO(content)
    except Exception as e:
        return None

# Función principal
def main():
    st.markdown("# DASHBOARD CONTROL AVANCE OBRA GRUESA Y TERMINACIONES")
    st.sidebar.header("Menú Principal")
    if 'menu_seleccionado' not in st.session_state:
        st.session_state['menu_seleccionado'] = 'HORMIGONES'
    if 'submenu_hormigones' not in st.session_state:
        st.session_state['submenu_hormigones'] = 'AVANCE GENERAL OG'
    if 'submenu_arquitectura' not in st.session_state:
        st.session_state['submenu_arquitectura'] = 'TABIQUES'

    with st.sidebar:
        exp_hormigones = st.expander("HORMIGONES", expanded=st.session_state['menu_seleccionado'] == 'HORMIGONES')
        exp_arquitectura = st.expander("ARQUITECTURA", expanded=st.session_state['menu_seleccionado'] == 'ARQUITECTURA')
        with exp_hormigones:
            if st.button("Ir a Hormigones", key="btn_hormigones"):
                st.session_state['menu_seleccionado'] = 'HORMIGONES'
        with exp_arquitectura:
            if st.button("Ir a Arquitectura", key="btn_arquitectura"):
                st.session_state['menu_seleccionado'] = 'ARQUITECTURA'

        # Mostrar solo el submenú correspondiente
        if st.session_state['menu_seleccionado'] == 'HORMIGONES':
            st.session_state['submenu_hormigones'] = st.radio(
                "Hormigones",
                ["AVANCE GENERAL OG", "AVANCE SEMANAL OG", "TRISEMANAL OG"],
                key="submenu_hormigones_radio",
                index=["AVANCE GENERAL OG", "AVANCE SEMANAL OG", "TRISEMANAL OG"].index(st.session_state['submenu_hormigones']) if 'submenu_hormigones' in st.session_state else 0
            )
        elif st.session_state['menu_seleccionado'] == 'ARQUITECTURA':
            st.session_state['submenu_arquitectura'] = st.radio(
                "Arquitectura",
                ["TABIQUES", "PAVIMENTOS", "CIELOS", "REVESTIMIENTOS"],
                key="submenu_arquitectura_radio",
                index=["TABIQUES", "PAVIMENTOS", "CIELOS", "REVESTIMIENTOS"].index(st.session_state['submenu_arquitectura']) if 'submenu_arquitectura' in st.session_state else 0
            )

    # Mostrar contenido según la navegación
    if st.session_state['menu_seleccionado'] == "HORMIGONES":
        use_local_files = st.sidebar.checkbox(
            "📁 Usar archivos locales (ignorar Google Drive)",
            key="main_local_checkbox",
            help="Marca esta opción si quieres usar archivos locales en lugar de Google Drive"
        )
        if use_local_files:
            df = cargar_datos_local()
        else:
            df = cargar_datos()
        if df is None:
            return
        submenu = st.session_state['submenu_hormigones']
        if submenu == "AVANCE GENERAL OG":
            st.header("Hormigones")
            crear_tabla_interactiva(df, "Avance de Hormigones", "VolumenHA", tab_key="hormigones_general")
            st.header("Moldajes")
            crear_tabla_interactiva(df, "Avance de Moldajes", "AreaMoldaje", tab_key="moldajes_general")
            st.header("Enfierraduras")
            crear_tabla_interactiva(df, "Avance de Enfierraduras", "Cuantia", tab_key="enfierraduras_general")
        elif submenu == "AVANCE SEMANAL OG":
            mostrar_avance_semanal(use_local_files)
        elif submenu == "TRISEMANAL OG":
            mostrar_trisemanal(use_local_files)
    elif st.session_state['menu_seleccionado'] == "ARQUITECTURA":
        submenu_arq = st.session_state['submenu_arquitectura']
        st.title(f"Arquitectura - {submenu_arq}")
        # Placeholder vacío para futuras vistas

# Ejecutar aplicación
if __name__ == "__main__":
    main() 