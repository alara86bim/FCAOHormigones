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
        
        # Debug: mostrar el tipo de datos recibido
        st.write(f"Tipo de credenciales recibidas: {type(creds_input)}")
        
        # Convertir a diccionario según el tipo de entrada
        if isinstance(creds_input, str):
            # Si es string, intentar parsear como JSON
            try:
                creds_dict = json.loads(creds_input)
                st.success("✅ Credenciales parseadas desde string JSON")
            except json.JSONDecodeError as e:
                st.error(f"❌ Error al parsear JSON: {e}")
                return None
        elif isinstance(creds_input, dict):
            # Si ya es un diccionario, usarlo directamente
            creds_dict = creds_input
            st.success("✅ Credenciales recibidas como diccionario")
        else:
            st.error(f"❌ Tipo de credenciales no soportado: {type(creds_input)}")
            return None
        
        # Verificar que tenga los campos necesarios
        required_fields = ["type", "project_id", "private_key", "client_email"]
        missing_fields = [field for field in required_fields if field not in creds_dict]
        
        if missing_fields:
            st.error(f"❌ Faltan campos requeridos en las credenciales: {missing_fields}")
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
            st.success("✅ Private key con \\n convertido a \\n")
        
        clean_creds["private_key"] = private_key
        
        # Debug: mostrar las primeras líneas del private_key
        st.write(f"Private key preview: {private_key[:100]}...")
        
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
            st.success("✅ Conexión con Google Drive exitosa")
            return service
        except Exception as e:
            st.error(f"❌ Error al conectar con Google Drive API: {e}")
            return None
            
    except Exception as e:
        st.error(f"❌ Error general al configurar Google Drive: {e}")
        st.error("Verifica que las credenciales estén en formato JSON válido")
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
        st.error(f"Error leyendo archivo desde Google Drive: {e}")
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
                
                st.success("✅ Datos cargados desde Google Drive")
                return df
        except Exception as e:
            st.warning(f"⚠️ Error al cargar desde Google Drive: {e}")
    
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
            
            st.success("✅ Datos cargados desde archivo local (fallback)")
            return df
        else:
            st.error("❌ No se encontró el archivo local AO_GENERAL.txt")
    except Exception as e:
        st.error(f"❌ Error al cargar archivo local: {e}")
    
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
                st.success("✅ Archivos semanales cargados desde Google Drive")
                return archivos_fechas, service
        except Exception as e:
            st.warning(f"⚠️ Error al cargar archivos semanales desde Google Drive: {e}")
    
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
                st.success("✅ Archivos semanales cargados desde carpeta local (fallback)")
                return archivos_fechas, None  # None indica que es local
        else:
            st.warning("⚠️ No se encontró la carpeta local REPORTE SEMANAL")
    except Exception as e:
        st.error(f"❌ Error al cargar archivos locales: {e}")
    
    return [], None

