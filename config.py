from dotenv import load_dotenv
import os

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")
    FLASK_DEBUG = os.getenv("FLASK_DEBUG")
    FLASK_HOST = os.getenv("FLASK_HOST")
    FLASK_PORT = os.getenv("FLASK_PORT")
    VECTOR_DB_PATH = os.getenv("VECTOR_DB_PATH")
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")
    CHAT_MODEL = os.getenv("CHAT_MODEL")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    CLAUDE_KEY = os.getenv("CLAUDE_KEY")
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
    MAX_CONTEXT_LENGTH = os.getenv("MAX_CONTEXT_LENGTH")
    TOP_K_RESULTS = os.getenv("TOP_K_RESULTS")
    TEMPERATURE = os.getenv("TEMPERATURE")
    MAX_QUERY_LENGTH = os.getenv("MAX_QUERY_LENGTH")
    REQUEST_TIMEOUT = os.getenv("REQUEST_TIMEOUT")
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "./data/corpus_raw")
    DB_PATH = os.getenv("DB_PATH", "./data/app.db")
