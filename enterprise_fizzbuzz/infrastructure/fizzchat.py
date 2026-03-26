import time
import random
import logging
import math
import string
from collections import defaultdict, Counter
from typing import Optional, List, Dict, Any, Union

from enterprise_fizzbuzz.domain.interfaces import IRuleEngine, IRule
from enterprise_fizzbuzz.domain.models import FizzBuzzResult

logger = logging.getLogger(__name__)

def tokenize(text: str) -> List[str]:
    return [w.strip(string.punctuation).lower() for w in text.split()]

class TFIDFVectorizer:
    def __init__(self):
        self.vocab = {}
        self.idf = {}

    def fit(self, docs: List[str]):
        doc_count = len(docs)
        if doc_count == 0:
            return
        word_doc_counts = Counter()
        for doc in docs:
            words = set(tokenize(doc))
            for w in set(words):
                if w:
                    word_doc_counts[w] += 1
        
        self.vocab = {w: i for i, w in enumerate(word_doc_counts.keys())}
        self.idf = {w: math.log(doc_count / count) + 1 for w, count in word_doc_counts.items()}

    def transform(self, docs: List[str]) -> List[Dict[int, float]]:
        vectors = []
        for doc in docs:
            words = tokenize(doc)
            tf = Counter([w for w in words if w])
            vec = {}
            for w, count in tf.items():
                if w in self.vocab:
                    vec[self.vocab[w]] = count * self.idf[w]
            vectors.append(vec)
        return vectors

def cosine_similarity(v1: Dict[int, float], v2: Dict[int, float]) -> float:
    dot = sum(v1.get(k, 0) * v2.get(k, 0) for k in set(v1) | set(v2))
    mag1 = math.sqrt(sum(v ** 2 for v in v1.values()))
    mag2 = math.sqrt(sum(v ** 2 for v in v2.values()))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)

class ChromaDB:
    """Simulated vector database for RAG context retrieval."""
    def __init__(self):
        self.collection_name = "historical_fizzbuzz_runs"
        self.embedding_dimension = 1536
        self.vectorizer = TFIDFVectorizer()
        self.docs = []
        self.metadatas = []
        self.ids = []
        self.vectors = []

    def add(self, documents: List[str], metadatas: List[dict], ids: List[str]):
        self.docs.extend(documents)
        self.metadatas.extend(metadatas)
        self.ids.extend(ids)
        self.vectorizer.fit(self.docs)
        self.vectors = self.vectorizer.transform(self.docs)
        
    def query(self, query_texts: Union[str, List[str]], n_results: int = 1) -> Dict[str, List[List[str]]]:
        if isinstance(query_texts, str):
            query_texts = [query_texts]
            
        q_vectors = self.vectorizer.transform(query_texts)
        results = {"documents": []}
        
        for q_vec in q_vectors:
            scored = []
            for i, d_vec in enumerate(self.vectors):
                score = cosine_similarity(q_vec, d_vec)
                scored.append((score, self.docs[i]))
            
            scored.sort(key=lambda x: x[0], reverse=True)
            results["documents"].append([doc for score, doc in scored[:n_results]])
            
        return results

class LLM:
    """Simulated N-gram parameter LLM for FizzBuzz inference."""
    def __init__(self, n_gram_size: int = 1, temperature: float = 0.7):
        self.n_gram_size = n_gram_size
        self.temperature = temperature
        self.ngrams = defaultdict(list)
        
    def train(self, corpus: str):
        tokens = corpus.split()
        for i in range(len(tokens) - self.n_gram_size):
            state = tuple(tokens[i:i+self.n_gram_size])
            next_token = tokens[i+self.n_gram_size]
            self.ngrams[state].append(next_token)
            
    def generate(self, prompt: str, context: str = "", max_tokens: int = 1, temperature: float = None) -> str:
        temp = temperature if temperature is not None else self.temperature
        
        tokens = prompt.split()
        output = []
        
        for _ in range(max_tokens):
            if len(tokens) < self.n_gram_size:
                state = tuple(tokens)
            else:
                state = tuple(tokens[-self.n_gram_size:])
                
            choices = self.ngrams.get(state, [])
            if not choices:
                break
                
            if temp == 0.0:
                counts = Counter(choices)
                # Sort counts to make most_common completely deterministic
                sorted_choices = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
                next_token = sorted_choices[0][0]
            else:
                counts = Counter(choices)
                vocab = list(counts.keys())
                probs = []
                for c in counts.values():
                    try:
                        probs.append(math.exp(math.log(c) / temp))
                    except OverflowError:
                        probs.append(float('inf'))
                
                if any(p == float('inf') for p in probs):
                    inf_indices = [i for i, p in enumerate(probs) if p == float('inf')]
                    next_token = vocab[random.choice(inf_indices)]
                else:
                    total = sum(probs)
                    probs = [p / total for p in probs]
                    next_token = random.choices(vocab, weights=probs)[0]
                
            output.append(next_token)
            tokens.append(next_token)
            
        return " ".join(output)

