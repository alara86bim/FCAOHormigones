# Dashboard de Control de Avance de Obra

Este proyecto es un dashboard interactivo en **Streamlit** para el control de avance de hormigones, moldajes y enfierraduras, con visualización de reportes semanales y trisemanales. Los datos se leen automáticamente desde Google Drive usando la API oficial.

## Características
- Visualización de avance por Hormigones, Moldajes y Enfierraduras
- Reporte semanal y trisemanales con comparación y variaciones
- Tablas jerárquicas y subtotales por nivel
- Filtros interactivos y gráficos de tendencia
- **Datos siempre actualizados** desde Google Drive

## Estructura de datos
- **AO_GENERAL.txt**: archivo principal de avance general (en Google Drive)
- **REPORTE SEMANAL/**: carpeta con archivos semanales de avance (en Google Drive)

## Despliegue en Streamlit Cloud

### 1. Sube tu código a GitHub
Asegúrate de que tu `.gitignore` excluya archivos de datos y credenciales.

### 2. Configura los secretos en Streamlit Cloud
En la sección **Secrets** de tu proyecto, pega el bloque de tu Service Account de Google Cloud, por ejemplo:

```toml
[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = """-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----"""
client_email = "..."
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."

FILE_ID_GENERAL = "ID_DE_AO_GENERAL.txt"
FOLDER_ID_SEMANAL = "ID_DE_LA_CARPETA_REPORTE_SEMANAL"
```

- **FILE_ID_GENERAL**: ID del archivo AO_GENERAL.txt en Google Drive
- **FOLDER_ID_SEMANAL**: ID de la carpeta con los reportes semanales

### 3. Comparte los archivos de Google Drive
- Comparte AO_GENERAL.txt y la carpeta REPORTE SEMANAL con el email de tu Service Account (ejemplo: `xxxx@xxxx.iam.gserviceaccount.com`)

### 4. Instala dependencias
El archivo `requirements.txt` incluye:
- streamlit
- pandas
- st-aggrid
- plotly
- google-api-python-client
- google-auth
- google-auth-oauthlib
- google-auth-httplib2

### 5. Ejecuta localmente (opcional)
Si quieres probar localmente, puedes usar tu propio `credentials.json` y configurar los IDs en un archivo `.streamlit/secrets.toml`.

### 6. Despliega en Streamlit Cloud
- Conecta tu repo en [Streamlit Cloud](https://share.streamlit.io/)
- ¡Listo! Tu dashboard leerá siempre los datos más recientes de Google Drive.

---

**Autor:** Tu nombre aquí

¿Dudas? Abre un issue o contacta al autor. 