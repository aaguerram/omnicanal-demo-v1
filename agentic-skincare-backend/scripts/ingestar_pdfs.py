import os
import glob
from dotenv import load_dotenv
import pdfplumber
from langchain_core.documents import Document
from langchain_google_vertexai import VertexAIEmbeddings
from langchain_google_firestore import FirestoreVectorStore
from google.cloud import firestore

load_dotenv()

def ingestar():
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "skincare-ai-commerce")
    pdf_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pdf_productos")
    
    # 1. Leer PDFs
    documents = []
    pdf_files = glob.glob(os.path.join(pdf_dir, "*.pdf"))
    
    if not pdf_files:
        print(f"No se encontraron PDFs en {pdf_dir}")
        return

    for pdf_path in pdf_files:
        print(f"Procesando {pdf_path}...")
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        
        if text:
            # En un entorno real se usaría RecursiveCharacterTextSplitter para mejorar el RAG
            doc = Document(
                page_content=text,
                metadata={"source": os.path.basename(pdf_path)}
            )
            documents.append(doc)
    
    if not documents:
        print("No se pudo extraer texto de los PDFs.")
        return
        
    print(f"Se extrajeron {len(documents)} documentos. Generando embeddings y guardando...")
    
    # 2. Embeddings
    embeddings = VertexAIEmbeddings(
        model_name="text-embedding-004", 
        project=project_id
    )
    
    # 3. Firestore Vector Store
    db = firestore.Client(project=project_id)
    
    # FirestoreVectorStore requiere que la base de datos esté configurada en GCP
    try:
        vector_store = FirestoreVectorStore.from_documents(
            documents=documents,
            embedding=embeddings,
            collection="catalogo_productos",
            client=db
        )
        print("Ingesta completada exitosamente.")
    except Exception as e:
        print(f"Ocurrió un error al guardar en Firestore: {e}")
        print("Asegúrate de haber inicializado Firestore en tu proyecto GCP.")

if __name__ == "__main__":
    ingestar()
