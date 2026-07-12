# Agentic Skincare Backend

Proyecto backend para un asistente virtual de comercio de cuidado de la piel con IA, utilizando **LangGraph**, **Vertex AI (Gemini 2.5 Flash-Lite)** y **Feature Slice Architecture**.

## Prerrequisitos

1. **Google Cloud SDK**: Debes tener instalado y configurado `gcloud`.
2. **Autenticación en GCP**:
   ```bash
   gcloud auth login
   gcloud auth application-default login
   gcloud config set project skincare-ai-commerce
   ```
3. **Firestore**: Asegúrate de tener una base de datos de Firestore nativa creada (`gcloud firestore databases create --location=us-central1 --type=firestore-native`).

## Configuración del Entorno

1. El entorno virtual de Python está en la carpeta `venv`. Para activarlo en Windows:
   ```bash
   .\venv\Scripts\activate
   ```
   En macOS/Linux:
   ```bash
   source venv/bin/activate
   ```
2. Instala las dependencias (si no se han instalado):
   ```bash
   pip install -r requirements.txt
   ```
3. Crea tu archivo `.env` basándote en `.env.example`:
   ```env
   ENVIRONMENT=development
   GOOGLE_CLOUD_PROJECT=skincare-ai-commerce
   ```

## Arquitectura

El proyecto utiliza **Feature Slice Architecture**:
- `/core`: Contiene el estado global de LangGraph (`state.py`), el enrutador (`router.py`) y el grafo principal (`main_graph.py`).
- `/features/diagnostico_sintomas`: Subgrafo encargado del análisis de síntomas, imágenes (visual) y 'slot filling' conversacional.
- `/features/info_productos`: Subgrafo encargado del RAG contra la base de datos de Firestore.
- `/entrypoints`: Punto de entrada de la aplicación. En este caso `web.py` levanta una interfaz con **Gradio**.
- `/pdf_productos`: Directorio donde se deben colocar los PDFs de manuales e información de productos.
- `/scripts`: Scripts utilitarios, como `ingestar_pdfs.py`.

## Ingesta de PDFs (Base de Datos RAG)

1. Coloca los archivos `.pdf` con la información de los productos dentro del directorio `pdf_productos`.
2. Ejecuta el script de ingesta para procesarlos y guardar los embeddings (Vector Search) en Firestore:
   ```bash
   python scripts/ingestar_pdfs.py
   ```

## Ejecución del Servidor Web (Gradio)

Para levantar la interfaz conversacional, ejecuta:
```bash
python entrypoints/web.py
```
Por defecto, la interfaz estará disponible en `http://localhost:7860`.
Podrás escribir texto sobre tus síntomas o dudas de productos y adjuntar imágenes de tu piel para un análisis visual.