def crear_tabla_interactiva(df, titulo, columna_volumen="VolumenHA", tab_key=""):
    """Crea una tabla interactiva con st.dataframe, jerarquía visual por Nivel y Elemento"""
    if df.empty:
        st.warning("No hay datos para mostrar")
        return
    # Verificar columnas necesarias
    required_columns = ["Nivel", "Elementos", columna_volumen]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        st.error(f"Faltan las siguientes columnas en los datos: {', '.join(missing_columns)}")
        st.info("Columnas disponibles: " + ", ".join(df.columns.tolist()))
        return
    # Filtrar filas válidas
    df_filtrado = df[df["Nivel"].notna() & (df["Nivel"].astype(str).str.strip() != "")]
    if df_filtrado.empty:
        st.warning("No hay datos con niveles válidos")
        return
    # Pivot o agrupación
    if "FC_CON_ESTADO" in df_filtrado.columns:
        pivot_table = df_filtrado.pivot_table(
            values=columna_volumen,
            index=["Nivel", "Elementos"],
            columns="FC_CON_ESTADO",
            aggfunc="sum",
            fill_value=0
        ).reset_index()
    else:
        st.info("No se encontró la columna 'FC_CON_ESTADO'. Mostrando resumen simple.")
        pivot_table = df_filtrado.groupby(["Nivel", "Elementos"])[columna_volumen].sum().reset_index()
        pivot_table = pivot_table.rename(columns={columna_volumen: "Total"})
    # Calcular totales y %
    if "Total" not in pivot_table.columns:
        numeric_columns = pivot_table.select_dtypes(include=[np.number]).columns
        if len(numeric_columns) > 0:
            pivot_table["Total"] = pivot_table[numeric_columns].sum(axis=1)
        else:
            pivot_table["Total"] = 0
    if "Total" in pivot_table.columns and pivot_table["Total"].sum() > 0:
        pivot_table["% Avance"] = (pivot_table["Total"] / pivot_table["Total"].sum() * 100).round(2)
    for col in pivot_table.select_dtypes(include=[np.number]).columns:
        pivot_table[col] = pivot_table[col].round(2)
    # Ordenar por Nivel y Elemento para jerarquía visual
    pivot_table = pivot_table.sort_values(["Nivel", "Elementos"]).reset_index(drop=True)
    st.subheader(titulo)
    col1, col2 = st.columns(2)
    with col1:
        try:
            niveles_raw = df_filtrado["Nivel"].dropna().unique()
            niveles_clean = [str(n).strip() for n in niveles_raw if str(n).strip()]
            niveles = ["Todos"] + sorted(niveles_clean)
            nivel_seleccionado = st.selectbox("Filtrar por Nivel:", niveles, key=f"nivel_{tab_key}")
        except Exception as e:
            st.error(f"Error al cargar niveles: {e}")
            nivel_seleccionado = "Todos"
    with col2:
        try:
            elementos_raw = df_filtrado["Elementos"].dropna().unique()
            elementos_clean = [str(e).strip() for e in elementos_raw if str(e).strip()]
            elementos = ["Todos"] + sorted(elementos_clean)
            elemento_seleccionado = st.selectbox("Filtrar por Elemento:", elementos, key=f"elemento_{tab_key}")
        except Exception as e:
            st.error(f"Error al cargar elementos: {e}")
            elemento_seleccionado = "Todos"
    df_filtrado_tabla = pivot_table.copy()
    try:
        if nivel_seleccionado != "Todos":
            df_filtrado_tabla = df_filtrado_tabla[df_filtrado_tabla["Nivel"] == nivel_seleccionado]
        if elemento_seleccionado != "Todos":
            df_filtrado_tabla = df_filtrado_tabla[df_filtrado_tabla["Elementos"] == elemento_seleccionado]
    except Exception as e:
        st.error(f"Error al aplicar filtros: {e}")
    try:
        st.dataframe(
            df_filtrado_tabla,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Nivel": st.column_config.TextColumn("Nivel", width="medium"),
                "Elementos": st.column_config.TextColumn("Elementos", width="large"),
                "Total": st.column_config.NumberColumn("Total", format="%.2f"),
                "% Avance": st.column_config.NumberColumn("% Avance", format="%.2f%%")
            }
        )
    except Exception as e:
        st.error(f"Error al mostrar tabla: {e}")
        st.dataframe(df_filtrado_tabla, use_container_width=True)
    if not df_filtrado_tabla.empty:
        try:
            total_sum = df_filtrado_tabla['Total'].sum()
            st.metric("Total General", f"{total_sum:.2f}")
        except Exception as e:
            st.error(f"Error al calcular total: {e}")

