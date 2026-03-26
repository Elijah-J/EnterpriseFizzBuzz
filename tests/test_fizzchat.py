import pytest
from enterprise_fizzbuzz.domain.interfaces import IRuleEngine
from enterprise_fizzbuzz.domain.models import FizzBuzzResult

# Expected to fail in TDD since it's not implemented yet
from enterprise_fizzbuzz.infrastructure.fizzchat import (
    FizzChatEngine, 
    ChromaDB, 
    LLM,
    TFIDFVectorizer
)

def test_tfidf_vectorizer_explicit():
    """Explicitly test the TF-IDF embedding and cosine similarity."""
    vectorizer = TFIDFVectorizer()
    docs = [
        "fizz buzz",
        "enterprise software architecture",
        "fizz fizz fizz"
    ]
    vectorizer.fit(docs)
    vectors = vectorizer.transform(docs)
    
    # Basic check that vectors were created
    assert len(vectors) == 3
    assert isinstance(vectors[0], dict)
    
def test_chromadb_retrieval():
    """Test ChromaDB successfully retrieves the most relevant context."""
    db = ChromaDB()
    documents = [
        "Rule for 3 is Fizz",
        "Rule for 5 is Buzz",
        "Rule for 15 is FizzBuzz"
    ]
    metadatas = [{"val": 3}, {"val": 5}, {"val": 15}]
    ids = ["doc1", "doc2", "doc3"]
    
    db.add(documents=documents, metadatas=metadatas, ids=ids)
    
    # Query for something closely matching doc2
    results = db.query(["What is the rule for 5?"], n_results=1)
    
    # Should retrieve the "Rule for 5 is Buzz" document
    assert len(results["documents"][0]) == 1
    assert "Buzz" in results["documents"][0][0]

def test_llm_ngram_generation():
    """Test the N-gram / text generation model."""
    llm = LLM(n_gram_size=2, temperature=0.0)
    corpus = "the quick brown fox jumps over the lazy dog " * 5
    llm.train(corpus)
    
    # Deterministic generation with temp=0
    out1 = llm.generate("the quick", max_tokens=3, temperature=0.0)
    out2 = llm.generate("the quick", max_tokens=3, temperature=0.0)
    
    assert out1 == out2
    assert len(out1) > 0
    
    # Non-deterministic generation with high temp
    llm_random = LLM(n_gram_size=1, temperature=10.0)
    llm_random.train("A B A C A D A E A F ")
    
    # Collect outputs at high temperature; they should eventually differ
    outputs = set()
    for _ in range(10):
        outputs.add(llm_random.generate("A", max_tokens=1, temperature=10.0))
    
    # Should have more than 1 unique continuation for "A"
    assert len(outputs) > 1

@pytest.fixture
def engine():
    """Instantiate the FizzChatEngine with real dependencies."""
    db = ChromaDB()
    db.add(
        documents=["3 Fizz", "5 Buzz", "15 FizzBuzz"], 
        metadatas=[{"k": "v"}, {"k": "v"}, {"k": "v"}], 
        ids=["1", "2", "3"]
    )
    
    llm = LLM(n_gram_size=1, temperature=0.0)
    # Train LLM to just output Fizz, Buzz, FizzBuzz deterministically for simple prompts
    llm.train("Evaluate FizzBuzz for 3? Fizz Evaluate FizzBuzz for 5? Buzz Evaluate FizzBuzz for 15? FizzBuzz Evaluate FizzBuzz for 2? 2 Evaluate FizzBuzz for 98? 98 ")
    
    return FizzChatEngine(chroma=db, llm=llm)

def test_implements_iruleengine(engine):
    """Verify that FizzChatEngine implements IRuleEngine."""
    assert isinstance(engine, IRuleEngine)

@pytest.mark.parametrize("number,expected_output", [
    (3, "Fizz"),
    (5, "Buzz"),
    (15, "FizzBuzz"),
    (2, "2"),
    (98, "98"),
])
def test_fizzchat_correct_returns(engine, number, expected_output):
    """Verify that FizzChatEngine returns the correct FizzBuzz strings using the real LLM."""
    rules = []
    
    result = engine.evaluate(number, rules)
    
    assert isinstance(result, FizzBuzzResult)
    assert result.output == expected_output
    assert result.number == number

def test_rlhf_bob_correction():
    """Verify the RLHF mechanism where Bob corrects an LLM hallucination."""
    db = ChromaDB()
    llm = LLM(n_gram_size=1, temperature=0.0)
    # Train the LLM to output garbage so that it triggers RLHF
    llm.train("Evaluate FizzBuzz for 3? Bazz ")
    
    engine = FizzChatEngine(chroma=db, llm=llm)
    
    number = 3
    result = engine.evaluate(number, [])
    
    # Engine should detect the hallucination ("Bazz" is invalid), consult Bob (RLHF), and correct the output to "Fizz"
    assert isinstance(result, FizzBuzzResult)
    assert result.output == "Fizz"
