# FizzSearch -- Full-Text Search Engine

## The Problem

The Enterprise FizzBuzz Platform generates data at every layer. The event sourcing journal records every state transition. The write-ahead intent log captures every pending operation. The audit trail logs every authorization decision. The OpenTelemetry collector accumulates spans across every subsystem boundary. The CDC stream emits change events for every persistence mutation. The compliance engine records every SOX, GDPR, and HIPAA control point evaluation. The FizzBuzz evaluator itself produces results -- billions of them across enterprise deployments -- each carrying metadata about which rules fired, which middleware transformed them, which cache line served them, and which strategy resolved ties.

All of this data is write-only.

The platform can produce data. It cannot search it. An operator who needs to find every evaluation where rule "Fizz" fired for multiples of 7 through 21 must write custom Python to iterate the event store. An auditor investigating a compliance anomaly must export journal entries to an external tool. A developer debugging a cache coherence issue must parse MESI state transition logs by hand. The platform has a regex engine (`FizzRegex`) that compiles and executes regular expressions -- but regex operates on individual strings. It has no concept of a document collection, no inverted index, no relevance ranking, no query language that can express "find all evaluations where the result contained 'Fizz' AND the cache state was MODIFIED, ranked by recency."

Every production search system -- Elasticsearch, Solr, Lucene, Meilisearch, Typesense -- is built on the same foundational data structure: the inverted index. An inverted index maps terms to the documents that contain them, enabling sub-linear lookup across arbitrarily large collections. On top of the inverted index sit the components that make search useful: analyzers that normalize text into indexable terms, scoring models that rank results by relevance, query parsers that translate human intent into index operations, and aggregation frameworks that compute statistics across result sets without loading individual documents.

The platform has none of this. It has 116 infrastructure modules, 300,000 lines of code, a columnar storage engine, a MapReduce framework, a SQL query engine, a graph database, and a spatial database. It does not have a search engine. An operator cannot type a query and find things. This is the gap between a data platform and an information retrieval system. FizzSearch closes it.

## The Vision

FizzSearch is a full-text search engine for the Enterprise FizzBuzz Platform, implementing the core information retrieval stack from first principles. It provides inverted index construction with posting lists, configurable analyzer pipelines (tokenization, filtering, stemming, stop words, synonyms), BM25 relevance scoring, a boolean query model with AND/OR/NOT operators, phrase queries with positional indexing, fuzzy matching via edit distance automata, faceted search for categorical drill-down, aggregation framework (terms, histogram, date_histogram, stats, cardinality), segment-based index architecture with tiered merge policies, near-real-time search via searchable refresh intervals, typed field mappings (text, keyword, numeric, date, geo_point), hit highlighting with fragment extraction, a structured query DSL, and scroll-based deep pagination. Every component is implemented from scratch -- no external search library, no Whoosh, no Lucene bindings. The inverted index is hand-built. The BM25 scorer computes term frequency and inverse document frequency from the posting lists directly. The analyzer pipeline processes Unicode text through a chain of character filters, tokenizers, and token filters. The query parser builds an abstract syntax tree and optimizes it before execution.

## Key Components

### `fizzsearch.py` (~3,500 lines): FizzSearch Full-Text Search Engine

---

### 1. Document Model & Field Mappings

The atomic unit of search is the document. A document is a collection of named fields, each with a declared type that determines how the field is indexed, stored, and queried.

- **`FieldType`** (enum): Declares the indexing behavior for a field:
  - `TEXT` -- analyzed, tokenized, indexed for full-text search. The field value passes through the analyzer pipeline before indexing. Positional information is recorded for phrase queries. The original value is optionally stored for retrieval
  - `KEYWORD` -- not analyzed, indexed as a single exact-match token. Used for structured data: status codes, identifiers, enum values, tags. Supports term queries, prefix queries, and terms aggregations
  - `NUMERIC` -- indexed as a numeric value supporting range queries and numeric aggregations. Internally stored as a sorted numeric index alongside the inverted index. Supports `INTEGER`, `LONG`, `FLOAT`, `DOUBLE` subtypes
  - `DATE` -- a numeric field with date-specific parsing and formatting. Accepts ISO 8601 strings, epoch milliseconds, and configurable date format patterns. Supports `date_histogram` aggregation with calendar-aware interval bucketing
  - `GEO_POINT` -- a geographic coordinate (latitude, longitude) indexed for bounding box and distance queries. Stored as a quantized integer pair for efficient range scanning. Supports `geo_distance` and `geo_bounding_box` queries
  - `BOOLEAN` -- indexed as a two-term keyword field (`true`/`false`). Supports term queries and terms aggregation

- **`FieldMapping`**: Defines how a specific field is indexed:
  - `name` (str): field name, dot-notation for nested fields (e.g., `metadata.cache_state`)
  - `field_type` (FieldType): the field's type
  - `analyzer` (str): name of the analyzer to use for TEXT fields (default: `"standard"`)
  - `search_analyzer` (str): analyzer override for query-time analysis (default: same as `analyzer`)
  - `index` (bool): whether to include this field in the inverted index (default: True)
  - `store` (bool): whether to store the original value for retrieval (default: False for TEXT, True for others)
  - `doc_values` (bool): whether to build columnar doc values for sorting and aggregations (default: True for non-TEXT fields)
  - `norms` (bool): whether to store field-length norms for relevance scoring (default: True for TEXT)
  - `positions` (bool): whether to index term positions for phrase queries (default: True for TEXT)
  - `copy_to` (list): fields to copy this field's value to (for multi-field search)

- **`IndexMapping`**: The schema for an index:
  - `fields` (dict[str, FieldMapping]): field name to mapping
  - `dynamic` (bool): whether to auto-detect and index unmapped fields (default: True)
  - `dynamic_templates` (list[DynamicTemplate]): rules for auto-mapping unmapped fields based on name patterns or detected types
  - `_source` (SourceConfig): whether to store the complete original document (default: enabled). Disabling saves storage but prevents document retrieval
  - `_all` (AllFieldConfig): whether to create a catch-all field that concatenates all text fields for unqualified queries

- **`Document`**: A searchable unit:
  - `doc_id` (str): unique document identifier within the index
  - `source` (dict): the original document body
  - `fields` (dict[str, Any]): extracted and typed field values
  - `version` (int): document version for optimistic concurrency control
  - `timestamp` (float): ingestion timestamp for recency-based scoring and time-based queries

- **`DynamicTemplate`**: Auto-mapping rule:
  - `match` (str): glob pattern for field names (e.g., `"*_text"`)
  - `match_mapping_type` (str): detected JSON type to match (e.g., `"string"`, `"long"`)
  - `mapping` (FieldMapping): the mapping to apply when both conditions match

---

### 2. Analyzer Pipeline

The analyzer pipeline transforms raw text into a stream of indexed tokens. It is the bridge between human-readable content and machine-searchable terms. Every full-text field passes through an analyzer at index time, and every full-text query passes through an analyzer at search time. Analyzer consistency between index and search is critical -- a term indexed by one analyzer must be found by the same (or compatible) analyzer at query time.

- **`CharFilter`** (abstract base): Transforms the raw character stream before tokenization:
  - **`HTMLStripCharFilter`**: strips HTML/XML tags and decodes HTML entities (`&amp;` -> `&`, `&#x27;` -> `'`). Preserves text content between tags
  - **`PatternReplaceCharFilter`**: applies a regex substitution to the character stream. Configured with `pattern` (regex) and `replacement` (substitution string). Used for normalizing special characters, stripping accents, or domain-specific preprocessing
  - **`MappingCharFilter`**: applies a static character mapping table. Each mapping entry replaces a character sequence with another. Used for ligature expansion (`fi` -> `fi`), Unicode normalization, or domain-specific character equivalences

