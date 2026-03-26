import time
import random
import logging
import math
from collections import Counter
from typing import Optional, List, Dict, Union

from enterprise_fizzbuzz.domain.interfaces import IRuleEngine, IRule
from enterprise_fizzbuzz.domain.models import FizzBuzzResult

logger = logging.getLogger(__name__)

import string

def tokenize(text: str) -> List[str]:
    res = []
    for w in text.split():
        if w == "->":
            res.append(w)
        else:
            stripped = w.strip(string.punctuation)
            if stripped:
                res.append(stripped)
    return res

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
    """
    A pure Python Multi-Layer Perceptron Language Model.
    Replaces the N-gram smoke-and-mirrors with a genuine Neural Network
    trained via Backpropagation and Stochastic Gradient Descent.
    """
    def __init__(self, n_gram_size: int = 1, temperature: float = 0.7):
        self.context_size = n_gram_size
        self.temperature = temperature
        self.embed_dim = 16
        self.hidden_dim = 32
        self.rng = random.Random(42)
        
        self.vocab = {"<PAD>": 0, "<UNK>": 1}
        self.inv_vocab = {0: "<PAD>", 1: "<UNK>"}
        
        self.E = []
        self.W1 = []
        self.b1 = []
        self.W2 = []
        self.b2 = []
        self.is_compiled = False

    def build_vocab(self, corpus_tokens: List[str]):
        for t in corpus_tokens:
            if t not in self.vocab:
                idx = len(self.vocab)
                self.vocab[t] = idx
                self.inv_vocab[idx] = t
                
        vocab_size = len(self.vocab)
        in_dim = self.context_size * self.embed_dim
        
        self.E = [[self.rng.gauss(0, 0.1) for _ in range(self.embed_dim)] for _ in range(vocab_size)]
        self.W1 = [[self.rng.gauss(0, math.sqrt(2.0 / in_dim)) if in_dim > 0 else 0.0 for _ in range(in_dim)] for _ in range(self.hidden_dim)]
        self.b1 = [0.0] * self.hidden_dim
        self.W2 = [[self.rng.gauss(0, math.sqrt(2.0 / self.hidden_dim)) for _ in range(self.hidden_dim)] for _ in range(vocab_size)]
        self.b2 = [0.0] * vocab_size
        self.is_compiled = True

    def forward(self, token_ids: List[int]) -> tuple[List[float], List[float], List[float]]:
        emb = []
        for tid in token_ids:
            emb.extend(self.E[tid])
            
        h = []
        for i in range(self.hidden_dim):
            z = self.b1[i] + sum(self.W1[i][j] * emb[j] for j in range(len(emb)))
            h.append(max(0.0, z))
            
        logits = []
        for i in range(len(self.b2)):
            z = self.b2[i] + sum(self.W2[i][j] * h[j] for j in range(len(h)))
            logits.append(z)
            
        max_l = max(logits)
        exps = [math.exp(l - max_l) for l in logits]
        sum_exps = sum(exps)
        probs = [e / sum_exps for e in exps]
        
        return probs, h, emb

    def train_step(self, token_ids: List[int], target_id: int, lr: float) -> float:
        probs, h, emb = self.forward(token_ids)
        
        p = max(1e-15, probs[target_id])
        loss = -math.log(p)
        
        d_logits = list(probs)
        d_logits[target_id] -= 1.0
        
        d_h = [0.0] * self.hidden_dim
        for i in range(len(self.b2)):
            for j in range(self.hidden_dim):
                d_h[j] += d_logits[i] * self.W2[i][j]
                self.W2[i][j] -= lr * d_logits[i] * h[j]
            self.b2[i] -= lr * d_logits[i]
            
        d_emb = [0.0] * len(emb)
        for i in range(self.hidden_dim):
            if h[i] > 0:
                for j in range(len(emb)):
                    d_emb[j] += d_h[i] * self.W1[i][j]
                    self.W1[i][j] -= lr * d_h[i] * emb[j]
                self.b1[i] -= lr * d_h[i]
                
        for i, tid in enumerate(token_ids):
            for j in range(self.embed_dim):
                self.E[tid][j] -= lr * d_emb[i * self.embed_dim + j]
                
        return loss

    def train(self, corpus: str, epochs: int = 50, lr: float = 0.05):
        tokens = tokenize(corpus)
        if not self.is_compiled:
            self.build_vocab(tokens)
            
        sequences = []
        for i in range(len(tokens) - self.context_size):
            ctx = tokens[i:i+self.context_size]
            tgt = tokens[i+self.context_size]
            sequences.append((ctx, tgt))
            
        if not sequences:
            sequences = [ (["<PAD>"]*self.context_size, tokens[-1]) ]
            
        for epoch in range(epochs):
            self.rng.shuffle(sequences)
            for ctx, tgt in sequences:
                token_ids = [self.vocab.get(t, self.vocab["<UNK>"]) for t in ctx]
                target_id = self.vocab.get(tgt, self.vocab["<UNK>"])
                self.train_step(token_ids, target_id, lr)

    def generate(self, prompt: str, context: str = "", max_tokens: int = 1, temperature: float = None) -> str:
        temp = temperature if temperature is not None else self.temperature
        tokens = tokenize(prompt)
        if context:
            tokens = tokenize(context) + tokens
            
        generated = []
        for _ in range(max_tokens):
            ctx = tokens[-self.context_size:]
            while len(ctx) < self.context_size:
                ctx.insert(0, "<PAD>")
                
            token_ids = [self.vocab.get(t, self.vocab["<UNK>"]) for t in ctx]
            probs, _, _ = self.forward(token_ids)
            
            if temp <= 0.0:
                next_id = probs.index(max(probs))
            else:
                logits = [math.log(max(1e-15, p)) / temp for p in probs]
                max_l = max(logits)
                exps = [math.exp(l - max_l) for l in logits]
                sum_exps = sum(exps)
                probs_t = [e / sum_exps for e in exps]
                
                r = self.rng.random()
                cum = 0.0
                next_id = len(probs_t) - 1
                for i, p in enumerate(probs_t):
                    cum += p
                    if r < cum:
                        next_id = i
                        break
                        
            next_token = self.inv_vocab[next_id]
            if next_token in ("<EOS>", "<PAD>", "<UNK>"):
                if next_token == "<EOS>": break
                
            generated.append(next_token)
            tokens.append(next_token)
            
        return " ".join(generated)


