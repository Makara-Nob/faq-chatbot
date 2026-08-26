"""
FAQ Chatbot RAG Pipeline
Handles retrieval and generation with Claude
"""

import logging
import os

from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_anthropic import ChatAnthropic
from langchain_community.vectorstores import Chroma

# getLogger(__name__) gives a logger named "app.services.rag_pipeline", so its
# output is tagged with where it came from and it inherits the app-wide config
# set up in app/core/logging.py. No print() in library code: prints have no
# level, no timestamp, no request id, and bypass your log tooling entirely.
log = logging.getLogger(__name__)


class FAQChatbot:
    def __init__(self):
        """Initialize the FAQ chatbot with Claude and vector store"""
        
        # Initialize Claude (Anthropic API)
        self.llm = ChatAnthropic(
            model="claude-3-5-sonnet-20241022",
            temperature=0.7,
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )
        
        # Initialize embeddings (free alternative to OpenAI)
        # Using Chroma's default embeddings
        self.embeddings = None  # Chroma handles embeddings by default
        
        self.vector_store = None
        self.retriever = None
        self.qa_chain = None
        
    def load_faq_data(self, file_path: str):
        """Load FAQ data from text file"""
        # %s is a lazy placeholder: logging only builds the string if this level
        # is actually enabled. Prefer this over f-strings in log calls.
        log.info("loading FAQs from %s", file_path)

        with open(file_path, encoding='utf-8') as f:
            faq_content = f.read()
        
        # Split FAQs into chunks
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            separators=["\n\nQ:", "\n\nA:", "\n", " "]
        )
        
        chunks = splitter.split_text(faq_content)
        log.info("split into %d chunks", len(chunks))

        return chunks
    
    def setup_vector_store(self, chunks: list):
        """Create vector store from FAQ chunks"""
        log.info("creating vector embeddings for %d chunks", len(chunks))

        # Use Chroma with default embeddings (no API key needed)
        self.vector_store = Chroma.from_texts(
            texts=chunks,
            persist_directory="./chroma_db",
            collection_name="faqs"
        )

        log.info("vector store created")
        
        # Create retriever
        self.retriever = self.vector_store.as_retriever(
            search_type="similarity",
            search_kwargs={"k": 3}  # Return top 3 relevant docs
        )
    
    def setup_qa_chain(self):
        """Setup QA chain with custom prompt"""
        
        # Custom prompt that ensures grounded answers
        prompt_template = """Use the following FAQ information to answer the question.
If the answer is not in the FAQs, say "I don't have information about that."
Do not make up information.

FAQ Context:
{context}

Question: {question}

Answer: """
        
        prompt = PromptTemplate(
            template=prompt_template,
            input_variables=["context", "question"]
        )
        
        # Create QA chain
        self.qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            chain_type="stuff",
            retriever=self.retriever,
            prompt=prompt,
            return_source_documents=True,
            verbose=False
        )

        log.info("QA chain configured")
    
    def answer_question(self, question: str) -> dict:
        """
        Answer a question using the RAG pipeline
        
        Args:
            question: User's question
            
        Returns:
            dict with answer and source documents
        """
        result = self.qa_chain({"query": question})
        
        return {
            "question": question,
            "answer": result["result"],
            "source_docs": [
                doc.page_content for doc in result.get("source_documents", [])
            ]
        }
    
    def initialize(self, faq_file: str):
        """Complete initialization pipeline"""
        log.info("starting FAQ chatbot initialization")

        # Load FAQs
        chunks = self.load_faq_data(faq_file)

        # Setup vector store
        self.setup_vector_store(chunks)

        # Setup QA chain
        self.setup_qa_chain()

        log.info("FAQ chatbot ready")


# Example usage
if __name__ == "__main__":
    # Only when run directly as a script (python -m app.services.rag_pipeline).
    # When imported by the app, app/core/logging.py has already configured
    # logging, so we must NOT reconfigure it there - only here.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    # Initialize chatbot
    chatbot = FAQChatbot()
    chatbot.initialize("data/faqs.txt")
    
    # Test questions
    test_questions = [
        "How do I reset my password?",
        "What payment methods do you accept?",
        "How long does shipping take?",
        "Can I return items?"
    ]
    
    print("\n" + "="*60)
    print("TESTING FAQ CHATBOT")
    print("="*60 + "\n")
    
    for question in test_questions:
        print(f"❓ Question: {question}")
        result = chatbot.answer_question(question)
        print(f"✅ Answer: {result['answer']}\n")
        print(f"📄 Sources used: {len(result['source_docs'])} document(s)\n")
        print("-" * 60 + "\n")