- **`Tokenizer`** (abstract base): Splits the character stream into tokens:
  - **`StandardTokenizer`**: Unicode Text Segmentation (UAX #29) based tokenizer. Splits on whitespace and punctuation boundaries while keeping email addresses, URLs, and hyphenated words intact. Produces tokens with `start_offset`, `end_offset`, and `position` attributes
  - **`WhitespaceTokenizer`**: splits strictly on Unicode whitespace characters. No special handling for punctuation or compound words
  - **`KeywordTokenizer`**: emits the entire input as a single token. Used for KEYWORD fields where the value should not be tokenized
  - **`NGramTokenizer`**: produces character n-grams of configurable min/max length. Used for substring matching and autocomplete. Parameters: `min_gram` (int, default 1), `max_gram` (int, default 2)
  - **`EdgeNGramTokenizer`**: like NGramTokenizer but only from the beginning of tokens. Produces prefixes: "fizzbuzz" with min=1, max=4 yields ["f", "fi", "fiz", "fizz"]. Used for prefix-based autocomplete
  - **`PatternTokenizer`**: splits on a configurable regex pattern. Group captures become tokens. Default pattern: `\W+` (split on non-word characters)

- **`TokenFilter`** (abstract base): Transforms the token stream after tokenization:
  - **`LowercaseFilter`**: converts all tokens to lowercase using Unicode case folding (not just ASCII). Ensures case-insensitive search
  - **`StopWordsFilter`**: removes common words that add noise to the index. Configurable stop word lists per language. Default English list: 33 common function words ("the", "a", "an", "and", "or", "not", "is", "are", "was", "were", "in", "on", "at", "to", "for", "of", "with", "by", "from", "as", "this", "that", "it", "be", "have", "has", "had", "do", "does", "did", "will", "would", "could"). Custom stop word lists supported for domain-specific corpora
  - **`PorterStemFilter`**: applies the Porter stemming algorithm to reduce words to their morphological root. "running" -> "run", "evaluation" -> "evalu", "fizzbuzzing" -> "fizzbuzz". Implements the five-step suffix-stripping algorithm with the standard English suffix rules. Stemming enables matching across inflectional forms -- a query for "evaluations" matches documents containing "evaluation", "evaluated", "evaluating"
  - **`SynonymFilter`**: expands or replaces tokens using a synonym map. Two modes:
    - **Expand mode**: "FizzBuzz" -> ["FizzBuzz", "FB", "fizz_buzz"] (all forms indexed, any form matches)
    - **Replace mode**: "FB" -> "FizzBuzz" (normalized to canonical form)
    - Synonym maps loaded from `.fizzsyn` files (one rule per line: `FB, fizz_buzz, fizzbuzz => FizzBuzz`)
    - Multi-word synonyms supported: "service mesh" -> "network proxy"
  - **`ASCIIFoldingFilter`**: converts Unicode characters to their ASCII equivalents. "resume" with accent -> "resume", "uber" with umlaut -> "uber". Enables ASCII-only queries to match accented content
  - **`TrimFilter`**: removes leading and trailing whitespace from tokens
  - **`LengthFilter`**: removes tokens shorter than `min_length` or longer than `max_length`. Default: min=1, max=255
  - **`UniqueFilter`**: removes duplicate tokens at the same position. Applied after synonym expansion to prevent double-counting in relevance scoring
  - **`ShingleFilter`**: produces token n-grams (shingles) for phrase-like matching without positional index overhead. Parameters: `min_shingle_size` (int, default 2), `max_shingle_size` (int, default 2), `output_unigrams` (bool, default True). "enterprise fizz buzz" with size=2 yields: ["enterprise", "enterprise fizz", "fizz", "fizz buzz", "buzz"]
  - **`KlingonStemFilter`**: applies morphological reduction rules for the Klingon language locale. Strips Klingon verb suffixes (-pu', -ta', -taH, -lI', -choH, -qa', -moH) and noun suffixes (-mey, -Du', -pu', -wI', -lIj, -vam, -vetlh) to produce root forms. Essential for searching FizzBuzz evaluation results localized to the Klingon locale (`tlhIngan Hol`), where "FizzBuzz" renders as warrior-appropriate terminology
  - **`SindarinStemFilter`**: handles Sindarin (Grey-Elvish) morphological patterns. Manages Sindarin's lenition-based mutations (soft mutation, nasal mutation, mixed mutation) and plural forms (-in, -ith, -ath, -rim). Necessary for the Sindarin locale where FizzBuzz outputs follow Tolkien's documented grammatical rules
  - **`QuenyaStemFilter`**: reduces Quenya (High-Elvish) inflected forms. Strips case declension suffixes (-nna, -llo, -sse, -nen) and number markers (-r, -i, -li for partitive plural). The Quenya locale's FizzBuzz outputs use proper noun declension, and search must match across cases

- **`Analyzer`**: A composed pipeline of char filters, a tokenizer, and token filters:
  - `char_filters` (list[CharFilter]): applied in order to the raw text
  - `tokenizer` (Tokenizer): splits filtered text into tokens
  - `token_filters` (list[TokenFilter]): applied in order to the token stream
  - `analyze(text: str) -> list[Token]`: the full pipeline execution
  - Token output includes: `text` (str), `position` (int), `start_offset` (int), `end_offset` (int), `position_increment` (int, typically 1; 0 for synonyms at the same position)

- **Built-in Analyzers** (pre-configured pipelines):
  - **`standard`**: StandardTokenizer -> LowercaseFilter -> StopWordsFilter (English)
  - **`simple`**: WhitespaceTokenizer -> LowercaseFilter
  - **`whitespace`**: WhitespaceTokenizer (no filtering)
  - **`keyword`**: KeywordTokenizer (no analysis, exact match)
  - **`english`**: StandardTokenizer -> LowercaseFilter -> StopWordsFilter (English) -> PorterStemFilter
  - **`klingon`**: StandardTokenizer -> LowercaseFilter -> StopWordsFilter (Klingon) -> KlingonStemFilter
  - **`sindarin`**: StandardTokenizer -> LowercaseFilter -> StopWordsFilter (Sindarin) -> SindarinStemFilter
  - **`quenya`**: StandardTokenizer -> LowercaseFilter -> StopWordsFilter (Quenya) -> QuenyaStemFilter
  - **`autocomplete`**: EdgeNGramTokenizer(min=2, max=10) -> LowercaseFilter
  - **`fizzbuzz_eval`**: StandardTokenizer -> LowercaseFilter -> SynonymFilter(fizzbuzz_synonyms) -> PorterStemFilter. Domain-specific analyzer for FizzBuzz evaluation results, with synonyms for evaluation terminology

---

### 3. Inverted Index & Posting Lists

The inverted index is the core data structure. It maps each unique term in the corpus to a posting list: the ordered set of documents containing that term, along with positional and frequency data needed for relevance scoring and phrase queries.

- **`Posting`**: A single occurrence record:
  - `doc_id` (int): internal document ID (dense sequential integer, mapped to external doc_id via `DocIdMap`)
  - `term_frequency` (int): number of times this term appears in this document's field
  - `positions` (list[int]): ordered list of term positions within the field (for phrase queries)
  - `offsets` (list[tuple[int, int]]): character offset pairs for each occurrence (for highlighting)
  - `payload` (bytes | None): optional per-position payload (for custom scoring)

- **`PostingList`**: The complete set of postings for a term:
  - `term` (str): the indexed term
  - `document_frequency` (int): number of documents containing this term (used in IDF calculation)
  - `total_term_frequency` (int): total number of occurrences across all documents (used in collection statistics)
  - `postings` (list[Posting]): document-ordered posting entries
  - `skip_list` (SkipList): multi-level skip list for efficient posting list intersection. Skip interval configurable (default: sqrt(n)). Enables O(sqrt(n)) advance operations instead of O(n) linear scan
  - `advance(target_doc_id: int) -> Posting | None`: advance to the first posting >= target_doc_id using skip list
  - `next() -> Posting | None`: advance to the next posting
  - `score_posting(posting: Posting, searcher: IndexSearcher) -> float`: compute BM25 score for this posting

- **`SkipList`**: Multi-level skip pointers for posting list traversal:
  - `levels` (list[list[SkipEntry]]): each level contains skip entries at exponentially increasing intervals
  - `skip_interval` (int): base interval between level-0 skip entries
  - `max_levels` (int): maximum skip list depth (default: 3)
  - Each `SkipEntry` contains: `doc_id` (int), `offset` (int) pointing into the posting list, `child_offset` (int) pointing to the entry in the next lower level

- **`TermDictionary`**: Maps terms to their posting lists:
  - Implemented as a sorted array of terms with binary search for term lookup
  - `FST` (Finite State Transducer): optional trie-like structure for prefix enumeration and fuzzy matching. Maps term prefixes to posting list offsets. Supports ordered iteration over terms matching a prefix or edit distance automaton
  - `get_postings(term: str) -> PostingList | None`: exact term lookup
  - `prefix_terms(prefix: str) -> Iterator[str]`: enumerate all terms with a given prefix
  - `fuzzy_terms(term: str, max_edits: int) -> Iterator[tuple[str, int]]`: enumerate terms within edit distance, yielding (term, edit_distance) pairs

- **`InvertedIndex`**: The per-field inverted index:
  - `field_name` (str): the field this index covers
  - `term_dictionary` (TermDictionary): term -> posting list mapping
  - `doc_count` (int): total number of documents in this index
  - `sum_doc_lengths` (int): sum of all document field lengths (for average length calculation in BM25)
  - `field_norms` (dict[int, int]): doc_id -> field length for length normalization
  - `add_document(doc_id: int, tokens: list[Token])`: index a document's analyzed tokens
  - `get_postings(term: str) -> PostingList | None`: retrieve postings for a term
  - `doc_freq(term: str) -> int`: number of documents containing the term
  - `total_docs() -> int`: total document count in the index

- **`DocValues`**: Columnar storage for sorting and aggregations:
  - Stores field values in a column-oriented format indexed by internal doc_id
  - Types: `SortedDocValues` (keyword/string), `NumericDocValues` (numeric), `SortedNumericDocValues` (multi-valued numeric), `SortedSetDocValues` (multi-valued keyword)
  - Enables sorting search results by field value without loading stored fields
  - Enables aggregation computation without loading documents

- **`StoredFields`**: Per-document field value storage:
  - Stores the original (pre-analysis) field values for document retrieval
  - Compressed per-block using LZ4-style run-length encoding
  - `get_document(doc_id: int) -> dict`: retrieve all stored fields for a document
  - `get_field(doc_id: int, field: str) -> Any`: retrieve a specific stored field

- **`DocIdMap`**: External-to-internal document ID mapping:
  - Maps external string doc_ids to dense sequential integers for compact posting list representation
  - Reverse mapping for document retrieval
  - Tracks deleted documents via a `LiveDocs` bitset (deleted documents are marked, not removed, until segment merge)

---

### 4. BM25 Relevance Scoring

BM25 (Best Matching 25) is the ranking function that determines document relevance. It is the standard scoring model used by virtually every production search engine. BM25 improves on raw TF-IDF by introducing term frequency saturation (diminishing returns for repeated terms) and document length normalization (shorter documents that match are ranked higher than longer documents with the same term frequency).

- **`BM25Scorer`**: Implements the Okapi BM25 scoring function:
  - Formula: `score(q, d) = sum_over_terms( IDF(t) * (tf(t,d) * (k1 + 1)) / (tf(t,d) + k1 * (1 - b + b * (dl / avgdl))) )`
  - Parameters:
    - `k1` (float, default 1.2): term frequency saturation. Higher values increase the impact of term frequency. At k1=0, term frequency is ignored entirely (binary model). At k1=inf, no saturation (pure TF)
    - `b` (float, default 0.75): document length normalization. At b=0, no length normalization. At b=1, full normalization against average document length. Default 0.75 provides moderate normalization
  - Components:
    - `idf(doc_freq: int, total_docs: int) -> float`: inverse document frequency. `log(1 + (total_docs - doc_freq + 0.5) / (doc_freq + 0.5))`. Rare terms get higher IDF scores. Terms appearing in every document get IDF approaching 0
    - `tf_norm(term_freq: int, doc_length: int, avg_doc_length: float) -> float`: normalized term frequency with saturation. `(term_freq * (k1 + 1)) / (term_freq + k1 * (1 - b + b * (doc_length / avg_doc_length)))`
    - `score_document(query_terms: list[str], doc_id: int, searcher: IndexSearcher) -> float`: compute the total BM25 score for a document against a query
  - **Field-level scoring**: when searching across multiple fields, each field produces its own BM25 score with independent statistics (doc count, average length, norms). Field scores are combined using configurable strategies:
    - `MAX`: take the maximum score across fields (default)
    - `SUM`: sum scores across fields
    - `AVG`: average scores across fields
    - Field boosting: per-field weight multipliers (e.g., `title^3.0` boosts title matches 3x)

- **`BM25FScorer`**: BM25F variant for multi-field scoring:
  - Instead of scoring each field independently and combining, BM25F combines term frequencies across fields before scoring
  - Per-field boost weights are applied to term frequencies: `tf_combined = sum(boost_i * tf_i)` across all fields
  - Per-field length normalization: `len_combined = sum(boost_i * len_i / avg_len_i)` across all fields
  - Produces more accurate relevance for queries that match across multiple fields

- **`ScoringContext`**: Per-query scoring state:
  - Caches IDF values for query terms (computed once per query, reused across documents)
  - Holds collection statistics (total docs, average field lengths)
  - Holds per-document field norms
  - `explain(doc_id: int) -> ScoreExplanation`: produces a detailed breakdown of how a document's score was computed, showing each term's IDF, TF, length normalization, and contribution to the total score

---

### 5. Query Model & Query DSL

The query model defines the operations that can be performed against the inverted index. Queries are composable -- complex queries are built from simple queries using boolean operators. The query DSL provides a structured JSON-like syntax for constructing queries programmatically.

- **`Query`** (abstract base): All queries implement:
  - `create_scorer(searcher: IndexSearcher) -> Scorer`: produce a scorer that iterates matching documents
  - `rewrite(searcher: IndexSearcher) -> Query`: optimize/rewrite the query (e.g., expand wildcard terms)
  - `explain(doc_id: int, searcher: IndexSearcher) -> ScoreExplanation`: explain scoring for a specific document

- **`TermQuery`**: Matches documents containing an exact term in a specific field:
  - `field` (str): the field to search
  - `term` (str): the term to match (already analyzed)
  - Looks up the term's posting list in the inverted index and iterates postings
  - Score: BM25(term_freq, doc_length, collection_stats)

- **`BooleanQuery`**: Combines sub-queries with boolean logic:
  - `must` (list[Query]): all must match (AND). Scores are summed
  - `should` (list[Query]): at least `minimum_should_match` must match (OR). Scores are summed
  - `must_not` (list[Query]): none may match (NOT). No score contribution
  - `filter` (list[Query]): all must match but do not contribute to scoring (used for structured filtering)
  - `minimum_should_match` (int, default 1 if no `must` clauses, 0 if `must` clauses exist)
  - Execution: the engine intersects `must` posting lists using sorted merge with skip lists, subtracts `must_not` documents, then checks `should` constraints. `filter` clauses are evaluated first as they can eliminate documents before scoring

- **`PhraseQuery`**: Matches documents where terms appear in exact order at consecutive positions:
  - `field` (str): the field to search
  - `terms` (list[str]): ordered terms to match
  - `slop` (int, default 0): maximum number of position gaps allowed between terms. Slop=0 requires exact adjacency. Slop=1 allows one intervening term. Slop=N allows N positions of gap (in any direction for sloppy phrases)
  - Execution: finds documents containing all terms (posting list intersection), then checks positional data for each candidate document. For each document, the algorithm verifies that term positions can be aligned with gaps totaling <= slop
  - Score: BM25 of the phrase (using minimum term frequency among constituent terms), boosted by proximity (tighter matches score higher when slop > 0)

- **`MatchQuery`**: User-facing query that analyzes input text and builds the appropriate query:
  - `field` (str): the field to search
  - `query_text` (str): the raw query text (will be analyzed)
  - `operator` (str, default "OR"): "OR" creates a BooleanQuery with should clauses, "AND" creates must clauses
  - `minimum_should_match` (int | str): minimum number of terms that must match. Supports integer (2) or percentage ("75%")
  - `fuzziness` (int | str): edit distance for fuzzy matching. "AUTO" uses length-based fuzziness: 0-2 chars=0 edits, 3-5 chars=1 edit, 6+ chars=2 edits
  - `analyzer` (str | None): override the field's search analyzer
  - `zero_terms_query` (str, default "none"): what to do when the analyzer produces no terms. "none" matches nothing, "all" matches everything
  - Execution: analyzes query_text with the field's search analyzer, then builds a BooleanQuery from the resulting terms. If the analyzer produces a single term and the field has positional data, checks for phrase-like input and may produce a PhraseQuery

- **`MultiMatchQuery`**: Searches across multiple fields:
  - `fields` (list[str]): fields to search (supports boost syntax: `"title^3"`)
  - `query_text` (str): the query text
  - `type` (str): scoring strategy:
    - `"best_fields"` (default): score is the max score across fields, with `tie_breaker` (float, 0.0-1.0) controlling how much non-max fields contribute
    - `"most_fields"`: score is the sum of scores across all fields
    - `"cross_fields"`: term-centric scoring -- looks for each term in any field, as if all fields were a single field
    - `"phrase"`: runs a PhraseQuery on each field
    - `"phrase_prefix"`: runs a phrase query with the last term as a prefix

- **`FuzzyQuery`**: Matches terms within edit distance of the query term:
  - `field` (str): the field to search
  - `term` (str): the approximate term
  - `max_edits` (int, default 2): maximum Levenshtein edit distance (1 or 2)
  - `prefix_length` (int, default 0): number of leading characters that must match exactly (reduces candidate set)
  - `max_expansions` (int, default 50): maximum number of matching terms to expand to
  - `transpositions` (bool, default True): whether to count transpositions as a single edit (Damerau-Levenshtein)
  - Execution: builds a Levenshtein automaton from the query term and intersects it with the term dictionary's FST to find all terms within edit distance. Each matching term is expanded into a BooleanQuery with should clauses

- **`WildcardQuery`**: Matches terms using wildcard patterns:
  - `field` (str): the field to search
  - `pattern` (str): wildcard pattern where `?` matches any single character and `*` matches any sequence
  - Execution: converts the wildcard pattern to a finite automaton and intersects with the term dictionary. Rewritten to a BooleanQuery of matching terms

- **`PrefixQuery`**: Matches all terms starting with a prefix:
  - `field` (str): the field to search
  - `prefix` (str): the term prefix
  - `max_expansions` (int, default 128): maximum terms to expand
  - Execution: enumerates matching terms from the term dictionary's sorted structure and rewrites to a BooleanQuery

- **`RangeQuery`**: Matches documents with field values in a range:
  - `field` (str): the field to search
  - `gte` / `gt` (Any | None): lower bound (inclusive / exclusive)
  - `lte` / `lt` (Any | None): upper bound (inclusive / exclusive)
  - Works on NUMERIC, DATE, and KEYWORD fields. For KEYWORD fields, uses lexicographic ordering. For NUMERIC, uses the sorted numeric index. For DATE, parses bounds using the field's date format

- **`ExistsQuery`**: Matches documents where a field has a value:
  - `field` (str): the field to check
  - Useful for filtering documents that have (or lack, via must_not) a specific field

- **`MatchAllQuery`**: Matches every document with score 1.0. Used as the base for filtered queries

- **`MatchNoneQuery`**: Matches no documents. Used as a sentinel in query rewriting

- **`BoostQuery`**: Wraps another query and multiplies its score by a constant factor:
  - `query` (Query): the inner query
  - `boost` (float): the score multiplier

- **`ConstantScoreQuery`**: Wraps a query and assigns a constant score to all matches:
  - `query` (Query): the inner query (typically a filter)
  - `score` (float, default 1.0): the score assigned to every match

- **`DisMaxQuery`**: Disjunction max -- score is the max score across sub-queries plus tie-breaker sum:
  - `queries` (list[Query]): the sub-queries
  - `tie_breaker` (float, default 0.0): weight for non-maximum scores
  - Score: `max(scores) + tie_breaker * sum(non_max_scores)`

- **`FunctionScoreQuery`**: Modifies scores using pluggable scoring functions:
  - `query` (Query): the base query
  - `functions` (list[ScoreFunction]): scoring functions applied to matching documents
  - Score functions include:
    - `DecayFunction`: exponential, linear, or Gaussian decay based on distance from an origin point. Used for recency boosting (decay by age), geo proximity boosting, or numeric proximity
    - `FieldValueFactor`: uses a numeric field value as a score factor. Parameters: `field`, `factor` (multiplier), `modifier` (none/log/log1p/log2p/ln/ln1p/ln2p/sqrt/square/reciprocal), `missing` (default value)
    - `ScriptScoreFunction`: compute score using a custom scoring expression (simple arithmetic DSL over field values and `_score`)

- **`QueryDSL`**: Parses structured query definitions into Query objects:
  - Accepts nested dict structures matching the query types above
  - Example:
    ```python
    {
        "bool": {
            "must": [
                {"match": {"result": "FizzBuzz"}},
                {"range": {"number": {"gte": 1, "lte": 100}}}
            ],
            "should": [
                {"term": {"cache_state": "MODIFIED"}}
            ],
            "must_not": [
                {"term": {"status": "error"}}
            ]
        }
    }
    ```
  - Validates query structure, resolves field mappings, and constructs the Query tree
  - Supports query string syntax for simpler queries: `"result:FizzBuzz AND number:[1 TO 100] NOT status:error"`

---

### 6. Index Segments & Merge Policy

FizzSearch uses a segment-based index architecture inspired by Lucene. New documents are indexed into an in-memory buffer. When the buffer is flushed (by size threshold, document count, or explicit request), it becomes an immutable on-disk segment. Searches span all segments. Over time, many small segments accumulate and are merged into larger segments by a background merge policy. This architecture enables near-real-time indexing while maintaining efficient search.

- **`IndexSegment`**: An immutable unit of the index:
  - `segment_id` (str): unique segment identifier (UUID)
  - `doc_count` (int): number of documents in this segment (including deleted)
  - `live_doc_count` (int): number of non-deleted documents
  - `live_docs` (Bitset): bitset marking which documents are live (not deleted)
  - `inverted_indices` (dict[str, InvertedIndex]): per-field inverted indices
  - `stored_fields` (StoredFields): per-document stored field values
  - `doc_values` (dict[str, DocValues]): per-field columnar values
  - `field_norms` (dict[str, dict[int, int]]): per-field document length norms
  - `min_doc_id` (int), `max_doc_id` (int): doc_id range in this segment
  - `size_bytes` (int): total segment size for merge policy decisions
  - `generation` (int): how many merges have contributed to this segment (0 for flushed segments)

- **`SegmentReader`**: Reads from a single segment:
  - Provides access to the segment's inverted indices, stored fields, and doc values
  - Filters deleted documents via `live_docs` bitset
  - Thread-safe: multiple searchers can read the same segment concurrently

- **`IndexWriter`**: Manages index mutations:
  - `write_buffer` (WriteBuffer): in-memory buffer for new documents
  - `buffer_size_limit` (int, default 64MB): flush threshold
  - `buffer_doc_limit` (int, default 10000): flush threshold by document count
  - `add_document(doc: Document)`: analyze and buffer a document
  - `update_document(doc_id: str, doc: Document)`: delete old version, add new version (delete + add is atomic per segment)
  - `delete_document(doc_id: str)`: mark document as deleted in its segment's live_docs bitset
  - `flush() -> IndexSegment`: flush the write buffer to a new immutable segment
  - `commit()`: make all flushed segments visible to searchers (the "commit point")
  - `merge(segments: list[IndexSegment]) -> IndexSegment`: merge multiple segments into one, physically removing deleted documents and combining posting lists
  - `force_merge(max_segments: int)`: merge all segments down to at most max_segments (expensive, used for optimization)

- **`MergePolicy`** (abstract base): Decides which segments to merge and when:
  - **`TieredMergePolicy`**: the default merge policy, inspired by Lucene's TieredMergePolicy:
    - `max_merge_at_once` (int, default 10): maximum segments to merge in a single merge operation
    - `segments_per_tier` (int, default 10): target number of segments per size tier
    - `max_merged_segment_size` (int, default 5GB): segments larger than this are never merged (unless force_merge)
    - `floor_segment_size` (int, default 2MB): segments smaller than this are treated as this size for merge prioritization
    - `deletes_pct_allowed` (float, default 33.0): segments with more than this percentage of deleted documents are prioritized for merge
    - Algorithm: groups segments into size tiers (powers of `segments_per_tier`). Within each tier, selects the merge that reduces segment count most efficiently. Prioritizes segments with high delete ratios
  - **`LogMergePolicy`**: merge when there are more than `merge_factor` segments of similar size:
    - `merge_factor` (int, default 10): number of similar-size segments that triggers a merge
    - Simpler than tiered but less efficient for heterogeneous segment sizes

- **`MergeScheduler`**: Executes merge operations:
  - **`SerialMergeScheduler`**: merges run synchronously in the indexing thread (simple, low-throughput)
  - **`ConcurrentMergeScheduler`**: merges run in background threads (default). Parameters:
    - `max_concurrent_merges` (int, default 3): maximum simultaneous merge operations
    - `max_merge_thread_throughput` (int, default 20MB/s): I/O throttle per merge thread to avoid starving searches

- **`CommitPoint`**: A snapshot of visible segments:
  - `segments` (list[IndexSegment]): the segments visible at this commit point
  - `generation` (int): monotonically increasing commit generation
  - `timestamp` (float): when the commit occurred
  - Old commit points are retained for a configurable period to support concurrent readers

---

### 7. Near-Real-Time Search

Production search engines do not require a full commit to make documents searchable. FizzSearch implements near-real-time (NRT) search by allowing searchers to read from the current write buffer's in-memory segment in addition to committed segments.

- **`SearcherManager`**: Manages IndexSearcher lifecycle:
  - `refresh_interval` (float, default 1.0): seconds between automatic refreshes
  - `acquire() -> IndexSearcher`: acquire a searcher that sees the latest refreshed state. Reference-counted: the searcher's segments are protected from deletion until released
  - `release(searcher: IndexSearcher)`: release a searcher
  - `maybe_refresh() -> bool`: check if new segments are available and create a fresh searcher if so. Called automatically at `refresh_interval` and explicitly after `IndexWriter.flush()`
  - The refresh operation is lightweight: it creates a new IndexSearcher pointing to the current set of segments (committed + flushed-but-uncommitted). No data is copied. The old searcher remains valid for in-flight queries

- **`IndexSearcher`**: The search execution engine:
  - `segments` (list[SegmentReader]): the segments visible to this searcher
  - `search(query: Query, limit: int, sort: Sort | None, after: ScoreDoc | None) -> SearchResults`: execute a query and return ranked results
  - `count(query: Query) -> int`: count matching documents without scoring
  - `explain(query: Query, doc_id: int) -> ScoreExplanation`: explain a document's relevance score
  - `aggregate(query: Query, aggregations: dict[str, Aggregation]) -> AggregationResults`: compute aggregations over matching documents
  - Multi-segment search: the searcher queries each segment independently and merges results using a priority queue (heap) sorted by score (or custom sort). The heap is bounded to `limit` entries, so memory usage is proportional to the number of requested results, not the total match count

- **`SearchResults`**: Query results container:
  - `total_hits` (int): total number of matching documents (may be exact or lower-bound estimate depending on `track_total_hits` setting)
  - `hits` (list[SearchHit]): the top-N result documents
  - `max_score` (float): the highest relevance score among all matches
  - `took_ms` (float): query execution time in milliseconds
  - `aggregations` (dict[str, AggregationResult] | None): aggregation results if requested

- **`SearchHit`**: A single result document:
  - `doc_id` (str): external document ID
  - `score` (float): relevance score
  - `source` (dict | None): the document's stored fields (if `_source` is enabled)
  - `fields` (dict[str, Any]): specific requested fields (via `fields` parameter)
  - `highlight` (dict[str, list[str]] | None): highlighted field fragments (if highlighting requested)
  - `sort_values` (list[Any] | None): the sort key values (if custom sort applied)
  - `explanation` (ScoreExplanation | None): score explanation (if `explain=True`)

---

### 8. Hit Highlighting & Snippet Extraction

When search results are presented to users, showing the matching text fragments with highlighted query terms is essential for result assessment. FizzSearch implements a highlighting system that extracts relevant snippets from matched documents and wraps matching terms in configurable tags.

- **`Highlighter`**: Extracts and highlights matching text fragments:
  - `pre_tag` (str, default `"<em>"`): tag inserted before each highlighted term
  - `post_tag` (str, default `"</em>"`): tag inserted after each highlighted term
  - `fragment_size` (int, default 150): maximum characters per fragment
  - `number_of_fragments` (int, default 5): maximum fragments per field
  - `order` (str, default "score"): fragment ordering -- "score" (best fragments first) or "none" (document order)
  - `no_match_size` (int, default 0): if no matches in a field, return first N characters as a fallback fragment

- **`HighlightStrategy`** (abstract base):
  - **`PlainHighlighter`**: re-analyzes the stored field text, finds term positions that match query terms, and extracts surrounding context as fragments. Fragments are scored by the density of matching terms. Simple and accurate but requires stored field values and re-analysis
  - **`PostingsHighlighter`**: uses positional and offset data from the inverted index to locate matches without re-analysis. Faster than plain highlighting but requires positions and offsets to be indexed. Fragments are sentence-aware: boundaries are aligned to sentence boundaries when possible
  - **`FastVectorHighlighter`**: uses term vectors (per-document positional data stored at index time) for fastest highlighting. Requires `term_vector: with_positions_offsets` on the field mapping. Supports multi-term highlighting (phrases, synonyms) with position-aware matching

- **`Fragment`**: A highlighted text excerpt:
  - `text` (str): the fragment text with highlight tags inserted
  - `score` (float): relevance score for this fragment (density of matching terms)
  - `start_offset` (int): character offset in the original field where this fragment begins
  - `end_offset` (int): character offset where this fragment ends

---

### 9. Aggregation Framework

Aggregations compute statistics and groupings over the set of documents matching a query, without returning individual documents. They are the analytical counterpart to search: where search finds specific documents, aggregations summarize the corpus. Aggregations are composable -- sub-aggregations can be nested inside bucket aggregations to any depth.

- **`Aggregation`** (abstract base): All aggregations implement:
  - `collect(doc_id: int, doc_values: DocValues)`: process a matching document
  - `result() -> AggregationResult`: produce the final aggregation result
  - `sub_aggregations` (dict[str, Aggregation]): nested aggregations computed within each bucket

- **Bucket Aggregations** (partition documents into groups):
  - **`TermsAggregation`**: groups documents by unique values in a KEYWORD or numeric field:
    - `field` (str): the field to aggregate on
    - `size` (int, default 10): number of top buckets to return
    - `min_doc_count` (int, default 1): minimum documents per bucket
    - `order` (dict): sort order for buckets (`{"_count": "desc"}`, `{"_key": "asc"}`, or by sub-aggregation)
    - `include` / `exclude` (str | list): filter bucket keys by regex or explicit list
    - Each bucket: `{key, doc_count, sub_aggregation_results}`
    - Implementation: iterates doc_values for the field, counts occurrences per unique value, and returns the top-N values by count (using a min-heap bounded to `size`)

  - **`HistogramAggregation`**: groups numeric values into fixed-width buckets:
    - `field` (str): the numeric field
    - `interval` (float): bucket width
    - `offset` (float, default 0): shift bucket boundaries
    - `min_doc_count` (int, default 0): minimum documents per bucket (0 includes empty buckets in range)
    - `extended_bounds` (dict): force inclusion of buckets outside the data range (`{"min": 0, "max": 100}`)
    - Each bucket: `{key (lower bound), doc_count, sub_aggregation_results}`

  - **`DateHistogramAggregation`**: groups date values into calendar-aware buckets:
    - `field` (str): the date field
    - `calendar_interval` (str): calendar-aware interval ("minute", "hour", "day", "week", "month", "quarter", "year"). Respects variable-length months, leap years, DST transitions
    - `fixed_interval` (str): fixed duration interval ("30s", "1m", "1h", "1d"). Does not respect calendar boundaries
    - `time_zone` (str, default "UTC"): timezone for bucket boundary computation
    - `format` (str): date format for bucket keys
    - Each bucket: `{key (bucket start timestamp), key_as_string (formatted), doc_count, sub_aggregation_results}`

  - **`RangeAggregation`**: groups numeric values into user-defined ranges:
    - `field` (str): the numeric field
    - `ranges` (list[dict]): list of `{"from": N, "to": M}` range definitions (from inclusive, to exclusive)
    - `keyed` (bool): if True, buckets are returned as a dict keyed by "from-to" strings

  - **`FilterAggregation`**: a single-bucket aggregation that restricts documents to those matching a query:
    - `filter` (Query): the filter query
    - Result: `{doc_count, sub_aggregation_results}`

  - **`FiltersAggregation`**: multi-bucket variant -- each named filter produces a bucket:
    - `filters` (dict[str, Query]): named filters
    - `other_bucket` (bool): whether to include an "other" bucket for documents matching none of the filters

  - **`NestedAggregation`**: aggregates over nested documents (for nested field types):
    - `path` (str): the nested field path
    - Scopes sub-aggregations to the nested document level

  - **`GeoDistanceAggregation`**: groups documents by distance from a geographic origin:
    - `field` (str): the geo_point field
    - `origin` (dict): `{"lat": float, "lon": float}`
    - `ranges` (list[dict]): distance ranges in meters/kilometers
    - `unit` (str): distance unit ("m", "km", "mi")

- **Metric Aggregations** (compute statistics):
  - **`AvgAggregation`**: arithmetic mean of a numeric field
  - **`SumAggregation`**: sum of a numeric field
  - **`MinAggregation`**: minimum value of a numeric field
  - **`MaxAggregation`**: maximum value of a numeric field
  - **`StatsAggregation`**: combined min, max, sum, count, avg in a single pass
  - **`ExtendedStatsAggregation`**: stats plus variance, standard deviation, sum of squares, std deviation bounds
  - **`CardinalityAggregation`**: approximate distinct count using HyperLogLog++:
    - `field` (str): the field to count distinct values of
    - `precision_threshold` (int, default 3000): HyperLogLog precision (higher = more accurate, more memory)
    - Returns approximate cardinality with configurable accuracy/memory tradeoff
  - **`PercentilesAggregation`**: compute percentile values using TDigest:
    - `field` (str): the numeric field
    - `percents` (list[float], default [1, 5, 25, 50, 75, 95, 99]): percentile ranks to compute
    - `compression` (int, default 100): TDigest compression parameter (higher = more accurate)
  - **`TopHitsAggregation`**: returns the top matching documents within each bucket:
    - `size` (int, default 3): number of top hits per bucket
    - `sort` (list[dict]): sort order for top hits
    - `_source` (dict): source filtering for returned documents

- **Pipeline Aggregations** (operate on other aggregations' outputs):
  - **`BucketSortAggregation`**: sorts parent bucket aggregation by a metric sub-aggregation value
  - **`CumulativeSumAggregation`**: computes cumulative sum across buckets in a histogram
  - **`DerivativeAggregation`**: computes first/second derivative across histogram buckets
  - **`MovingAverageAggregation`**: computes moving average across histogram buckets with configurable window models (simple, linear, exponentially weighted)

---

### 10. Faceted Search

Faceted search enables categorical drill-down -- the search interface presents category counts alongside results, allowing users to progressively narrow their query by selecting facet values. FizzSearch implements faceted search as a combination of aggregations and post-filter queries.

- **`FacetSpec`**: Defines a facet:
  - `field` (str): the KEYWORD field to facet on
  - `size` (int, default 10): number of facet values to return
  - `order` (str, default "count"): "count" (most frequent first) or "value" (alphabetical)
  - `selected_values` (list[str]): currently selected facet values (for drill-down)

- **`FacetResult`**: Facet computation result:
  - `field` (str): the faceted field
  - `values` (list[FacetValue]): the facet values with counts
  - `total_other` (int): count of documents in values not shown (beyond `size`)
  - `total_missing` (int): count of documents with no value for this field

- **`FacetValue`**: A single facet entry:
  - `value` (str): the facet value
  - `count` (int): number of matching documents with this value
  - `selected` (bool): whether this value is currently selected

- **`FacetedSearch`**: Orchestrates multi-facet search:
  - `query` (Query): the base query
  - `facets` (list[FacetSpec]): facet definitions
  - `post_filter` (Query | None): filter applied after aggregation computation (so facet counts reflect the unfiltered query, enabling accurate counts for non-selected facet values)
  - Execution: runs the base query with terms aggregations for each facet field. Aggregation counts are computed against the unfiltered results. The post_filter (built from selected facet values) is then applied to produce the final result set. This ensures that selecting a facet value narrows results but does not collapse the facet counts, allowing users to see how many documents each facet value would produce

---

### 11. Scroll / Deep Pagination

Standard search pagination (offset + limit) becomes expensive for deep pages because the engine must score and sort all preceding documents to determine page boundaries. FizzSearch implements scroll-based deep pagination that maintains a search context across requests, enabling efficient traversal of large result sets.

- **`ScrollContext`**: A stateful search cursor:
  - `scroll_id` (str): opaque identifier for this scroll context
  - `query` (Query): the frozen query
  - `sort` (Sort): the frozen sort order
  - `last_sort_values` (list[Any]): the sort values of the last returned document (used as the "search after" cursor)
  - `last_doc_id` (int): tiebreaker for documents with identical sort values
  - `segment_readers` (list[SegmentReader]): pinned segment readers (preventing merge deletion of these segments)
  - `total_hits` (int): total matching documents at scroll creation time
  - `created_at` (float): creation timestamp
  - `ttl` (float): time-to-live in seconds (default: 60)
  - `is_expired() -> bool`: whether the scroll context has expired

- **`ScrollManager`**: Manages active scroll contexts:
  - `create_scroll(query: Query, sort: Sort, size: int, ttl: float) -> tuple[list[SearchHit], str]`: execute the initial search and return the first page plus a scroll_id
  - `scroll(scroll_id: str, size: int) -> tuple[list[SearchHit], str]`: fetch the next page using the scroll context. Returns new hits and a (possibly updated) scroll_id
  - `clear_scroll(scroll_id: str)`: explicitly release a scroll context and unpin its segment readers
  - `clear_expired()`: garbage-collect expired scroll contexts (run periodically)
  - Maximum active scrolls: configurable (default: 500). Creating a scroll beyond the limit returns an error

- **`SearchAfter`**: Stateless deep pagination alternative:
  - Instead of maintaining server-side state, the client provides the sort values of the last seen document
  - `search_after` (list[Any]): sort values to search after
  - Requires a deterministic sort order (add `_doc` as tiebreaker)
  - More scalable than scroll (no server-side state) but does not support consistent snapshots -- concurrent index changes may cause results to shift

---

### 12. Sort & Scoring Configuration

- **`Sort`**: Defines result ordering:
  - `fields` (list[SortField]): ordered list of sort criteria
  - Default sort: `[SortField("_score", order="desc"), SortField("_doc", order="asc")]` (relevance then doc ID tiebreaker)

- **`SortField`**: A single sort criterion:
  - `field` (str): field name, or `"_score"` for relevance, or `"_doc"` for insertion order
  - `order` (str): `"asc"` or `"desc"`
  - `missing` (str): handling for missing values -- `"_first"` or `"_last"`
  - `mode` (str): for multi-valued fields -- `"min"`, `"max"`, `"avg"`, `"sum"`, `"median"`
  - `nested` (dict | None): for sorting by nested field values -- specifies the nested path and optional filter

---

### 13. Index Management

- **`FizzSearchEngine`**: Top-level search engine managing multiple named indices:
  - `create_index(name: str, mapping: IndexMapping, settings: IndexSettings) -> Index`: create a new index
  - `delete_index(name: str)`: delete an index and all its data
  - `get_index(name: str) -> Index`: retrieve an index by name
  - `list_indices() -> list[IndexInfo]`: list all indices with metadata
  - `index_exists(name: str) -> bool`: check if an index exists
  - `reindex(source: str, dest: str, query: Query | None)`: copy documents from one index to another, optionally filtered
  - `aliases` (dict[str, str]): index aliases for transparent index switching (e.g., `"evaluations"` -> `"evaluations_v2"`)

- **`IndexSettings`**: Per-index configuration:
  - `number_of_shards` (int, default 1): number of primary shards (for future distribution)
  - `number_of_replicas` (int, default 0): number of replica shards
  - `refresh_interval` (float, default 1.0): NRT refresh interval in seconds
  - `max_result_window` (int, default 10000): maximum offset+limit for standard pagination
  - `merge_policy` (str, default "tiered"): merge policy name
  - `codec` (str, default "default"): compression codec for stored fields
  - `analyzers` (dict[str, AnalyzerConfig]): custom analyzer definitions for this index
  - `similarity` (str, default "BM25"): similarity model ("BM25" or "BM25F")

- **`Index`**: A named, searchable document collection:
  - `name` (str): the index name
  - `mapping` (IndexMapping): the index schema
  - `settings` (IndexSettings): the index configuration
  - `writer` (IndexWriter): the index writer
  - `searcher_manager` (SearcherManager): manages searcher instances
  - `index_document(doc: dict) -> str`: index a document (auto-generate doc_id if not provided)
  - `bulk_index(docs: list[dict]) -> BulkResult`: index multiple documents in a single operation
  - `get_document(doc_id: str) -> dict | None`: retrieve a document by ID
  - `delete_document(doc_id: str) -> bool`: delete a document by ID
  - `update_document(doc_id: str, doc: dict)`: replace a document
  - `search(query: dict | Query, **kwargs) -> SearchResults`: search the index
  - `aggregate(query: dict | Query, aggregations: dict) -> AggregationResults`: run aggregations
  - `refresh()`: explicitly refresh to make recent changes searchable
  - `flush()`: flush in-memory buffer to a segment
  - `commit()`: commit all changes
  - `force_merge(max_segments: int)`: optimize the index by merging segments
  - `stats() -> IndexStats`: return index statistics (doc count, size, segment count, etc.)

---

### 14. Platform Integration

FizzSearch integrates with the Enterprise FizzBuzz Platform's existing subsystems to provide searchability across all data producers.

- **`EvaluationIndexer`**: Indexes FizzBuzz evaluation results:
  - Subscribes to the event bus for `EvaluationCompleted` events
  - Creates documents with fields: `number` (NUMERIC), `result` (TEXT, analyzed with `fizzbuzz_eval` analyzer), `rules_fired` (KEYWORD, multi-valued), `cache_state` (KEYWORD), `middleware_chain` (KEYWORD, multi-valued), `strategy` (KEYWORD), `timestamp` (DATE), `execution_time_ms` (NUMERIC), `locale` (KEYWORD)
  - Enables queries like: "find all evaluations where the result contained 'FizzBuzz' and the number was between 1 and 1000, aggregated by cache state"

- **`AuditLogIndexer`**: Indexes audit trail entries:
  - Subscribes to compliance engine events
  - Fields: `action` (KEYWORD), `principal` (KEYWORD), `resource` (KEYWORD), `decision` (KEYWORD), `compliance_framework` (KEYWORD), `timestamp` (DATE), `details` (TEXT)

- **`EventJournalIndexer`**: Indexes event sourcing journal entries:
  - Reads from the event store
  - Fields: `event_type` (KEYWORD), `aggregate_id` (KEYWORD), `sequence` (NUMERIC), `payload` (TEXT), `timestamp` (DATE)

- **`MetricsIndexer`**: Indexes platform metrics as time-series documents:
  - Subscribes to the metrics subsystem
  - Fields: `metric_name` (KEYWORD), `value` (NUMERIC), `labels` (KEYWORD, multi-valued), `timestamp` (DATE)
  - Enables date_histogram aggregations for time-series visualization

- **`SearchMiddleware`**: Middleware pipeline component that logs search queries and results to the search index itself (meta-search: searching searches):
  - Fields: `query_text` (TEXT), `query_type` (KEYWORD), `index_name` (KEYWORD), `total_hits` (NUMERIC), `took_ms` (NUMERIC), `timestamp` (DATE)

---

### 15. CLI Flags

- `--fizzsearch`: Enable the FizzSearch full-text search engine
- `--fizzsearch-create-index <name>`: Create a new search index with default mapping
- `--fizzsearch-create-index-mapping <name> <mapping_json>`: Create an index with explicit field mappings
- `--fizzsearch-delete-index <name>`: Delete a search index
- `--fizzsearch-list-indices`: List all search indices with document counts and sizes
- `--fizzsearch-index-stats <name>`: Show detailed statistics for an index (segments, memory, doc counts)
- `--fizzsearch-index-doc <index> <json>`: Index a single document
- `--fizzsearch-bulk-index <index> <file>`: Bulk index documents from a JSONL file
- `--fizzsearch-search <index> <query>`: Execute a search query (query string syntax)
- `--fizzsearch-search-dsl <index> <dsl_json>`: Execute a search query using the full query DSL
- `--fizzsearch-aggregate <index> <query> <agg_json>`: Execute aggregations over matching documents
- `--fizzsearch-explain <index> <query> <doc_id>`: Explain a document's relevance score
- `--fizzsearch-analyze <analyzer> <text>`: Run text through an analyzer and show the resulting tokens
- `--fizzsearch-scroll <index> <query> --scroll-size <n> --scroll-ttl <seconds>`: Start a scroll search
- `--fizzsearch-facets <index> <query> --facet-fields <f1,f2,...>`: Execute a faceted search
- `--fizzsearch-highlight <on|off>`: Enable/disable hit highlighting in search results (default: on)
- `--fizzsearch-index-evaluations`: Enable automatic indexing of FizzBuzz evaluation results
- `--fizzsearch-index-audit`: Enable automatic indexing of audit trail entries
- `--fizzsearch-index-events`: Enable automatic indexing of event journal entries
- `--fizzsearch-index-metrics`: Enable automatic indexing of platform metrics
- `--fizzsearch-refresh-interval <seconds>`: Set the near-real-time refresh interval (default: 1.0)
- `--fizzsearch-merge-policy <tiered|log>`: Set the segment merge policy
- `--fizzsearch-bm25-k1 <float>`: Set BM25 k1 parameter (default: 1.2)
- `--fizzsearch-bm25-b <float>`: Set BM25 b parameter (default: 0.75)
- `--fizzsearch-similarity <BM25|BM25F>`: Set the similarity model
- `--fizzsearch-max-result-window <int>`: Maximum offset+limit for pagination (default: 10000)

---

## Why This Is Necessary

The Enterprise FizzBuzz Platform has 116 infrastructure modules that collectively generate, process, store, and transmit data across dozens of subsystems. The event sourcing journal grows with every evaluation. The audit trail grows with every authorization decision. The metrics pipeline grows with every observation interval. The CDC stream grows with every state mutation. None of this data is searchable.

The platform has a SQL query engine (FizzSQL) for relational queries against structured tables. It has a graph database for relationship traversal. It has a spatial database for geographic queries. It has a columnar storage engine for analytical workloads. It does not have a full-text search engine. An operator who wants to find "all evaluations where the result contained 'Fizz' and the cache was in MODIFIED state, grouped by locale and sorted by recency" has no tool for this query. This is not a SQL query -- the result field requires full-text analysis, stemming, and relevance scoring. It is not a graph query -- there are no relationships to traverse. It is not a spatial query -- there are no geographic dimensions. It is a search query, and the platform has no search engine to answer it.

Full-text search is a foundational capability that every data-intensive platform requires. Elasticsearch alone serves this function for millions of organizations. The Enterprise FizzBuzz Platform, which already implements a TCP/IP stack, a DNS server, a video codec, a ray tracer, a protein folder, an audio synthesizer, a theorem prover, a GPU shader compiler, a smart contract VM, a spreadsheet engine, an x86 bootloader, a garbage collector, a regex engine, a typesetting engine, a CPU pipeline simulator, and a container runtime stack with image registry and CRI integration, does not have a search engine. FizzSearch corrects this omission.

## Estimated Scale

~3,500 lines of search engine implementation:
- ~250 lines for document model and field mappings (FieldType, FieldMapping, IndexMapping, Document, DynamicTemplate)
- ~400 lines for analyzer pipeline (CharFilter variants, Tokenizer variants, TokenFilter variants including Klingon/Sindarin/Quenya stemmers, built-in analyzer definitions)
- ~450 lines for inverted index and posting lists (Posting, PostingList, SkipList, TermDictionary with FST, InvertedIndex, DocValues, StoredFields, DocIdMap)
- ~250 lines for BM25 relevance scoring (BM25Scorer, BM25FScorer, ScoringContext, ScoreExplanation)
- ~500 lines for query model and query DSL (TermQuery, BooleanQuery, PhraseQuery, MatchQuery, MultiMatchQuery, FuzzyQuery, WildcardQuery, PrefixQuery, RangeQuery, ExistsQuery, FunctionScoreQuery, DisMaxQuery, QueryDSL parser)
- ~350 lines for index segments and merge policy (IndexSegment, SegmentReader, IndexWriter, TieredMergePolicy, LogMergePolicy, MergeScheduler, CommitPoint)
- ~200 lines for near-real-time search (SearcherManager, IndexSearcher, SearchResults, SearchHit)
- ~150 lines for hit highlighting (Highlighter, PlainHighlighter, PostingsHighlighter, FastVectorHighlighter, Fragment)
- ~400 lines for aggregation framework (TermsAggregation, HistogramAggregation, DateHistogramAggregation, RangeAggregation, FilterAggregation, metric aggregations, pipeline aggregations, HyperLogLog++, TDigest)
- ~100 lines for faceted search (FacetSpec, FacetedSearch, FacetResult)
- ~100 lines for scroll/deep pagination (ScrollContext, ScrollManager, SearchAfter)
- ~100 lines for sort configuration (Sort, SortField)
- ~200 lines for index management (FizzSearchEngine, IndexSettings, Index, aliases, reindex)
- ~150 lines for platform integration (EvaluationIndexer, AuditLogIndexer, EventJournalIndexer, MetricsIndexer, SearchMiddleware)
- ~100 lines for CLI integration

~500 tests covering:
- Analyzer pipeline correctness (tokenization, filtering, stemming for all 7+ locales)
- Inverted index construction and posting list operations (add, delete, merge, skip list traversal)
- BM25 scoring accuracy (verified against reference implementations)
- Boolean query execution (AND/OR/NOT intersection, scoring, minimum_should_match)
- Phrase query with slop (positional matching, gap tolerance)
- Fuzzy matching (edit distance automaton, transpositions, prefix length)
- Aggregation correctness (terms counts, histogram bucketing, percentile accuracy, cardinality estimation)
- Segment lifecycle (flush, commit, merge, delete reclamation)
- Near-real-time visibility (documents searchable after refresh but before commit)
- Scroll pagination (state management, expiry, concurrent scrolls)
- Faceted search (post-filter aggregation isolation)
- Highlighting (fragment extraction, multi-term highlighting)
- Platform integration (evaluation indexing, audit log indexing)

Total: ~4,000 lines (implementation + tests)
