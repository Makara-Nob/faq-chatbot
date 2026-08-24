"""
LangSmith Evaluation for FAQ Chatbot
Evaluates retrieval and generation quality
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402
from langsmith import Client  # noqa: E402
from langsmith.evaluation import evaluate  # noqa: E402

from app.services.rag_pipeline import FAQChatbot  # noqa: E402

# Load environment variables
load_dotenv()


def create_evaluation_dataset():
    """Create test dataset in LangSmith"""
    
    print("\n📊 Creating evaluation dataset...\n")
    
    client = Client()
    
    dataset_name = "FAQ_Chatbot_Tests"
    
    # Create dataset
    try:
        client.create_dataset(
            dataset_name=dataset_name,
            description="Test cases for FAQ Chatbot evaluation"
        )
        print(f"✅ Dataset created: {dataset_name}")
    except Exception as e:
        print(f"Dataset might already exist: {e}")
    
    # Test examples
    test_cases = [
        {
            "question": "How do I reset my password?",
            "expected_answer": "Settings, Security, Reset Password",
            "category": "authentication"
        },
        {
            "question": "What payment methods do you accept?",
            "expected_answer": "credit cards, PayPal, bank transfers",
            "category": "payments"
        },
        {
            "question": "How long does shipping take?",
            "expected_answer": "5-7 business days, express 2-3 days",
            "category": "shipping"
        },
        {
            "question": "Can I return items?",
            "expected_answer": "30-day returns",
            "category": "returns"
        },
        {
            "question": "What is your refund policy?",
            "expected_answer": "5-10 business days",
            "category": "refunds"
        },
        {
            "question": "How do I contact support?",
            "expected_answer": "email or phone, 9AM-5PM EST",
            "category": "support"
        }
    ]
    
    # Add examples to dataset
    for test_case in test_cases:
        try:
            client.create_example(
                inputs={"question": test_case["question"]},
                outputs={
                    "expected_answer": test_case["expected_answer"],
                    "category": test_case["category"]
                },
                dataset_name=dataset_name
            )
        except Exception as e:
            print(f"Could not add example: {e}")
    
    print(f"✅ Added {len(test_cases)} test cases\n")
    return dataset_name


def run_evaluation(dataset_name: str):
    """Run evaluation on test dataset"""
    
    print("\n🧪 Starting evaluation...\n")
    
    # Initialize chatbot
    chatbot = FAQChatbot()
    chatbot.initialize("data/faqs.txt")
    
    # Test function
    def test_faq_chatbot(inputs):
        """Test the FAQ chatbot"""
        result = chatbot.answer_question(inputs["question"])
        return {
            "answer": result["answer"],
            "sources_used": len(result["source_docs"])
        }
    
    # Simple evaluators
    def answer_length_evaluator(run, example):
        """Check if answer is not empty"""
        answer = run.outputs.get("answer", "")
        return {
            "key": "answer_not_empty",
            "score": 1.0 if len(answer) > 10 else 0.0
        }
    
    def sources_retrieved_evaluator(run, example):
        """Check if sources were retrieved"""
        sources = run.outputs.get("sources_used", 0)
        return {
            "key": "sources_retrieved",
            "score": 1.0 if sources > 0 else 0.0
        }
    
    # Run evaluation
    try:
        results = evaluate(
            test_faq_chatbot,
            data=dataset_name,
            evaluators=[
                answer_length_evaluator,
                sources_retrieved_evaluator
            ],
            experiment_prefix="FAQ_Chatbot_Eval",
            verbose=True
        )
        
        print("\n✅ Evaluation complete!")
        print("\n📊 Results summary:")
        print(f"   Total tests run: {len(results)}")
        
        return results
        
    except Exception as e:
        print(f"❌ Evaluation error: {e}")
        return None


def manual_evaluation():
    """Manual evaluation interface"""
    
    print("\n" + "="*60)
    print("🧪 MANUAL EVALUATION MODE")
    print("="*60 + "\n")
    
    # Initialize chatbot
    chatbot = FAQChatbot()
    chatbot.initialize("data/faqs.txt")
    
    test_questions = [
        "How do I reset my password?",
        "What payment methods do you accept?",
        "How long does shipping take?",
        "Can I return items?",
        "What is your privacy policy?",
    ]
    
    results = []
    
    for question in test_questions:
        print(f"\n📝 Question: {question}")
        print("-" * 60)
        
        result = chatbot.answer_question(question)
        
        print(f"\n🤖 Answer: {result['answer']}")
        print(f"\n📄 Retrieved {len(result['source_docs'])} documents")
        
        if result['source_docs']:
            for i, doc in enumerate(result['source_docs'], 1):
                preview = doc[:80] + "..." if len(doc) > 80 else doc
                print(f"   Doc {i}: {preview}")
        
        # Get user feedback
        print("\n" + "-" * 60)
        feedback = input("Rate this answer (1-5, or skip): ").strip()
        
        if feedback.isdigit() and 1 <= int(feedback) <= 5:
            results.append({
                "question": question,
                "rating": int(feedback),
                "sources_retrieved": len(result['source_docs'])
            })
    
    # Show summary
    if results:
        print("\n" + "="*60)
        print("📊 EVALUATION SUMMARY")
        print("="*60)
        
        avg_rating = sum(r['rating'] for r in results) / len(results)
        avg_sources = sum(r['sources_retrieved'] for r in results) / len(results)
        
        print(f"\nQuestions evaluated: {len(results)}")
        print(f"Average rating: {avg_rating:.2f}/5.0")
        print(f"Average sources retrieved: {avg_sources:.2f}")
        
        print("\nDetailed results:")
        for r in results:
            stars = "⭐" * r['rating']
            print(f"  {r['question']}: {stars}")
        
        print("\n" + "="*60 + "\n")


def main():
    """Main evaluation interface"""
    
    print("\n" + "="*60)
    print("📊 FAQ CHATBOT EVALUATION")
    print("="*60 + "\n")
    
    print("Choose evaluation mode:")
    print("1. Manual evaluation (rate answers yourself)")
    print("2. Automated evaluation (LangSmith)")
    print("3. Exit\n")
    
    choice = input("Enter choice (1-3): ").strip()
    
    if choice == "1":
        manual_evaluation()
    
    elif choice == "2":
        # Create dataset
        dataset_name = create_evaluation_dataset()
        
        # Run evaluation
        run_evaluation(dataset_name)
        
        print("\n✅ Check LangSmith dashboard: https://smith.langchain.com/")
    
    elif choice == "3":
        print("\nGoodbye!\n")
    
    else:
        print("\n❌ Invalid choice. Please try again.\n")


if __name__ == "__main__":
    main()