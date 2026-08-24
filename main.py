"""
Interactive FAQ Chatbot
Run this to chat with the FAQ bot
"""

import os
from dotenv import load_dotenv
from rag_pipeline import FAQChatbot

# Load environment variables
load_dotenv()

def main():
    """Main chatbot interface"""
    
    print("\n" + "="*60)
    print("🤖 FAQ CHATBOT WITH LANGSMITH EVALUATION")
    print("="*60)
    print("\nInitializing chatbot...\n")
    
    # Check if FAQ file exists
    if not os.path.exists("data/faqs.txt"):
        print("❌ Error: data/faqs.txt not found!")
        print("Please create the FAQ data file first.")
        return
    
    # Initialize chatbot
    chatbot = FAQChatbot()
    chatbot.initialize("data/faqs.txt")
    
    print("\n" + "="*60)
    print("💬 Chat with the FAQ Bot")
    print("="*60)
    print("\nType your questions below.")
    print("Type 'quit' or 'exit' to stop.\n")
    
    # Chat loop
    while True:
        try:
            user_question = input("\n❓ You: ").strip()
            
            if user_question.lower() in ['quit', 'exit', 'q']:
                print("\n👋 Thanks for using FAQ Chatbot! Goodbye.\n")
                break
            
            if not user_question:
                print("Please enter a question.")
                continue
            
            print("\n🔍 Searching FAQs...")
            result = chatbot.answer_question(user_question)
            
            print(f"\n🤖 Bot: {result['answer']}")
            
            # Show source documents
            if result['source_docs']:
                print(f"\n📄 Source documents used:")
                for i, doc in enumerate(result['source_docs'], 1):
                    preview = doc[:100] + "..." if len(doc) > 100 else doc
                    print(f"   {i}. {preview}")
            
        except KeyboardInterrupt:
            print("\n\n👋 Chat interrupted. Goodbye!\n")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            print("Please try again.\n")


if __name__ == "__main__":
    main()