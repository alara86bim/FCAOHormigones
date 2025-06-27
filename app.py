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
        
        # Crear las credenciales
        creds = service_account.Credentials.from_service_account_info(
            creds_dict,
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
    """Crea una tabla interactiva con st.dataframe"""
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
    
    # Formatear columnas numéricas
    for col in pivot_table.select_dtypes(include=[np.number]).columns:
        pivot_table[col] = pivot_table[col].round(2)
    
    # Mostrar tabla
    st.subheader(titulo)
    
    # Agregar filtros
    col1, col2 = st.columns(2)
    
    with col1:
        niveles = ["Todos"] + sorted(df_filtrado["Nivel"].unique().tolist())
        nivel_seleccionado = st.selectbox("Filtrar por Nivel:", niveles)
    
    with col2:
        elementos = ["Todos"] + sorted(df_filtrado["Elementos"].unique().tolist())
        elemento_seleccionado = st.selectbox("Filtrar por Elemento:", elementos)
    
    # Aplicar filtros
    df_filtrado_tabla = pivot_table.copy()
    if nivel_seleccionado != "Todos":
        df_filtrado_tabla = df_filtrado_tabla[df_filtrado_tabla["Nivel"] == nivel_seleccionado]
    if elemento_seleccionado != "Todos":
        df_filtrado_tabla = df_filtrado_tabla[df_filtrado_tabla["Elementos"] == elemento_seleccionado]
    
    # Mostrar tabla con st.dataframe
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
    
    # Mostrar resumen
    if not df_filtrado_tabla.empty:
        st.metric("Total General", f"{df_filtrado_tabla['Total'].sum():.2f}")

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
    
    # Formatear columnas numéricas
    for col in pivot_semanal.select_dtypes(include=[np.number]).columns:
        pivot_semanal[col] = pivot_semanal[col].round(2)
    
    # Mostrar tabla
    st.subheader("Avance Semanal Hormigones")
    
    # Agregar filtros
    col1, col2 = st.columns(2)
    
    with col1:
        niveles = ["Todos"] + sorted(df_semana["Nivel"].unique().tolist())
        nivel_seleccionado = st.selectbox("Filtrar por Nivel:", niveles, key="semanal_nivel")
    
    with col2:
        elementos = ["Todos"] + sorted(df_semana["Elementos"].unique().tolist())
        elemento_seleccionado = st.selectbox("Filtrar por Elemento:", elementos, key="semanal_elemento")
    
    # Aplicar filtros
    df_filtrado_tabla = pivot_semanal.copy()
    if nivel_seleccionado != "Todos":
        df_filtrado_tabla = df_filtrado_tabla[df_filtrado_tabla["Nivel"] == nivel_seleccionado]
    if elemento_seleccionado != "Todos":
        df_filtrado_tabla = df_filtrado_tabla[df_filtrado_tabla["Elementos"] == elemento_seleccionado]
    
    # Mostrar tabla con st.dataframe
    st.dataframe(
        df_filtrado_tabla,
        use_container_width=True,
        hide_index=True
    )
    
    # Mostrar gráfico de tendencia
    if len(fechas) >= 2:
        st.subheader("Tendencia Semanal")
        df_tendencia = df_semana.groupby("Fecha")["VolumenHA"].sum().reset_index()
        fig = px.line(df_tendencia, x="Fecha", y="VolumenHA", 
                     title="Evolución del Volumen de Hormigón por Semana")
        st.plotly_chart(fig, use_container_width=True)

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
    
    # Formatear columnas numéricas
    for col in pivot_trisemanal.select_dtypes(include=[np.number]).columns:
        pivot_trisemanal[col] = pivot_trisemanal[col].round(2)
    
    # Mostrar tabla
    st.subheader("Comparación Trisemanal")
    
    # Agregar filtros
    col1, col2 = st.columns(2)
    
    with col1:
        niveles = ["Todos"] + sorted(df_semana["Nivel"].unique().tolist())
        nivel_seleccionado = st.selectbox("Filtrar por Nivel:", niveles, key="trisemanal_nivel")
    
    with col2:
        elementos = ["Todos"] + sorted(df_semana["Elementos"].unique().tolist())
        elemento_seleccionado = st.selectbox("Filtrar por Elemento:", elementos, key="trisemanal_elemento")
    
    # Aplicar filtros
    df_filtrado_tabla = pivot_trisemanal.copy()
    if nivel_seleccionado != "Todos":
        df_filtrado_tabla = df_filtrado_tabla[df_filtrado_tabla["Nivel"] == nivel_seleccionado]
    if elemento_seleccionado != "Todos":
        df_filtrado_tabla = df_filtrado_tabla[df_filtrado_tabla["Elementos"] == elemento_seleccionado]
    
    # Mostrar tabla con st.dataframe
    st.dataframe(
        df_filtrado_tabla,
        use_container_width=True,
        hide_index=True
    )
    
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

# Función principal
def main():
    # Debug: Verificar que los secretos estén configurados
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
            return
        
        st.success("✅ Todos los secretos configurados")
    
    except Exception as e:
        st.error(f"Error al verificar configuración: {e}")
        return
    
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