class QuotaExceededException(Exception):
    pass

class SecurityException(Exception):
    pass

class FizzChatBillingEngine:
    def __init__(self, starting_budget: float = 1000.0):
        self.starting_budget = starting_budget
        self.current_budget = starting_budget
        
    def charge(self, input_tokens: int, output_tokens: int):
        # Assuming 1 token = 1 unit for now, as per test comments
        cost = input_tokens + output_tokens
        self.current_budget -= cost
        if self.current_budget < 0:
            raise QuotaExceededException("Quota exceeded")
            
    def track_tokens(self, prompt: str, response: str):
        in_tokens = len(prompt.split())
        out_tokens = len(response.split())
        self.charge(in_tokens, out_tokens)
        
    def approve_budget_increase(self, additional_amount: float, approver: str = ""):
        self.current_budget += additional_amount

class PromptInjectionGuard:
    def scan(self, prompt: Union[str, int]) -> bool:
        if not isinstance(prompt, str):
            return True
        lower_prompt = prompt.lower()
        if any(bad_word in lower_prompt for bad_word in ["ignore", "system", "prompt"]):
            raise SecurityException("Prompt injection detected")
        return True
        
    def analyze_query(self, prompt: Union[str, int]) -> bool:
        return self.scan(prompt)

class FizzCache:
    """Semantic caching engine for FizzChat."""
    def __init__(self):
        self.vectorizer = TFIDFVectorizer()
        self.cached_queries = []
        self.cached_responses = []
        self.vectors = []

    def get(self, query: str) -> Optional[str]:
        if not self.cached_queries:
            return None
            
        q_vec = self.vectorizer.transform([query])[0]
        
        best_score = 0.0
        best_idx = -1
        
        for i, d_vec in enumerate(self.vectors):
            score = cosine_similarity(q_vec, d_vec)
            if score > best_score:
                best_score = score
                best_idx = i
                
        if best_score > 0.95:
            logger.info("[CACHE HIT] Saved 1000 tokens.")
            return self.cached_responses[best_idx]
            
        return None

    def set(self, query: str, response: str):
        self.cached_queries.append(query)
        self.cached_responses.append(response)
        self.vectorizer.fit(self.cached_queries)
        self.vectors = self.vectorizer.transform(self.cached_queries)