def mostrar_avance_semanal(use_local_files=False):
    """Muestra el avance semanal de hormigones"""
    if use_local_files:
        archivos_fechas, service = cargar_archivos_semanales_local()
    else:
        archivos_fechas, service = cargar_archivos_semanales()
    
    if not archivos_fechas:
        st.warning("No se encontraron archivos semanales")
        return
    
    # Procesar archivos
    lista_df = []
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
                nombre_archivo = f if use_local_files else f['name']
                st.warning(f"No se pudo leer el archivo: {nombre_archivo}")
                continue
                
            # Leer el archivo con el formato correcto
            dfw = pd.read_csv(fh, sep='\t', header=1, dtype=str, quoting=3)  # QUOTE_NONE
            dfw = dfw.dropna(how="all")
            
            # Limpiar columnas (remover comillas)
            dfw = dfw.rename(columns=lambda x: x.strip().replace('"', '') if isinstance(x, str) else x)
            
            # Limpiar datos (remover comillas de los valores)
            for col in dfw.columns:
                if dfw[col].dtype == 'object':
                    dfw[col] = dfw[col].astype(str).str.replace('"', '')
            
            # Verificar que exista la columna VolumenHA
            if "VolumenHA" not in dfw.columns:
                nombre_archivo = f if use_local_files else f['name']
                st.warning(f"Archivo {nombre_archivo} no tiene columna VolumenHA. Columnas disponibles: {list(dfw.columns)}")
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
                nombre_archivo = f if use_local_files else f['name']
                st.warning(f"Archivo {nombre_archivo} no tiene columna Hormigonado")
                continue
            
            # Solo filas con Nivel y Elementos válidos
            if "Nivel" in dfw.columns and "Elementos" in dfw.columns:
                dfw = dfw[dfw["Nivel"].notna() & (dfw["Nivel"].astype(str).str.strip() != "")]
                dfw = dfw[dfw["Elementos"].notna() & (dfw["Elementos"].astype(str).str.strip() != "")]
            else:
                nombre_archivo = f if use_local_files else f['name']
                st.warning(f"Archivo {nombre_archivo} no tiene columnas Nivel o Elementos")
                continue
            
            # Agrupar por Nivel y Elementos
            resumen = dfw.groupby(["Nivel", "Elementos"])["VolumenHA"].sum().reset_index()
            resumen["Fecha"] = fecha
            lista_df.append(resumen)
            
        except Exception as e:
            nombre_archivo = f if use_local_files else f['name']
            st.error(f"Error procesando archivo {nombre_archivo}: {e}")
            continue
    
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
    
    # Formatear columnas numéricas
    for col in pivot_semanal.select_dtypes(include=[np.number]).columns:
        pivot_semanal[col] = pivot_semanal[col].round(2)
    
    # Mostrar tabla
    st.subheader("Avance Semanal Hormigones")
    
    # Agregar filtros
    col1, col2 = st.columns(2)
    
    with col1:
        try:
            niveles_raw = df_semana["Nivel"].dropna().unique()
            niveles_clean = [str(n).strip() for n in niveles_raw if str(n).strip()]
            niveles = ["Todos"] + sorted(niveles_clean)
            nivel_seleccionado = st.selectbox("Filtrar por Nivel:", niveles, key="semanal_nivel")
        except Exception as e:
            st.error(f"Error al cargar niveles: {e}")
            nivel_seleccionado = "Todos"
    
    with col2:
        try:
            elementos_raw = df_semana["Elementos"].dropna().unique()
            elementos_clean = [str(e).strip() for e in elementos_raw if str(e).strip()]
            elementos = ["Todos"] + sorted(elementos_clean)
            elemento_seleccionado = st.selectbox("Filtrar por Elemento:", elementos, key="semanal_elemento")
        except Exception as e:
            st.error(f"Error al cargar elementos: {e}")
            elemento_seleccionado = "Todos"
    
    # Aplicar filtros
    df_filtrado_tabla = pivot_semanal.copy()
    try:
        if nivel_seleccionado != "Todos":
            df_filtrado_tabla = df_filtrado_tabla[df_filtrado_tabla["Nivel"] == nivel_seleccionado]
        if elemento_seleccionado != "Todos":
            df_filtrado_tabla = df_filtrado_tabla[df_filtrado_tabla["Elementos"] == elemento_seleccionado]
    except Exception as e:
        st.error(f"Error al aplicar filtros: {e}")
    
    # Mostrar tabla con st.dataframe
    try:
        st.dataframe(
            df_filtrado_tabla,
            use_container_width=True,
            hide_index=True
        )
    except Exception as e:
        st.error(f"Error al mostrar tabla: {e}")
        st.dataframe(df_filtrado_tabla, use_container_width=True)
    
    # Mostrar gráfico de tendencia
    if len(fechas) >= 2:
        st.subheader("Tendencia Semanal")
        df_tendencia = df_semana.groupby("Fecha")["VolumenHA"].sum().reset_index()
        fig = px.line(df_tendencia, x="Fecha", y="VolumenHA", 
                     title="Evolución del Volumen de Hormigón por Semana")
        st.plotly_chart(fig, use_container_width=True)

