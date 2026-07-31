import os
import glob
import logging
from dotenv import load_dotenv

load_dotenv(override=True)

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import AzureSearch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger("indexer")

def index_docs():
    '''
    Reads the PDF's, chunks them, and upload them to Azure AI search
    '''

    current_dir = os.path.dirname(os.path.abspath(__file__))
    data_folder = os.path.join(current_dir, "../data")

    azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    openai_api_key = os.getenv("OPENAI_API_KEY")

    logger.info("="*60)
    logger.info("Environment Configuration Check: ")
    logger.info(f"AZURE_OPENAI_ENDPOINT: {azure_openai_endpoint} ")
    logger.info(f"OPENAI_API: {openai_api_key} ")
    logger.info("="*60)

    required_vars=["OPENAI_API_KEY","AZURE_SEARCH_ENDPOINT","AZURE_SEARCH_API_KEY","AZURE_SEARCH_INDEX_NAME"]

    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        logger.error(f"Missing required environment variables : {missing_vars}")
        logger.error("Please check your env file and esnure all required vars are set")
        return
    # Initialize embedding model
    try:
        logger.info("Initializing Open AI Embeddings....")
        embeddings=OpenAIEmbeddings(
            api_key=os.getenv("OPENAI_API_KEY"),
            model="text-embedding-3-small"
        )
        logger.info("Embedding model intiliazation is successful")

    except Exception as e:
        logger.error(f"Failed to initialize embeddings: {e}")
        logger.error("Please verify your Azure endpoint")
        return

    #Initialize vector store
    index_name = os.getenv("AZURE_SEARCH_INDEX_NAME")
    try:
        vector_store=AzureSearch(
            azure_search_endpoint=os.getenv("AZURE_SEARCH_ENDPOINT"),
            azure_search_key=os.getenv("AZURE_SEARCH_API_KEY"),
            index_name=index_name,
            embedding_function=embeddings.embed_query
        )
        logger.info(f"Vector Store Initialized for Index : {index_name}")

    except Exception as e:
        logger.error(f"Failed to initialize Azure Search: {e}")
        logger.error("Please verify your Azure Search endpoint api key and index name")
        return

    #Find PDF files
    pdf_files = glob.glob(os.path.join(data_folder,"*.pdf"))
    if not pdf_files:
        logger.warning(f"No PDF's found in {data_folder}.Please add files")
    logger.info(f"Found {len(pdf_files)} PDF's to process: {[os.path.basename(f) for f in pdf_files]}")

    all_splits=[]

    #Process each pdf
    for pdf_path in pdf_files:
        try:
            logger.info(f"Loading: {os.path.basename(pdf_path)}")
            loader=PyPDFLoader(pdf_path)
            raw_docs=loader.load()

            text_splitter=RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200
            )

            splits=text_splitter.split_documents(raw_docs)
            for split in splits:
                split.metadata["source"]=os.path.basename(pdf_path)

            all_splits.extend(splits)
            logger.info(f"Split into {len(splits)} chunks.")

        except Exception as e:
            logger.error(f"failed to process {pdf_path}: {e}")

    #Upload to Azure
    if all_splits:
        logger.info(f"Uploading {len(all_splits)} chunks to Azure AI Search Index: {index_name}")
        try:
            vector_store.add_documents(documents=all_splits)
            logger.info("="*60)
            logger.info("Indexing Complete! Knowledge Base is ready...")

        except Exception as e:
            logger.error(f"failed to upload the documents to Azure Search: {e}")
            logger.error("Please search the Azure Search configuration and try again")
    else:
        logger.warning("No documents were processed")

if __name__=="__main__":
    index_docs()
