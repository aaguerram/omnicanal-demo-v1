import glob
import os

import pdfplumber
from dotenv import load_dotenv
from google.cloud import firestore
from langchain_aws import BedrockEmbeddings
from langchain_core.documents import Document
from langchain_google_firestore import FirestoreVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

# amazon.titan-embed-text-v2:0 rechaza inputs de mas de 50000 caracteres
# (ValidationException: "expected maxLength: 50000") -- el vademecum completo
# solo (un PDF) ya extrae ~96000 caracteres de texto, asi que cada PDF entero
# como un unico Document (como hacia esta ingesta antes de este chunking) no
# entra. chunk_size deja margen bajo el limite real del modelo.
CHUNK_SIZE = 4000
CHUNK_OVERLAP = 400

# Mismos defaults que core/settings.py (Settings.bedrock_embedding_model_id /
# aws_region) -- repetidos acá en vez de importar core.settings porque este
# script corre standalone (`python scripts/ingestar_pdfs.py`), sin el
# directorio raiz del proyecto en sys.path.
BEDROCK_EMBEDDING_MODEL_ID = os.environ.get(
    "BEDROCK_EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0"
)
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

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

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )
    chunks = splitter.split_documents(documents)

    print(
        f"Se extrajeron {len(documents)} documentos, divididos en {len(chunks)} "
        "chunks. Generando embeddings y guardando..."
    )
    
    # 2. Embeddings
    embeddings = BedrockEmbeddings(
        model_id=BEDROCK_EMBEDDING_MODEL_ID,
        region_name=AWS_REGION,
    )
    
    # 3. Firestore Vector Store
    db = firestore.Client(project=project_id)
    
    # FirestoreVectorStore requiere que la base de datos esté configurada en GCP
    try:
        FirestoreVectorStore.from_documents(
            documents=chunks,
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