def mostrar_trisemanal(use_local_files=False):
    """Muestra comparación trisemanal"""
    if use_local_files:
        archivos_fechas, service = cargar_archivos_semanales_local()
    else:
        archivos_fechas, service = cargar_archivos_semanales()
    
    if len(archivos_fechas) < 2:
        st.warning("Se necesitan al menos 2 archivos semanales para la comparación trisemanal")
        return
    
    # Tomar solo los 2 últimos archivos
    archivos_fechas = archivos_fechas[-2:]
    
    # Procesar archivos
    lista_df = []
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
                nombre_archivo = f if use_local_files else f['name']
                st.warning(f"No se pudo leer el archivo: {nombre_archivo}")
                continue
                
            # Leer el archivo con el formato correcto
            dfw = pd.read_csv(fh, sep='\t', header=1, dtype=str, quoting=3)  # QUOTE_NONE
            dfw = dfw.dropna(how="all")
            
            # Limpiar columnas (remover comillas)
            dfw = dfw.rename(columns=lambda x: x.strip().replace('"', '') if isinstance(x, str) else x)
            
            # Limpiar datos (remover comillas de los valores)
            for col in dfw.columns:
                if dfw[col].dtype == 'object':
                    dfw[col] = dfw[col].astype(str).str.replace('"', '')
            
            # Verificar que exista la columna VolumenHA
            if "VolumenHA" not in dfw.columns:
                nombre_archivo = f if use_local_files else f['name']
                st.warning(f"Archivo {nombre_archivo} no tiene columna VolumenHA. Columnas disponibles: {list(dfw.columns)}")
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
                nombre_archivo = f if use_local_files else f['name']
                st.warning(f"Archivo {nombre_archivo} no tiene columna Hormigonado")
                continue
            
            # Solo filas con Nivel y Elementos válidos
            if "Nivel" in dfw.columns and "Elementos" in dfw.columns:
                dfw = dfw[dfw["Nivel"].notna() & (dfw["Nivel"].astype(str).str.strip() != "")]
                dfw = dfw[dfw["Elementos"].notna() & (dfw["Elementos"].astype(str).str.strip() != "")]
            else:
                nombre_archivo = f if use_local_files else f['name']
                st.warning(f"Archivo {nombre_archivo} no tiene columnas Nivel o Elementos")
                continue
            
            # Filtrar por FC_CON_TRISEMANAL = 'Semana 01' por defecto
            if "FC_CON_TRISEMANAL" in dfw.columns:
                dfw = dfw[dfw["FC_CON_TRISEMANAL"] == "Semana 01"]
            
            # Agrupar por Nivel y Elementos
            resumen = dfw.groupby(["Nivel", "Elementos"])["VolumenHA"].sum().reset_index()
            resumen["Fecha"] = fecha
            lista_df.append(resumen)
            
        except Exception as e:
            nombre_archivo = f if use_local_files else f['name']
            st.error(f"Error procesando archivo {nombre_archivo}: {e}")
            continue
    
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
    
    # Formatear columnas numéricas
    for col in pivot_trisemanal.select_dtypes(include=[np.number]).columns:
        pivot_trisemanal[col] = pivot_trisemanal[col].round(2)
    
    # Mostrar tabla
    st.subheader("Comparación Trisemanal")
    
    # Agregar filtros
    col1, col2 = st.columns(2)
    
    with col1:
        try:
            niveles_raw = df_semana["Nivel"].dropna().unique()
            niveles_clean = [str(n).strip() for n in niveles_raw if str(n).strip()]
            niveles = ["Todos"] + sorted(niveles_clean)
            nivel_seleccionado = st.selectbox("Filtrar por Nivel:", niveles, key="trisemanal_nivel")
        except Exception as e:
            st.error(f"Error al cargar niveles: {e}")
            nivel_seleccionado = "Todos"
    
    with col2:
        try:
            elementos_raw = df_semana["Elementos"].dropna().unique()
            elementos_clean = [str(e).strip() for e in elementos_raw if str(e).strip()]
            elementos = ["Todos"] + sorted(elementos_clean)
            elemento_seleccionado = st.selectbox("Filtrar por Elemento:", elementos, key="trisemanal_elemento")
        except Exception as e:
            st.error(f"Error al cargar elementos: {e}")
            elemento_seleccionado = "Todos"
    
    # Aplicar filtros
    df_filtrado_tabla = pivot_trisemanal.copy()
    try:
        if nivel_seleccionado != "Todos":
            df_filtrado_tabla = df_filtrado_tabla[df_filtrado_tabla["Nivel"] == nivel_seleccionado]
        if elemento_seleccionado != "Todos":
            df_filtrado_tabla = df_filtrado_tabla[df_filtrado_tabla["Elementos"] == elemento_seleccionado]
    except Exception as e:
        st.error(f"Error al aplicar filtros: {e}")
    
    # Mostrar tabla con st.dataframe
    try:
        st.dataframe(
            df_filtrado_tabla,
            use_container_width=True,
            hide_index=True
        )
    except Exception as e:
        st.error(f"Error al mostrar tabla: {e}")
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
            
            st.success("✅ Datos cargados desde archivo local")
            return df
        else:
            st.error("❌ No se encontró el archivo local AO_GENERAL.txt")
            return None
    except Exception as e:
        st.error(f"❌ Error al cargar archivo local: {e}")
        return None

