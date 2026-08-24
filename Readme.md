# FAQ Chatbot with RAG + LangSmith Evaluation

A production-ready FAQ chatbot built with Claude, LangChain, and Chroma vector database. Includes LangSmith evaluation for monitoring retrieval and generation quality.

**Tech Stack:**

- 🤖 Claude (Anthropic) - LLM
- 🔗 LangChain - Orchestration
- 🗃️ Chroma - Vector Database
- 📊 LangSmith - Evaluation & Monitoring

---

## 📋 Prerequisites

- **Python 3.10.5** or higher
- **Windows, macOS, or Linux**
- **API Keys:**
  - Anthropic API Key (Claude): https://console.anthropic.com/
  - LangSmith API Key: https://smith.langchain.com/

---

## 🚀 Quick Start (5 minutes)

### Step 1: Create Project Folder

```powershell
mkdir faq-chatbot
cd faq-chatbot
```

### Step 2: Clone/Download Files

Download these files into the folder:

- `rag_pipeline.py`
- `main.py`
- `evaluate_chatbot.py`
- `requirements.txt`
- `.gitignore`

### Step 3: Create Virtual Environment

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

If this fails, run:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Step 4: Install Dependencies

```powershell
pip install -r requirements.txt
```

### Step 5: Create Data Folder & FAQ File

```powershell
mkdir data
```

Create `data/faqs.txt` with this content:

```
Q: How do I reset my password?
A: Go to Settings → Security → Click "Reset Password" → Check your email for reset link

Q: What payment methods do you accept?
A: We accept all major credit cards, PayPal, and bank transfers

Q: How long does shipping take?
A: Standard shipping takes 5-7 business days. Express shipping takes 2-3 business days

Q: Can I return items?
A: Yes, we offer 30-day returns on most items. Electronics have 14-day returns

Q: What is your refund policy?
A: Refunds are processed within 5-10 business days after we receive your return

Q: Do you offer customer support?
A: Yes, email support@example.com or call 1-800-XXX-XXXX. Hours: 9AM-5PM EST

Q: How do I track my order?
A: After shipping, you'll receive an email with a tracking number

Q: What is your privacy policy?
A: We protect your data. See our privacy policy at example.com/privacy
```

### Step 6: Create .env File

In project root, create `.env`:

```
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxx
LANGCHAIN_API_KEY=ls_xxxxxxxxxxxx
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=faq-chatbot
```

**Get your keys:**

1. **Anthropic:** https://console.anthropic.com/
2. **LangSmith:** https://smith.langchain.com/

### Step 7: Test the Chatbot

```powershell
python main.py
```

Try these questions:

- "How do I reset my password?"
- "What payment methods do you accept?"
- "How long does shipping take?"

Type `quit` to exit.

---

## 📊 Running Evaluation

```powershell
python evaluate_chatbot.py
```

Choose:

1. **Manual Evaluation** - You rate answers (1-5 stars)
2. **Automated Evaluation** - LangSmith tests automatically

### What Gets Evaluated

**Retrieval Layer:**

- Are relevant documents retrieved? (Context Precision)
- Are all necessary docs retrieved? (Context Recall)

**Generation Layer:**

- Is the answer grounded in retrieved docs? (Faithfulness)
- Does it answer the user's question? (Relevance)

---

## 📁 Project Structure

```
faq-chatbot/
├── venv/                     # Virtual environment (created)
├── data/
│   └── faqs.txt             # Your FAQ data
├── chroma_db/               # Vector database (created)
├── rag_pipeline.py          # RAG logic
├── main.py                  # Interactive chatbot
├── evaluate_chatbot.py      # Evaluation tool
├── requirements.txt         # Dependencies
├── .env                     # API keys (KEEP SECRET!)
├── .gitignore               # Ignore files
└── README.md                # This file
```

---

## 🔧 How It Works

### 1. Loading FAQs

```
data/faqs.txt → Split into chunks → Vector embeddings
```

### 2. User Question

```
"How do I reset my password?"
  ↓
Vector search (find similar FAQs)
  ↓
Retrieve top 3 relevant docs
  ↓
Claude generates answer from docs
```

### 3. Evaluation

```
Check 1: Did we retrieve the RIGHT documents?
Check 2: Is the answer grounded in those documents?
Check 3: Did it actually answer the question?
```

---

## 🎯 Customization

### Change FAQ Data

Edit `data/faqs.txt` and restart:

```powershell
python main.py
```

### Change LLM Model

In `rag_pipeline.py`, line 26:

```python
self.llm = ChatAnthropic(
    model="claude-3-5-sonnet-20241022",  # Change this
    temperature=0.7,
    api_key=os.getenv("ANTHROPIC_API_KEY")
)
```

**Available models:**

- `claude-3-5-sonnet-20241022` (recommended - fast & smart)
- `claude-3-opus-20250219` (most powerful)
- `claude-3-haiku-20250307` (fastest)

### Adjust Retrieval Settings

In `rag_pipeline.py`, line 91:

```python
self.retriever = self.vector_store.as_retriever(
    search_type="similarity",
    search_kwargs={"k": 3}  # Return 3 documents (change here)
)
```

### Change Temperature

Lower = more consistent, Higher = more creative

In `rag_pipeline.py`, line 26:

```python
temperature=0.7,  # 0-1 scale (0.7 recommended for FAQs)
```

---

## 🐛 Troubleshooting

### Error: "No module named langchain"

```powershell
pip install -r requirements.txt
```

### Error: "ANTHROPIC_API_KEY not found"

- Check `.env` file exists
- Check key is correct
- Restart Python

### Error: "data/faqs.txt not found"

```powershell
mkdir data
# Create faqs.txt in data folder
```

### Chatbot gives generic answers

- Your FAQ data might be too short
- Add more detailed Q&A pairs to `data/faqs.txt`
- Increase chunk overlap in `rag_pipeline.py`

### LangSmith not recording traces

- Verify `LANGCHAIN_TRACING_V2=true` in `.env`
- Check API key is correct
- Restart Python after changing `.env`

---

## 📊 View Results in LangSmith

After running evaluation:

1. Go to: https://smith.langchain.com/
2. Click on your project (FAQ_Chatbot_Eval)
3. View:
   - Traces (what the bot did)
   - Experiments (test results)
   - Metrics (accuracy, latency, etc.)

---

## 🎓 Learning Resources

**RAG Basics:**

- https://docs.langchain.com/langsmith/evaluate-rag-tutorial

**LangSmith Docs:**

- https://docs.smith.langchain.com/

**Claude API:**

- https://docs.anthropic.com/

---

## 📝 Next Steps

1. ✅ Run chatbot locally
2. ✅ Test with your FAQ data
3. ✅ Run evaluation and check LangSmith
4. ✅ Adjust prompts based on results
5. Deploy to production

---

## 💡 Tips for Better Results

1. **Quality Data:** FAQs should be clear and specific
2. **Test Cases:** Create 20+ test questions for evaluation
3. **Prompt Engineering:** Adjust the prompt template in `rag_pipeline.py`
4. **Chunk Size:** Experiment with `chunk_size` parameter
5. **Monitor:** Always check LangSmith for quality drift

---

## 📄 License

MIT License - Feel free to use for personal projects

---

## 🤝 Support

Having issues? Check:

1. `.env` file has correct API keys
2. `data/faqs.txt` exists
3. Virtual environment is activated
4. All dependencies installed (`pip install -r requirements.txt`)

---

**Happy Building! 🚀**