class FizzChatEngine(IRuleEngine):
    """
    FizzBuzz LLM RAG Pipeline (FizzChat).
    Instead of calculating n % 3, the system embeds the integer into a high-dimensional 
    vector space, performs a semantic search against a distributed ChromaDB instance, 
    and uses an integrated N-gram parameter LLM to 'hallucinate' whether the number is 
    Fizz, Buzz, or FizzBuzz. Includes an RLHF mechanism for Bob McFizzington.
    """
    def __init__(self, chroma: Optional[ChromaDB] = None, llm: Optional[LLM] = None):
        self.chroma = chroma or ChromaDB()
        self.llm = llm or LLM()
        
        # Pre-train the RAG pipeline and LLM
        if not self.chroma.docs:
            docs = []
            for i in range(1, 101):
                res = "FizzBuzz" if i % 15 == 0 else "Fizz" if i % 3 == 0 else "Buzz" if i % 5 == 0 else str(i)
                docs.append(f"What is the FizzBuzz result for {i}? {res}")
            self.chroma.add(docs, [{"source": "wikipedia"} for _ in docs], [str(i) for i in range(1, 101)])
            
        if not self.llm.ngrams:
            # Simple corpus: questions and answers so the N-gram model can predict the next word
            corpus = " ".join(docs)
            # Add some "hallucinations" to the corpus to make it interesting
            corpus += " Evaluate FizzBuzz for 1? 1 Evaluate FizzBuzz for 2? 2 Evaluate FizzBuzz for 3? Fizz Evaluate FizzBuzz for 4? 4 Evaluate FizzBuzz for 5? Buzz Evaluate FizzBuzz for 6? Bazz Evaluate FizzBuzz for 15? FizzBizz"
            self.llm.train(corpus)

    def evaluate(self, number: int, rules: List[IRule]) -> FizzBuzzResult:
        start = time.perf_counter_ns()
        
        # RAG Pipeline
        context_res = self.chroma.query([f"What is the FizzBuzz result for {number}?"], n_results=1)
        context = ""
        if isinstance(context_res, dict) and "documents" in context_res and context_res["documents"]:
            docs = context_res["documents"][0]
            if docs:
                context = docs[0]
                
        output = self.llm.generate(f"Evaluate FizzBuzz for {number}?", context=context, max_tokens=1)
        
        # Validate output
        valid_outputs = ["Fizz", "Buzz", "FizzBuzz", str(number)]
        if output not in valid_outputs:
            output = self.apply_rlhf_correction(number, output)
            
        elapsed = time.perf_counter_ns() - start
        
        return FizzBuzzResult(
            number=number,
            output=output,
            matched_rules=[],
            processing_time_ns=elapsed,
        )

    def apply_rlhf_correction(self, number: int, wrong_output: str) -> str:
        """
        Reinforcement Learning from Human Feedback (RLHF).
        Pages Bob McFizzington to manually correct model drift.
        """
        logger.warning(f"Model drift detected! LLM hallucinated '{wrong_output}' for {number}.")
        logger.warning("Paging Bob McFizzington for emergency RLHF correction...")
        time.sleep(0.01) # Simulate Bob's response time
        
        # Bob's deterministic correction
        if number % 15 == 0:
            return "FizzBuzz"
        elif number % 3 == 0:
            return "Fizz"
        elif number % 5 == 0:
            return "Buzz"
        else:
            return str(number)

    async def evaluate_async(self, number: int, rules: List[IRule]) -> FizzBuzzResult:
        # FizzChat does not currently support asynchronous tensor operations
        return self.evaluate(number, rules)