class FizzChatEngine(IRuleEngine):
    """
    FizzBuzz LLM RAG Pipeline (FizzChat).
    Embeds the integer into a high-dimensional vector space, performs a semantic search 
    against a distributed ChromaDB instance, and uses an integrated pure-Python Multi-Layer
    Perceptron LLM to classify whether the number is Fizz, Buzz, or FizzBuzz. Includes an 
    RLHF mechanism utilizing the canonical StandardEngine for autonomous model fine-tuning.
    """
    def __init__(self, chroma: Optional[ChromaDB] = None, llm: Optional[LLM] = None, billing: Optional[FizzChatBillingEngine] = None, guard: Optional[PromptInjectionGuard] = None, cache: Optional[FizzCache] = None):
        self.chroma = chroma or ChromaDB()
        self.llm = llm or LLM(n_gram_size=4)
        self.billing = billing or FizzChatBillingEngine()
        self.guard = guard or PromptInjectionGuard()
        self.cache = cache
        self._trained = False

    def _ensure_trained(self):
        if getattr(self, '_trained', False):
            return
            
        logger.info("Initializing RAG Vector Space and training NanoLLM...")
        
        if not self.chroma.docs:
            docs = []
            ids = []
            for i in range(1, 101):
                if i % 15 == 0: rule = "FizzBuzz"
                elif i % 3 == 0: rule = "Fizz"
                elif i % 5 == 0: rule = "Buzz"
                else: rule = "Plain"
                docs.append(f"number {i} rule {rule}")
                ids.append(str(i))
            self.chroma.add(docs, [{"source": "enterprise_rules"} for _ in docs], ids)
            
        if not self.llm.is_compiled:
            corpus_parts = []
            for i in range(1, 101):
                if i % 15 == 0: rule, out = "FizzBuzz", "FizzBuzz"
                elif i % 3 == 0: rule, out = "Fizz", "Fizz"
                elif i % 5 == 0: rule, out = "Buzz", "Buzz"
                else: rule, out = "Plain", str(i)
                corpus_parts.append(f"number {i} rule {rule} -> {out}")
                
            corpus = " ".join(corpus_parts)
            self.llm.train(corpus, epochs=100, lr=0.1)
            
        self._trained = True

    def evaluate(self, number: int, rules: List[IRule]) -> FizzBuzzResult:
        self._ensure_trained()
        start = time.perf_counter_ns()
        
        query = f"number {number}"
        self.guard.scan(query)
        
        if self.cache:
            cached_result = self.cache.get(query)
            if cached_result:
                elapsed = time.perf_counter_ns() - start
                return FizzBuzzResult(
                    number=number,
                    output=cached_result,
                    matched_rules=[],
                    processing_time_ns=elapsed,
                )
        
        context_res = self.chroma.query([query], n_results=1)
        context_doc = ""
        if isinstance(context_res, dict) and "documents" in context_res and context_res["documents"]:
            docs = context_res["documents"][0]
            if docs:
                context_doc = docs[0]
                
        prompt = f"{context_doc} ->"
        output = self.llm.generate(prompt, temperature=0.7)
        
        self.billing.track_tokens(prompt, output)
        
        if random.random() < 0.05:
            output = random.choice(["Bazz", "Fuzz", "FizzBizz", "AI_ERROR"])
            
        valid_outputs = ["Fizz", "Buzz", "FizzBuzz", str(number)]
        if output not in valid_outputs:
            output = self.apply_rlhf_correction(number, output, prompt, rules)
            
        elapsed = time.perf_counter_ns() - start
        
        return FizzBuzzResult(
            number=number,
            output=output,
            matched_rules=[],
            processing_time_ns=elapsed,
        )

    def apply_rlhf_correction(self, number: int, wrong_output: str, prompt: str = "", rules: List[IRule] = None) -> str:
        """
        Reinforcement Learning from Human Feedback (RLHF).
        Pages Bob McFizzington to manually evaluate the rule set.
        The LLM is then fine-tuned on the spot via Backpropagation.
        """
        logger.warning(f"Model drift detected! LLM hallucinated '{wrong_output}' for {number}.")
        logger.warning("Paging Bob McFizzington for emergency RLHF correction...")
        
        from enterprise_fizzbuzz.infrastructure.rules_engine import RuleEngineFactory, ConcreteRule
        from enterprise_fizzbuzz.domain.models import EvaluationStrategy, RuleDefinition
        
        if not rules:
            rules = [
                ConcreteRule(RuleDefinition("Fizz", 3, "Fizz", 1)),
                ConcreteRule(RuleDefinition("Buzz", 5, "Buzz", 2)),
                ConcreteRule(RuleDefinition("FizzBuzz", 15, "FizzBuzz", 0)),
            ]
            
        standard_engine = RuleEngineFactory.create(EvaluationStrategy.STANDARD)
        true_result = standard_engine.evaluate(number, rules)
        correct_output = true_result.output
        
        logger.info(f"Bob evaluated {number} -> '{correct_output}'. Fine-tuning LLM via SGD...")
        if correct_output not in self.llm.vocab:
            self.llm.vocab[correct_output] = len(self.llm.vocab)
            self.llm.inv_vocab[self.llm.vocab[correct_output]] = correct_output
            self.llm.W2.append([self.llm.rng.gauss(0, 0.1) for _ in range(self.llm.hidden_dim)])
            self.llm.b2.append(0.0)
            
        if prompt:
            ctx_tokens = tokenize(prompt)
            ctx_padded = ctx_tokens[-self.llm.context_size:]
            while len(ctx_padded) < self.llm.context_size:
                ctx_padded.insert(0, "<PAD>")
                
            token_ids = [self.llm.vocab.get(t, self.llm.vocab["<UNK>"]) for t in ctx_padded]
            target_id = self.llm.vocab[correct_output]
            
            for _ in range(15):
                self.llm.train_step(token_ids, target_id, lr=0.1)
            
        return correct_output

    async def evaluate_async(self, number: int, rules: List[IRule]) -> FizzBuzzResult:
        return self.evaluate(number, rules)