def cargar_archivos_semanales_local():
    """Carga archivos semanales desde la carpeta local"""
    try:
        carpeta = "REPORTE SEMANAL"
        if not os.path.exists(carpeta):
            st.error(f"❌ Carpeta '{carpeta}' no encontrada")
            return [], None
        
        archivos = []
        for filename in os.listdir(carpeta):
            if filename.endswith('.txt') and 'AO_GENERAL' in filename:
                # Extraer fecha del nombre del archivo
                fecha_str = filename.split('_')[0]  # Tomar la primera parte antes del primer _
                
                # Intentar diferentes formatos de fecha
                fecha = None
                for formato in ['%d-%m-%Y', '%d-%m-%y', '%Y-%m-%d']:
                    try:
                        fecha = datetime.strptime(fecha_str, formato)
                        break
                    except ValueError:
                        continue
                
                if fecha:
                    archivos.append((filename, fecha))
        
        # Ordenar por fecha
        archivos.sort(key=lambda x: x[1])
        
        if not archivos:
            st.warning("❌ No se encontraron archivos semanales en la carpeta local")
            return [], None
        
        return archivos, None  # None indica que es local
        
    except Exception as e:
        st.error(f"❌ Error al cargar archivos locales: {e}")
        return [], None

def leer_archivo_local(filepath):
    """Lee directamente un archivo local"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        from io import StringIO
        return StringIO(content)
    except Exception as e:
        st.error(f"Error leyendo archivo local {filepath}: {e}")
        return None

# Función principal
def main():
    # Configuración en sidebar
    st.sidebar.header("⚙️ Configuración")
    
    # Opción para forzar uso de archivos locales
    use_local_files = st.sidebar.checkbox(
        "📁 Usar archivos locales (ignorar Google Drive)",
        key="main_local_checkbox",
        help="Marca esta opción si quieres usar archivos locales en lugar de Google Drive"
    )
    
    if use_local_files:
        st.sidebar.info("📁 Modo archivos locales activado")
        # Verificar archivos locales
        if not os.path.exists("AO_GENERAL.txt"):
            st.sidebar.error("❌ No se encontró AO_GENERAL.txt")
        else:
            st.sidebar.success("✅ AO_GENERAL.txt encontrado")
        
        if not os.path.exists("REPORTE SEMANAL"):
            st.sidebar.warning("⚠️ No se encontró carpeta REPORTE SEMANAL")
        else:
            weekly_files = [f for f in os.listdir("REPORTE SEMANAL") if f.endswith('_AO_GENERAL.txt')]
            if weekly_files:
                st.sidebar.success(f"✅ {len(weekly_files)} archivos semanales encontrados")
            else:
                st.sidebar.warning("⚠️ No se encontraron archivos semanales")
    
    # Debug: Verificar que los secretos estén configurados (solo si no se usan archivos locales)
    if not use_local_files:
        try:
            # Verificar que existan los secretos necesarios
            required_secrets = ["GOOGLE_CREDENTIALS", "FILE_ID_GENERAL", "FOLDER_ID_SEMANAL"]
            missing_secrets = []
            
            for secret in required_secrets:
                if secret not in st.secrets:
                    missing_secrets.append(secret)
            
            if missing_secrets:
                st.error(f"Faltan los siguientes secretos: {', '.join(missing_secrets)}")
                st.info("Configura estos secretos en Streamlit Cloud > Settings > Secrets")
                st.info("💡 Alternativamente, puedes usar archivos locales:")
                st.info("- Coloca AO_GENERAL.txt en la raíz del proyecto")
                st.info("- Coloca los archivos semanales en la carpeta 'REPORTE SEMANAL'")
                return
            
            st.success("✅ Todos los secretos configurados")
        
        except Exception as e:
            st.error(f"Error al verificar configuración: {e}")
            return
    
    # Verificar archivos locales como alternativa
    local_files_exist = False
    if os.path.exists("AO_GENERAL.txt"):
        st.info("📁 Archivo local AO_GENERAL.txt encontrado")
        local_files_exist = True
    
    if os.path.exists("REPORTE SEMANAL"):
        weekly_files = [f for f in os.listdir("REPORTE SEMANAL") if f.endswith('_AO_GENERAL.txt')]
        if weekly_files:
            st.info(f"📁 Carpeta local REPORTE SEMANAL encontrada con {len(weekly_files)} archivos")
            local_files_exist = True
    
    # Cargar datos
    if use_local_files:
        # Forzar uso de archivos locales
        df = cargar_datos_local()
    else:
        df = cargar_datos()
    
    if df is None:
        st.error("No se pudieron cargar los datos")
        if local_files_exist:
            st.info("💡 Se detectaron archivos locales. La aplicación intentará usarlos automáticamente.")
        else:
            st.info("💡 Para usar archivos locales:")
            st.info("1. Coloca AO_GENERAL.txt en la raíz del proyecto")
            st.info("2. Coloca los archivos semanales en la carpeta 'REPORTE SEMANAL'")
        return
    
    # Debug: Mostrar información sobre los datos
    st.success(f"✅ Datos cargados exitosamente: {len(df)} filas")
    st.info(f"Columnas disponibles: {', '.join(df.columns.tolist())}")
    
    # Mostrar primeras filas para debug
    with st.expander("🔍 Ver datos cargados (Debug)"):
        st.write("Primeras 5 filas:")
        st.dataframe(df.head(), use_container_width=True)
        
        st.write("Información del DataFrame:")
        st.write(f"- Filas: {len(df)}")
        st.write(f"- Columnas: {len(df.columns)}")
        st.write(f"- Columnas con datos: {df.columns.tolist()}")
    
    # Crear pestañas
    tabs = st.tabs([
        "📊 Avance General",
        "📈 Avance Semanal",
        "🔄 Avance Trisemanal"
    ])

    # Pestaña Avance General
    with tabs[0]:
        st.header("📊 Avance General de Obra")
        st.markdown("### Hormigones")
        crear_tabla_interactiva(df, "Avance de Hormigones", "VolumenHA", tab_key="hormigones_general")
        st.markdown("### Moldajes")
        crear_tabla_interactiva(df, "Avance de Moldajes", "AreaMoldaje", tab_key="moldajes_general")
        st.markdown("### Enfierraduras")
        crear_tabla_interactiva(df, "Avance de Enfierraduras", "Cuantia", tab_key="enfierraduras_general")

    # Pestaña Avance Semanal
    with tabs[1]:
        mostrar_avance_semanal(use_local_files)

    # Pestaña Avance Trisemanal
    with tabs[2]:
        mostrar_trisemanal(use_local_files)

# Ejecutar aplicación
if __name__ == "__main__":
    main() 