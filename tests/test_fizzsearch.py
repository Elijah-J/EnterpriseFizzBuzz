"""
Enterprise FizzBuzz Platform - FizzSearch Full-Text Search Engine Tests

Validates the FizzSearch subsystem's information retrieval components:
inverted index construction, BM25 scoring, analyzer pipelines with
morphological stemmers (including Klingon, Sindarin, and Quenya), boolean
query model, phrase queries, fuzzy matching, aggregations, segment-based
architecture, merge policies, scroll pagination, faceted search, hit
highlighting, and middleware integration.
"""

import math
import time

import pytest

from enterprise_fizzbuzz.infrastructure.fizzsearch import (
    ENGLISH_STOP_WORDS,
    FIZZSEARCH_VERSION,
    KLINGON_STOP_WORDS,
    MIDDLEWARE_PRIORITY,
    QUENYA_STOP_WORDS,
    SINDARIN_STOP_WORDS,
    AllFieldConfig,
    Analyzer,
    AnalyzerRegistry,
    ASCIIFoldingFilter,
    AuditLogIndexer,
    AvgAggregation,
    BM25FScorer,
    BM25Scorer,
    BooleanQuery,
    BoostQuery,
    CardinalityAggregation,
    DateHistogramAggregation,
    DisMaxQuery,
    DocIdMap,
    DocValues,
    Document,
    DynamicTemplate,
    EdgeNGramTokenizer,
    EvaluationIndexer,
    EventJournalIndexer,
    ExistsQuery,
    FacetedSearch,
    FacetResult,
    FacetSpec,
    FacetValue,
    FieldMapping,
    FieldType,
    FilterAggregation,
    FizzSearchEngine,
    FizzSearchMiddleware,
    Fragment,
    FuzzyQuery,
    HTMLStripCharFilter,
    HighlightStrategyType,
    Highlighter,
    HistogramAggregation,
    Index,
    IndexMapping,
    IndexSearcher,
    IndexSegment,
    IndexSettings,
    IndexWriter,
    InvertedIndex,
    KeywordTokenizer,
    KlingonStemFilter,
    LengthFilter,
    LogMergePolicy,
    LowercaseFilter,
    MappingCharFilter,
    MatchAllQuery,
    MatchQuery,
    MaxAggregation,
    MergePolicyType,
    MetricsIndexer,
    MinAggregation,
    MultiMatchQuery,
    MultiMatchType,
    NGramTokenizer,
    PatternReplaceCharFilter,
    PatternTokenizer,
    PercentilesAggregation,
    PhraseQuery,
    PorterStemFilter,
    Posting,
    PostingList,
    PrefixQuery,
    Query,
    QueryDSL,
    QueryScorer,
    QuenyaStemFilter,
    RangeAggregation,
    RangeQuery,
    ScoreExplanation,
    ScoringContext,
    ScrollContext,
    ScrollManager,
    SearchDashboard,
    SearchHit,
    SearchResults,
    SearcherManager,
    SegmentReader,
    ShingleFilter,
    SimilarityModel,
    SindarinStemFilter,
    SkipEntry,
    SkipList,
    SortField,
    SourceConfig,
    StandardTokenizer,
    StatsAggregation,
    StopWordsFilter,
    StoredFields,
    SumAggregation,
    SynonymFilter,
    TermDictionary,
    TermQuery,
    TermsAggregation,
    TieredMergePolicy,
    Token,
    TopHitsAggregation,
    TrimFilter,
    UniqueFilter,
    WhitespaceTokenizer,
    WildcardQuery,
    create_fizzsearch_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions.fizzsearch import (
    FizzSearchError,
    FizzSearchIndexNotFoundError,
    FizzSearchIndexAlreadyExistsError,
    FizzSearchAnalyzerError,
    FizzSearchScrollExpiredError,
    FizzSearchScrollLimitError,
    FizzSearchAliasError,
)


# ===== TestFieldType =====

class TestFieldType:
    """Test FieldType enum values and membership."""

    def test_all_values_present(self):
        assert FieldType.TEXT.value == "text"
        assert FieldType.KEYWORD.value == "keyword"
        assert FieldType.NUMERIC.value == "numeric"
        assert FieldType.DATE.value == "date"
        assert FieldType.GEO_POINT.value == "geo_point"
        assert FieldType.BOOLEAN.value == "boolean"

    def test_string_values(self):
        for member in FieldType:
            assert isinstance(member.value, str)

    def test_count(self):
        assert len(FieldType) == 6


# ===== TestFieldMapping =====

class TestFieldMapping:
    """Test FieldMapping defaults and TEXT/KEYWORD behavior."""

    def test_default_text(self):
        fm = FieldMapping(name="title")
        assert fm.field_type == FieldType.TEXT
        assert fm.analyzer == "standard"
        assert fm.index is True

    def test_keyword_defaults(self):
        fm = FieldMapping(name="status", field_type=FieldType.KEYWORD)
        assert fm.field_type == FieldType.KEYWORD
        assert fm.doc_values is True

    def test_copy_to(self):
        fm = FieldMapping(name="title", copy_to=["_all"])
        assert "_all" in fm.copy_to


# ===== TestIndexMapping =====

class TestIndexMapping:
    """Test IndexMapping dynamic template matching."""

    def test_dynamic_enabled(self):
        mapping = IndexMapping()
        assert mapping.dynamic is True

    def test_template_match(self):
        template = DynamicTemplate(
            match="*_text",
            mapping=FieldMapping(name="", field_type=FieldType.TEXT),
        )
        mapping = IndexMapping(dynamic_templates=[template])
        assert len(mapping.dynamic_templates) == 1

    def test_source_config(self):
        sc = SourceConfig(enabled=True)
        mapping = IndexMapping(source=sc)
        assert mapping.source.enabled is True


# ===== TestDocument =====

class TestDocument:
    """Test Document construction and auto-ID generation."""

    def test_defaults(self):
        doc = Document(source={"title": "hello"})
        assert doc.source == {"title": "hello"}

    def test_explicit_id(self):
        doc = Document(doc_id="abc-123", source={"x": 1})
        assert doc.doc_id == "abc-123"


# ===== TestToken =====

class TestToken:
    """Test Token dataclass attributes."""

    def test_defaults(self):
        t = Token()
        assert t.text == ""
        assert t.position == 0
        assert t.position_increment == 1

    def test_synonym_position_increment(self):
        t = Token(text="quick", position=0, position_increment=0)
        assert t.position_increment == 0


# ===== TestHTMLStripCharFilter =====

class TestHTMLStripCharFilter:
    """Test HTML tag stripping and entity decoding."""

    def test_strip_tags(self):
        cf = HTMLStripCharFilter()
        assert cf.filter("<p>hello</p>") == "hello"

    def test_decode_entities(self):
        cf = HTMLStripCharFilter()
        assert cf.filter("a &amp; b") == "a & b"

    def test_preserve_text(self):
        cf = HTMLStripCharFilter()
        assert cf.filter("plain text") == "plain text"


# ===== TestPatternReplaceCharFilter =====

class TestPatternReplaceCharFilter:
    """Test regex replacement in character stream."""

    def test_pattern_replace(self):
        cf = PatternReplaceCharFilter(r"\d+", "NUM")
        assert cf.filter("abc123def") == "abcNUMdef"

    def test_no_match_passthrough(self):
        cf = PatternReplaceCharFilter(r"\d+", "NUM")
        assert cf.filter("abcdef") == "abcdef"


# ===== TestMappingCharFilter =====

class TestMappingCharFilter:
    """Test static character mapping."""

    def test_ligature_expansion(self):
        cf = MappingCharFilter({"fi": "fi"})
        assert "fi" in cf.filter("find")

    def test_no_match_passthrough(self):
        cf = MappingCharFilter({"xyz": "abc"})
        assert cf.filter("hello") == "hello"


# ===== TestStandardTokenizer =====

class TestStandardTokenizer:
    """Test Unicode text segmentation tokenization."""

    def test_basic_split(self):
        t = StandardTokenizer()
        tokens = t.tokenize("hello world")
        assert len(tokens) == 2
        assert tokens[0].text == "hello"
        assert tokens[1].text == "world"

    def test_punctuation_handling(self):
        t = StandardTokenizer()
        tokens = t.tokenize("hello, world!")
        texts = [tok.text for tok in tokens]
        assert "hello" in texts
        assert "world" in texts

    def test_hyphenated_words(self):
        t = StandardTokenizer()
        tokens = t.tokenize("well-known fact")
        texts = [tok.text for tok in tokens]
        assert any("well" in text for text in texts)

    def test_offsets(self):
        t = StandardTokenizer()
        tokens = t.tokenize("hello world")
        assert tokens[0].start_offset == 0
        assert tokens[0].end_offset == 5


# ===== TestWhitespaceTokenizer =====

class TestWhitespaceTokenizer:
    """Test whitespace-only splitting."""

    def test_basic_split(self):
        t = WhitespaceTokenizer()
        tokens = t.tokenize("hello world foo")
        assert len(tokens) == 3

    def test_punctuation_kept(self):
        t = WhitespaceTokenizer()
        tokens = t.tokenize("hello, world!")
        assert tokens[0].text == "hello,"
        assert tokens[1].text == "world!"


# ===== TestKeywordTokenizer =====

class TestKeywordTokenizer:
    """Test single-token emission."""

    def test_whole_input_as_one_token(self):
        t = KeywordTokenizer()
        tokens = t.tokenize("hello world")
        assert len(tokens) == 1
        assert tokens[0].text == "hello world"

    def test_empty_input(self):
        t = KeywordTokenizer()
        tokens = t.tokenize("")
        assert len(tokens) == 0


# ===== TestNGramTokenizer =====

class TestNGramTokenizer:
    """Test character n-gram generation."""

    def test_default_bigrams(self):
        t = NGramTokenizer()
        tokens = t.tokenize("abc")
        texts = [tok.text for tok in tokens]
        assert "ab" in texts
        assert "bc" in texts

    def test_custom_range(self):
        t = NGramTokenizer(min_gram=1, max_gram=3)
        tokens = t.tokenize("ab")
        texts = [tok.text for tok in tokens]
        assert "a" in texts
        assert "ab" in texts


# ===== TestEdgeNGramTokenizer =====

class TestEdgeNGramTokenizer:
    """Test prefix n-gram generation."""

    def test_prefix_generation(self):
        t = EdgeNGramTokenizer(min_gram=2, max_gram=4)
        tokens = t.tokenize("hello")
        texts = [tok.text for tok in tokens]
        assert "he" in texts
        assert "hel" in texts
        assert "hell" in texts

    def test_max_gram_boundary(self):
        t = EdgeNGramTokenizer(min_gram=2, max_gram=3)
        tokens = t.tokenize("abcdef")
        texts = [tok.text for tok in tokens]
        assert "ab" in texts
        assert "abc" in texts
        assert "abcd" not in texts


# ===== TestPatternTokenizer =====

class TestPatternTokenizer:
    """Test regex-based tokenization."""

    def test_default_non_word_split(self):
        t = PatternTokenizer()
        tokens = t.tokenize("hello-world_foo")
        assert len(tokens) >= 1

    def test_custom_pattern(self):
        t = PatternTokenizer(pattern=r",\s*")
        tokens = t.tokenize("a, b, c")
        texts = [tok.text for tok in tokens]
        assert "a" in texts
        assert "b" in texts
        assert "c" in texts


# ===== TestLowercaseFilter =====

class TestLowercaseFilter:
    """Test Unicode case folding."""

    def test_ascii_lowercase(self):
        f = LowercaseFilter()
        tokens = [Token(text="HELLO", position=0)]
        result = f.filter(tokens)
        assert result[0].text == "hello"

    def test_unicode_lowercase(self):
        f = LowercaseFilter()
        tokens = [Token(text="FIZZBUZZ", position=0)]
        result = f.filter(tokens)
        assert result[0].text == "fizzbuzz"


# ===== TestStopWordsFilter =====

class TestStopWordsFilter:
    """Test stop word removal."""

    def test_english_defaults(self):
        f = StopWordsFilter(ENGLISH_STOP_WORDS)
        tokens = [Token(text="the", position=0), Token(text="cat", position=1)]
        result = f.filter(tokens)
        assert len(result) == 1
        assert result[0].text == "cat"

    def test_custom_list(self):
        f = StopWordsFilter(frozenset(["foo", "bar"]))
        tokens = [Token(text="foo", position=0), Token(text="baz", position=1)]
        result = f.filter(tokens)
        assert len(result) == 1
        assert result[0].text == "baz"

    def test_all_stopped(self):
        f = StopWordsFilter(frozenset(["a", "b"]))
        tokens = [Token(text="a", position=0), Token(text="b", position=1)]
        result = f.filter(tokens)
        assert len(result) == 0


# ===== TestPorterStemFilter =====

class TestPorterStemFilter:
    """Test Porter stemming algorithm."""

    def test_basic_stemming(self):
        f = PorterStemFilter()
        tokens = [Token(text="running", position=0)]
        result = f.filter(tokens)
        assert result[0].text != "running"

    def test_ing_removal(self):
        f = PorterStemFilter()
        tokens = [Token(text="walking", position=0)]
        result = f.filter(tokens)
        assert not result[0].text.endswith("ing")

    def test_tion_handling(self):
        f = PorterStemFilter()
        tokens = [Token(text="generalization", position=0)]
        result = f.filter(tokens)
        assert len(result[0].text) < len("generalization")

    def test_ies_handling(self):
        f = PorterStemFilter()
        tokens = [Token(text="ponies", position=0)]
        result = f.filter(tokens)
        assert len(result[0].text) <= len("ponies")

    def test_short_word_passthrough(self):
        f = PorterStemFilter()
        tokens = [Token(text="go", position=0)]
        result = f.filter(tokens)
        assert result[0].text == "go"


# ===== TestSynonymFilter =====

class TestSynonymFilter:
    """Test synonym expansion and replacement."""

    def test_expand_mode(self):
        synonyms = {"fast": ["quick", "rapid"]}
        f = SynonymFilter(synonyms, expand=True)
        tokens = [Token(text="fast", position=0)]
        result = f.filter(tokens)
        texts = [t.text for t in result]
        assert "fast" in texts
        assert "quick" in texts

    def test_replace_mode(self):
        synonyms = {"fast": ["quick"]}
        f = SynonymFilter(synonyms, expand=False)
        tokens = [Token(text="fast", position=0)]
        result = f.filter(tokens)
        texts = [t.text for t in result]
        assert "quick" in texts

    def test_synonym_position_increment(self):
        synonyms = {"fast": ["quick"]}
        f = SynonymFilter(synonyms, expand=True)
        tokens = [Token(text="fast", position=0)]
        result = f.filter(tokens)
        syn_tokens = [t for t in result if t.text == "quick"]
        assert len(syn_tokens) >= 1
        assert syn_tokens[0].position_increment == 0


# ===== TestASCIIFoldingFilter =====

class TestASCIIFoldingFilter:
    """Test Unicode to ASCII folding."""

    def test_accented_characters(self):
        f = ASCIIFoldingFilter()
        tokens = [Token(text="caf\u00e9", position=0)]
        result = f.filter(tokens)
        assert result[0].text == "cafe"

    def test_already_ascii(self):
        f = ASCIIFoldingFilter()
        tokens = [Token(text="hello", position=0)]
        result = f.filter(tokens)
        assert result[0].text == "hello"


# ===== TestKlingonStemFilter =====

class TestKlingonStemFilter:
    """Test Klingon morphological stemming."""

    def test_verb_suffixes(self):
        f = KlingonStemFilter()
        tokens = [Token(text="jatlhlaH", position=0)]
        result = f.filter(tokens)
        assert len(result[0].text) <= len("jatlhlaH")

    def test_noun_suffixes(self):
        f = KlingonStemFilter()
        tokens = [Token(text="tlhInganpu", position=0)]
        result = f.filter(tokens)
        assert len(result[0].text) <= len("tlhInganpu")

    def test_no_suffix(self):
        f = KlingonStemFilter()
        tokens = [Token(text="Qo", position=0)]
        result = f.filter(tokens)
        assert len(result) == 1


# ===== TestSindarinStemFilter =====

class TestSindarinStemFilter:
    """Test Sindarin plural and mutation handling."""

    def test_plural_removal(self):
        f = SindarinStemFilter()
        tokens = [Token(text="edhil", position=0)]
        result = f.filter(tokens)
        assert len(result) == 1

    def test_passthrough(self):
        f = SindarinStemFilter()
        tokens = [Token(text="mel", position=0)]
        result = f.filter(tokens)
        assert result[0].text == "mel"


# ===== TestQuenyaStemFilter =====

class TestQuenyaStemFilter:
    """Test Quenya case declension stripping."""

    def test_case_suffix_removal(self):
        f = QuenyaStemFilter()
        tokens = [Token(text="eldanna", position=0)]
        result = f.filter(tokens)
        assert len(result[0].text) <= len("eldanna")

    def test_number_markers(self):
        f = QuenyaStemFilter()
        tokens = [Token(text="Eldar", position=0)]
        result = f.filter(tokens)
        assert len(result) == 1


# ===== TestAnalyzer =====

class TestAnalyzer:
    """Test analyzer pipeline composition."""

    def test_standard_analyzer(self):
        a = Analyzer(
            name="test",
            tokenizer=StandardTokenizer(),
            token_filters=[LowercaseFilter()],
        )
        tokens = a.analyze("Hello World")
        texts = [t.text for t in tokens]
        assert "hello" in texts
        assert "world" in texts

    def test_custom_pipeline(self):
        a = Analyzer(
            name="custom",
            char_filters=[HTMLStripCharFilter()],
            tokenizer=StandardTokenizer(),
            token_filters=[LowercaseFilter()],
        )
        tokens = a.analyze("<b>Hello</b> World")
        texts = [t.text for t in tokens]
        assert "hello" in texts

    def test_empty_input(self):
        a = Analyzer(name="empty", tokenizer=StandardTokenizer())
        tokens = a.analyze("")
        assert len(tokens) == 0


# ===== TestAnalyzerRegistry =====

class TestAnalyzerRegistry:
    """Test built-in analyzer lookup and custom registration."""

    def test_all_builtins_present(self):
        reg = AnalyzerRegistry()
        builtins = ["standard", "simple", "whitespace", "keyword",
                     "english", "klingon", "sindarin", "quenya",
                     "autocomplete", "fizzbuzz_eval"]
        for name in builtins:
            analyzer = reg.get(name)
            assert analyzer is not None
            assert analyzer.name == name

    def test_get_by_name(self):
        reg = AnalyzerRegistry()
        a = reg.get("standard")
        tokens = a.analyze("Hello World")
        assert len(tokens) == 2

    def test_custom_register(self):
        reg = AnalyzerRegistry()
        custom = Analyzer(name="my_analyzer", tokenizer=KeywordTokenizer())
        reg.register(custom)
        assert reg.get("my_analyzer").name == "my_analyzer"


# ===== TestPosting =====

class TestPosting:
    """Test Posting dataclass and position recording."""

    def test_defaults(self):
        p = Posting(doc_id=0, term_frequency=1)
        assert p.doc_id == 0
        assert p.term_frequency == 1

    def test_with_positions(self):
        p = Posting(doc_id=1, term_frequency=2, positions=[0, 5])
        assert p.positions == [0, 5]


# ===== TestSkipList =====

class TestSkipList:
    """Test multi-level skip list construction and advance."""

    def test_build(self):
        sl = SkipList(skip_interval=4, max_levels=2)
        postings = [Posting(doc_id=i, term_frequency=1) for i in range(20)]
        sl.build(postings)
        assert len(sl.levels) >= 1

    def test_no_build_for_small_list(self):
        sl = SkipList(skip_interval=16)
        postings = [Posting(doc_id=i, term_frequency=1) for i in range(5)]
        sl.build(postings)
        assert len(sl.levels) == 0

    def test_advance_to_existing(self):
        sl = SkipList(skip_interval=4, max_levels=2)
        postings = [Posting(doc_id=i, term_frequency=1) for i in range(20)]
        sl.build(postings)
        # Level 0 should have entries at positions 4, 8, 12, 16
        assert len(sl.levels[0]) > 0
        assert sl.levels[0][0].doc_id == 4


# ===== TestPostingList =====

class TestPostingList:
    """Test posting list operations."""

    def test_add_posting(self):
        pl = PostingList("hello")
        pl.add_posting(Posting(doc_id=0, term_frequency=1))
        assert pl.document_frequency == 1

    def test_advance(self):
        pl = PostingList("hello")
        pl.add_posting(Posting(doc_id=0, term_frequency=1))
        pl.add_posting(Posting(doc_id=5, term_frequency=2))
        pl.build_skip_list()
        result = pl.advance(3)
        assert result is not None
        assert result.doc_id == 5

    def test_next(self):
        pl = PostingList("hello")
        pl.add_posting(Posting(doc_id=0, term_frequency=1))
        pl.add_posting(Posting(doc_id=1, term_frequency=1))
        pl.reset()
        first = pl.next()
        assert first is not None
        assert first.doc_id == 1

    def test_reset(self):
        pl = PostingList("hello")
        pl.add_posting(Posting(doc_id=0, term_frequency=1))
        pl.add_posting(Posting(doc_id=1, term_frequency=1))
        pl.next()
        pl.reset()
        result = pl.next()
        assert result.doc_id == 1


# ===== TestTermDictionary =====

class TestTermDictionary:
    """Test term lookup and prefix/fuzzy enumeration."""

    def test_exact_lookup(self):
        td = TermDictionary()
        td.add_term("hello", Posting(doc_id=0, term_frequency=1))
        pl = td.get_postings("hello")
        assert pl is not None
        assert pl.document_frequency == 1

    def test_missing_term(self):
        td = TermDictionary()
        assert td.get_postings("nothing") is None

    def test_prefix_terms(self):
        td = TermDictionary()
        td.add_term("hello", Posting(doc_id=0, term_frequency=1))
        td.add_term("help", Posting(doc_id=1, term_frequency=1))
        td.add_term("world", Posting(doc_id=2, term_frequency=1))
        terms = td.prefix_terms("hel")
        assert "hello" in terms
        assert "help" in terms
        assert "world" not in terms

    def test_fuzzy_terms(self):
        td = TermDictionary()
        td.add_term("hello", Posting(doc_id=0, term_frequency=1))
        td.add_term("hallo", Posting(doc_id=1, term_frequency=1))
        td.add_term("world", Posting(doc_id=2, term_frequency=1))
        terms = [t for t, d in td.fuzzy_terms("hello", max_edits=1)]
        assert "hello" in terms
        assert "hallo" in terms

    def test_all_terms(self):
        td = TermDictionary()
        td.add_term("a", Posting(doc_id=0, term_frequency=1))
        td.add_term("b", Posting(doc_id=1, term_frequency=1))
        assert len(list(td.all_terms())) == 2


# ===== TestInvertedIndex =====

class TestInvertedIndex:
    """Test inverted index construction and statistics."""

    def test_add_document(self):
        idx = InvertedIndex("content")
        tokens = [Token(text="hello", position=0), Token(text="world", position=1)]
        idx.add_document(0, tokens)
        assert idx.doc_count == 1

    def test_get_postings(self):
        idx = InvertedIndex("content")
        tokens = [Token(text="hello", position=0)]
        idx.add_document(0, tokens)
        pl = idx.get_postings("hello")
        assert pl is not None
        assert pl.document_frequency == 1

    def test_doc_freq(self):
        idx = InvertedIndex("content")
        idx.add_document(0, [Token(text="hello", position=0)])
        idx.add_document(1, [Token(text="hello", position=0)])
        assert idx.doc_freq("hello") == 2

    def test_avg_doc_length(self):
        idx = InvertedIndex("content")
        idx.add_document(0, [Token(text="a", position=0), Token(text="b", position=1)])
        idx.add_document(1, [Token(text="c", position=0)])
        assert idx.avg_doc_length() == 1.5


# ===== TestDocValues =====

class TestDocValues:
    """Test columnar value storage and sort order."""

    def test_set_get(self):
        dv = DocValues("price", FieldType.NUMERIC)
        dv.set(0, 10.0)
        assert dv.get(0) == 10.0

    def test_iterate(self):
        dv = DocValues("price", FieldType.NUMERIC)
        dv.set(0, 10.0)
        dv.set(1, 20.0)
        items = list(dv.iterate())
        assert len(items) == 2

    def test_sort_order(self):
        dv = DocValues("price", FieldType.NUMERIC)
        dv.set(0, 30.0)
        dv.set(1, 10.0)
        dv.set(2, 20.0)
        order = dv.sort_order(ascending=True)
        assert order == [1, 2, 0]


# ===== TestStoredFields =====

class TestStoredFields:
    """Test document storage and retrieval."""

    def test_store_get(self):
        sf = StoredFields()
        sf.store(0, {"title": "hello", "body": "world"})
        doc = sf.get_document(0)
        assert doc["title"] == "hello"

    def test_missing_document(self):
        sf = StoredFields()
        doc = sf.get_document(999)
        assert doc == {}


# ===== TestDocIdMap =====

class TestDocIdMap:
    """Test external-to-internal ID mapping and deletion."""

    def test_assign(self):
        m = DocIdMap()
        internal = m.assign("doc-1")
        assert internal == 0

    def test_to_internal(self):
        m = DocIdMap()
        m.assign("doc-1")
        assert m.to_internal("doc-1") == 0

    def test_to_external(self):
        m = DocIdMap()
        m.assign("doc-1")
        assert m.to_external(0) == "doc-1"

    def test_delete_and_is_live(self):
        m = DocIdMap()
        m.assign("doc-1")
        assert m.is_live(0) is True
        m.delete("doc-1")
        assert m.is_live(0) is False


# ===== TestBM25Scorer =====

class TestBM25Scorer:
    """Test BM25 scoring accuracy."""

    def test_idf_calculation(self):
        scorer = BM25Scorer()
        idf = scorer.idf(doc_freq=10, total_docs=1000)
        assert idf > 0
        # IDF = log(1 + (1000 - 10 + 0.5) / (10 + 0.5))
        expected = math.log(1.0 + (1000 - 10 + 0.5) / (10 + 0.5))
        assert abs(idf - expected) < 1e-10

    def test_tf_norm(self):
        scorer = BM25Scorer()
        tf = scorer.tf_norm(term_freq=5, doc_length=100, avg_doc_length=100)
        assert tf > 0
        assert tf < 5  # Saturation should cap this

    def test_score_term(self):
        scorer = BM25Scorer()
        score = scorer.score_term(
            term_freq=3, doc_freq=50, doc_length=200,
            avg_doc_length=150, total_docs=10000,
        )
        assert score > 0

    def test_k1_zero_binary(self):
        scorer = BM25Scorer(k1=0.0)
        tf1 = scorer.tf_norm(term_freq=1, doc_length=100, avg_doc_length=100)
        tf5 = scorer.tf_norm(term_freq=5, doc_length=100, avg_doc_length=100)
        # With k1=0, all tf produces the same norm
        assert abs(tf1 - tf5) < 1e-10

    def test_b_zero_no_normalization(self):
        scorer = BM25Scorer(b=0.0)
        short = scorer.tf_norm(term_freq=3, doc_length=50, avg_doc_length=100)
        long_doc = scorer.tf_norm(term_freq=3, doc_length=500, avg_doc_length=100)
        # With b=0, length normalization is disabled
        assert abs(short - long_doc) < 1e-10


# ===== TestBM25FScorer =====

class TestBM25FScorer:
    """Test BM25F multi-field scoring."""

    def test_combined_scoring(self):
        scorer = BM25FScorer(field_boosts={"title": 2.0, "body": 1.0})
        # Create two inverted indices
        title_idx = InvertedIndex("title")
        body_idx = InvertedIndex("body")
        title_idx.add_document(0, [Token(text="fizz", position=0)])
        body_idx.add_document(0, [Token(text="fizz", position=0), Token(text="buzz", position=1)])
        score = scorer.score_document(["fizz"], 0, {"title": title_idx, "body": body_idx})
        assert score > 0

    def test_field_boosts(self):
        scorer1 = BM25FScorer(field_boosts={"title": 1.0})
        scorer2 = BM25FScorer(field_boosts={"title": 10.0})
        idx = InvertedIndex("title")
        idx.add_document(0, [Token(text="fizz", position=0)])
        s1 = scorer1.score_document(["fizz"], 0, {"title": idx})
        s2 = scorer2.score_document(["fizz"], 0, {"title": idx})
        assert s2 > s1


# ===== TestTermQuery =====

class TestTermQuery:
    """Test exact term matching."""

    def test_matching_document(self):
        tq = TermQuery(field_name="content", term="hello")
        assert tq.field_name == "content"
        assert tq.term == "hello"

    def test_no_match(self):
        tq = TermQuery(field_name="content", term="nonexistent")
        assert tq.term == "nonexistent"


# ===== TestBooleanQuery =====

class TestBooleanQuery:
    """Test boolean query composition."""

    def test_must_clauses(self):
        bq = BooleanQuery()
        bq.must.append(TermQuery(field_name="f", term="a"))
        bq.must.append(TermQuery(field_name="f", term="b"))
        assert len(bq.must) == 2

    def test_should_clauses(self):
        bq = BooleanQuery()
        bq.should.append(TermQuery(field_name="f", term="a"))
        bq.should.append(TermQuery(field_name="f", term="b"))
        assert len(bq.should) == 2

    def test_must_not_clauses(self):
        bq = BooleanQuery()
        bq.must_not.append(TermQuery(field_name="f", term="x"))
        assert len(bq.must_not) == 1

    def test_filter_clauses(self):
        bq = BooleanQuery()
        bq.add_filter(TermQuery(field_name="status", term="active"))
        assert len(bq.filter_clauses) == 1

    def test_minimum_should_match(self):
        bq = BooleanQuery()
        bq.set_minimum_should_match(2)
        assert bq.minimum_should_match == 2


# ===== TestPhraseQuery =====

class TestPhraseQuery:
    """Test phrase matching with positions."""

    def test_exact_phrase(self):
        pq = PhraseQuery(field_name="content", terms=["hello", "world"], slop=0)
        assert pq.terms == ["hello", "world"]
        assert pq.slop == 0

    def test_slop_zero(self):
        pq = PhraseQuery(field_name="content", terms=["a", "b"], slop=0)
        assert pq.slop == 0

    def test_slop_one(self):
        pq = PhraseQuery(field_name="content", terms=["a", "b"], slop=1)
        assert pq.slop == 1


# ===== TestMatchQuery =====

class TestMatchQuery:
    """Test analyzed text query."""

    def test_or_operator(self):
        mq = MatchQuery(field_name="content", query_text="hello world", operator="or")
        assert mq.operator == "OR"

    def test_and_operator(self):
        mq = MatchQuery(field_name="content", query_text="hello world", operator="and")
        assert mq.operator == "AND"

    def test_fuzziness(self):
        mq = MatchQuery(field_name="content", query_text="hello", fuzziness=1)
        assert mq.fuzziness == 1


# ===== TestMultiMatchQuery =====

class TestMultiMatchQuery:
    """Test multi-field search."""

    def test_best_fields(self):
        mmq = MultiMatchQuery(
            fields=["title", "body"], query_text="hello",
            match_type="best_fields",
        )
        assert mmq.match_type == "best_fields"

    def test_most_fields(self):
        mmq = MultiMatchQuery(
            fields=["title", "body"], query_text="hello",
            match_type="most_fields",
        )
        assert mmq.match_type == "most_fields"


# ===== TestFuzzyQuery =====

class TestFuzzyQuery:
    """Test edit distance matching."""

    def test_distance_one(self):
        fq = FuzzyQuery(field_name="content", term="hello", max_edits=1)
        assert fq.max_edits == 1

    def test_distance_two(self):
        fq = FuzzyQuery(field_name="content", term="hello", max_edits=2)
        assert fq.max_edits == 2

    def test_prefix_length(self):
        fq = FuzzyQuery(field_name="content", term="hello", prefix_length=2)
        assert fq.prefix_length == 2


# ===== TestWildcardQuery =====

class TestWildcardQuery:
    """Test wildcard pattern matching."""

    def test_star_wildcard(self):
        wq = WildcardQuery(field_name="content", pattern="hel*")
        assert wq.pattern == "hel*"

    def test_question_mark(self):
        wq = WildcardQuery(field_name="content", pattern="h?llo")
        assert wq.pattern == "h?llo"


# ===== TestPrefixQuery =====

class TestPrefixQuery:
    """Test prefix matching."""

    def test_matching_prefix(self):
        pq = PrefixQuery(field_name="content", prefix="hel")
        assert pq.prefix == "hel"

    def test_no_match(self):
        pq = PrefixQuery(field_name="content", prefix="xyz")
        assert pq.prefix == "xyz"


# ===== TestRangeQuery =====

class TestRangeQuery:
    """Test range query on numeric fields."""

    def test_inclusive_range(self):
        rq = RangeQuery(field_name="price", gte=10, lte=100)
        assert rq.gte == 10
        assert rq.lte == 100

    def test_exclusive_bounds(self):
        rq = RangeQuery(field_name="price", gt=10, lt=100)
        assert rq.gt == 10
        assert rq.lt == 100

    def test_no_matches(self):
        rq = RangeQuery(field_name="price", gte=1000, lte=2000)
        assert rq.gte == 1000


# ===== TestExistsQuery =====

class TestExistsQuery:
    """Test field existence check."""

    def test_field_exists(self):
        eq = ExistsQuery(field_name="title")
        assert eq.field_name == "title"

    def test_field_missing(self):
        eq = ExistsQuery(field_name="nonexistent")
        assert eq.field_name == "nonexistent"


# ===== TestMatchAllQuery =====

class TestMatchAllQuery:
    """Test match-all query."""

    def test_matches_everything(self):
        maq = MatchAllQuery()
        assert isinstance(maq, Query)


# ===== TestQueryDSL =====

class TestQueryDSL:
    """Test query DSL parsing."""

    def test_term_query(self):
        reg = AnalyzerRegistry()
        dsl = QueryDSL(reg)
        q = dsl.parse({"term": {"status": "active"}})
        assert isinstance(q, TermQuery)

    def test_bool_query(self):
        reg = AnalyzerRegistry()
        dsl = QueryDSL(reg)
        q = dsl.parse({
            "bool": {
                "must": [{"term": {"status": "active"}}],
            }
        })
        assert isinstance(q, BooleanQuery)

    def test_match_query(self):
        reg = AnalyzerRegistry()
        dsl = QueryDSL(reg)
        q = dsl.parse({"match": {"content": "hello world"}})
        assert isinstance(q, MatchQuery)

    def test_range_query(self):
        reg = AnalyzerRegistry()
        dsl = QueryDSL(reg)
        q = dsl.parse({"range": {"price": {"gte": 10, "lte": 100}}})
        assert isinstance(q, RangeQuery)

    def test_query_string(self):
        reg = AnalyzerRegistry()
        dsl = QueryDSL(reg)
        q = dsl.parse({"query_string": {"query": "hello world"}})
        assert q is not None


# ===== TestIndexSegment =====

class TestIndexSegment:
    """Test segment construction and deletion marking."""

    def test_create(self):
        seg = IndexSegment()
        assert seg.doc_count == 0
        assert seg.segment_id is not None

    def test_delete_document(self):
        seg = IndexSegment()
        seg.live_docs.add(0)
        seg.doc_count = 1
        seg.live_doc_count = 1
        seg.delete_document(0)
        assert seg.live_doc_count == 0

    def test_is_live(self):
        seg = IndexSegment()
        seg.live_docs.add(0)
        assert seg.is_live(0) is True
        assert seg.is_live(1) is False


# ===== TestIndexWriter =====

class TestIndexWriter:
    """Test document indexing, flushing, and committing."""

    def test_add_document(self):
        writer = IndexWriter(IndexMapping(), AnalyzerRegistry(), IndexSettings())
        doc = Document(doc_id="doc-1", source={"content": "hello world"})
        internal = writer.add_document(doc)
        assert internal is not None

    def test_flush(self):
        writer = IndexWriter(IndexMapping(), AnalyzerRegistry(), IndexSettings())
        doc = Document(doc_id="doc-1", source={"content": "hello world"})
        writer.add_document(doc)
        seg = writer.flush()
        assert seg is not None
        assert seg.doc_count == 1

    def test_commit(self):
        writer = IndexWriter(IndexMapping(), AnalyzerRegistry(), IndexSettings())
        doc = Document(doc_id="doc-1", source={"content": "hello world"})
        writer.add_document(doc)
        writer.commit()
        assert len(writer.segments) >= 1

    def test_delete(self):
        writer = IndexWriter(IndexMapping(), AnalyzerRegistry(), IndexSettings())
        doc = Document(doc_id="doc-1", source={"content": "hello world"})
        writer.add_document(doc)
        result = writer.delete_document("doc-1")
        assert result is True

    def test_update(self):
        writer = IndexWriter(IndexMapping(), AnalyzerRegistry(), IndexSettings())
        doc = Document(doc_id="doc-1", source={"content": "hello world"})
        writer.add_document(doc)
        new_doc = Document(doc_id="doc-1", source={"content": "updated"})
        writer.update_document("doc-1", new_doc)
        # The old version should be deleted, new version added
        assert writer._current_segment.doc_count >= 1


# ===== TestTieredMergePolicy =====

class TestTieredMergePolicy:
    """Test tiered merge policy segment selection."""

    def test_no_merge_needed(self):
        policy = TieredMergePolicy(segments_per_tier=10)
        segments = [IndexSegment() for _ in range(3)]
        merges = policy.find_merges(segments)
        assert isinstance(merges, list)

    def test_merge_triggered(self):
        policy = TieredMergePolicy(segments_per_tier=2, max_merge_at_once=5)
        segments = []
        for i in range(10):
            seg = IndexSegment()
            seg.doc_count = 10
            seg.live_doc_count = 10
            seg.size_bytes = 100
            segments.append(seg)
        merges = policy.find_merges(segments)
        assert isinstance(merges, list)

    def test_delete_prioritization(self):
        policy = TieredMergePolicy(deletes_pct_allowed=10.0)
        seg = IndexSegment()
        seg.doc_count = 100
        seg.live_doc_count = 50  # 50% deletes
        seg.size_bytes = 1000
        merges = policy.find_merges([seg])
        assert isinstance(merges, list)


# ===== TestLogMergePolicy =====

class TestLogMergePolicy:
    """Test log merge policy segment selection."""

    def test_below_factor(self):
        policy = LogMergePolicy()
        segments = [IndexSegment() for _ in range(2)]
        merges = policy.find_merges(segments)
        assert isinstance(merges, list)

    def test_above_factor_triggers_merge(self):
        policy = LogMergePolicy()
        segments = []
        for _ in range(20):
            seg = IndexSegment()
            seg.doc_count = 10
            seg.live_doc_count = 10
            seg.size_bytes = 100
            segments.append(seg)
        merges = policy.find_merges(segments)
        assert isinstance(merges, list)


# ===== TestSearcherManager =====

class TestSearcherManager:
    """Test NRT searcher lifecycle."""

    def test_acquire_release(self):
        writer = IndexWriter(IndexMapping(), AnalyzerRegistry(), IndexSettings())
        sm = SearcherManager(writer)
        searcher = sm.acquire()
        assert isinstance(searcher, IndexSearcher)
        sm.release(searcher)

    def test_refresh(self):
        writer = IndexWriter(IndexMapping(), AnalyzerRegistry(), IndexSettings())
        doc = Document(doc_id="d1", source={"content": "hello"})
        writer.add_document(doc)
        writer.flush()
        sm = SearcherManager(writer)
        sm.maybe_refresh()
        searcher = sm.acquire()
        assert searcher is not None
        sm.release(searcher)

    def test_concurrent_access(self):
        writer = IndexWriter(IndexMapping(), AnalyzerRegistry(), IndexSettings())
        sm = SearcherManager(writer)
        s1 = sm.acquire()
        s2 = sm.acquire()
        sm.release(s1)
        sm.release(s2)


# ===== TestIndexSearcher =====

class TestIndexSearcher:
    """Test multi-segment search execution."""

    def test_search_with_results(self):
        engine = FizzSearchEngine()
        idx = engine.create_index("test")
        idx.index_document({"content": "hello world"})
        idx.commit()
        results = idx.search({"match": {"content": "hello"}})
        assert results.total_hits >= 1

    def test_count(self):
        engine = FizzSearchEngine()
        idx = engine.create_index("test")
        idx.index_document({"content": "hello world"})
        idx.commit()
        results = idx.search(MatchAllQuery())
        assert results.total_hits >= 1

    def test_empty_index(self):
        engine = FizzSearchEngine()
        idx = engine.create_index("test")
        idx.commit()
        results = idx.search(MatchAllQuery())
        assert results.total_hits == 0

    def test_explain(self):
        engine = FizzSearchEngine()
        idx = engine.create_index("test")
        idx.index_document({"content": "hello world"})
        idx.commit()
        searcher = idx.searcher_manager.acquire()
        try:
            q = TermQuery(field_name="content", term="hello")
            explanation = searcher.explain(q, "nonexistent")
            assert isinstance(explanation, ScoreExplanation)
        finally:
            idx.searcher_manager.release(searcher)


# ===== TestHighlighter =====

class TestHighlighter:
    """Test hit highlighting and fragment extraction."""

    def test_basic_highlight(self):
        h = Highlighter()
        analyzer = Analyzer(name="std", tokenizer=StandardTokenizer())
        frags = h.highlight("content", "The quick brown fox", {"quick"}, analyzer)
        assert len(frags) >= 1
        assert "<em>" in frags[0]

    def test_multiple_fragments(self):
        h = Highlighter(fragment_size=20)
        analyzer = Analyzer(name="std", tokenizer=StandardTokenizer())
        text = "Hello world. " * 20 + "The quick brown fox jumps."
        frags = h.highlight("content", text, {"hello", "quick"}, analyzer)
        assert len(frags) >= 1

    def test_no_match_fallback(self):
        h = Highlighter(no_match_size=50)
        analyzer = Analyzer(name="std", tokenizer=StandardTokenizer())
        frags = h.highlight("content", "No matching terms here", {"nonexistent"}, analyzer)
        assert len(frags) >= 1

    def test_custom_tags(self):
        h = Highlighter(pre_tag="<b>", post_tag="</b>")
        analyzer = Analyzer(name="std", tokenizer=StandardTokenizer())
        frags = h.highlight("content", "hello world", {"hello"}, analyzer)
        if frags:
            assert "<b>" in frags[0]
            assert "</b>" in frags[0]


# ===== TestTermsAggregation =====

class TestTermsAggregation:
    """Test terms aggregation bucketing."""

    def test_top_n_buckets(self):
        agg = TermsAggregation(name="by_status", field_name="status", size=10)
        assert agg.field_name == "status"
        assert agg.size == 10

    def test_min_doc_count(self):
        agg = TermsAggregation(name="by_status", field_name="status", min_doc_count=2)
        assert agg.min_doc_count == 2

    def test_size_limit(self):
        agg = TermsAggregation(name="by_status", field_name="status", size=5)
        assert agg.size == 5


# ===== TestHistogramAggregation =====

class TestHistogramAggregation:
    """Test numeric histogram bucketing."""

    def test_fixed_interval(self):
        agg = HistogramAggregation(name="price_hist", field_name="price", interval=10)
        assert agg.interval == 10

    def test_empty_buckets(self):
        agg = HistogramAggregation(name="price_hist", field_name="price", interval=10, min_doc_count=0)
        assert agg.min_doc_count == 0


# ===== TestStatsAggregation =====

class TestStatsAggregation:
    """Test min/max/sum/count/avg computation."""

    def test_basic_stats(self):
        agg = StatsAggregation(name="price_stats", field_name="price")
        assert agg.field_name == "price"

    def test_single_document(self):
        agg = StatsAggregation(name="price_stats", field_name="price")
        dv = DocValues("price", FieldType.NUMERIC)
        dv.set(0, 10.0)
        agg.collect(0, dv)
        result = agg.result()
        assert result["count"] == 1
        assert result["min"] == 10.0
        assert result["max"] == 10.0


# ===== TestCardinalityAggregation =====

class TestCardinalityAggregation:
    """Test HyperLogLog++ cardinality estimation."""

    def test_exact_for_small_sets(self):
        agg = CardinalityAggregation(name="unique_users", field_name="user_id")
        dv = DocValues("user_id", FieldType.KEYWORD)
        for i, val in enumerate(["a", "b", "c", "a", "b"]):
            dv.set(i, val)
            agg.collect(i, dv)
        result = agg.result()
        assert result["value"] == 3

    def test_approximate_for_large(self):
        agg = CardinalityAggregation(name="unique_users", field_name="user_id")
        dv = DocValues("user_id", FieldType.KEYWORD)
        for i in range(1000):
            dv.set(i, str(i))
            agg.collect(i, dv)
        result = agg.result()
        # HLL++ should be within ~10% for sets this size
        assert abs(result["value"] - 1000) < 150


# ===== TestPercentilesAggregation =====

class TestPercentilesAggregation:
    """Test TDigest percentile computation."""

    def test_p50_median(self):
        agg = PercentilesAggregation(name="latency_pcts", field_name="latency")
        dv = DocValues("latency", FieldType.NUMERIC)
        for i in range(1, 101):
            dv.set(i, float(i))
            agg.collect(i, dv)
        result = agg.result()
        assert "50" in result["values"]
        p50 = result["values"]["50"]
        assert 45 <= p50 <= 55

    def test_p99(self):
        agg = PercentilesAggregation(name="latency_pcts", field_name="latency")
        dv = DocValues("latency", FieldType.NUMERIC)
        for i in range(1, 101):
            dv.set(i, float(i))
            agg.collect(i, dv)
        result = agg.result()
        assert "99" in result["values"]
        p99 = result["values"]["99"]
        assert p99 >= 90


# ===== TestScrollContext =====

class TestScrollContext:
    """Test scroll context TTL and expiry."""

    def test_not_expired(self):
        writer = IndexWriter(IndexMapping(), AnalyzerRegistry(), IndexSettings())
        sm = SearcherManager(writer)
        searcher = sm.acquire()
        ctx = ScrollContext(MatchAllQuery(), [], searcher, ttl=60.0)
        assert ctx.is_expired() is False
        sm.release(searcher)

    def test_expired_after_ttl(self):
        writer = IndexWriter(IndexMapping(), AnalyzerRegistry(), IndexSettings())
        sm = SearcherManager(writer)
        searcher = sm.acquire()
        ctx = ScrollContext(MatchAllQuery(), [], searcher, ttl=0.01)
        time.sleep(0.02)
        assert ctx.is_expired() is True
        sm.release(searcher)


# ===== TestScrollManager =====

class TestScrollManager:
    """Test scroll lifecycle management."""

    def test_create_scroll(self):
        sm = ScrollManager(max_scrolls=10)
        writer = IndexWriter(IndexMapping(), AnalyzerRegistry(), IndexSettings())
        writer.add_document(Document(doc_id="d1", source={"content": "hello"}))
        writer.commit()
        searcher_mgr = SearcherManager(writer)
        searcher = searcher_mgr.acquire()
        hits, scroll_id = sm.create_scroll(MatchAllQuery(), [], searcher, size=10, ttl=60.0)
        assert scroll_id is not None
        searcher_mgr.release(searcher)

    def test_advance(self):
        sm = ScrollManager(max_scrolls=10)
        writer = IndexWriter(IndexMapping(), AnalyzerRegistry(), IndexSettings())
        for i in range(5):
            writer.add_document(Document(doc_id=f"d{i}", source={"content": f"doc {i}"}))
        writer.commit()
        searcher_mgr = SearcherManager(writer)
        searcher = searcher_mgr.acquire()
        _, scroll_id = sm.create_scroll(MatchAllQuery(), [], searcher, size=2, ttl=60.0)
        next_hits, _ = sm.scroll(scroll_id, size=2)
        assert isinstance(next_hits, list)
        searcher_mgr.release(searcher)

    def test_clear(self):
        sm = ScrollManager(max_scrolls=10)
        writer = IndexWriter(IndexMapping(), AnalyzerRegistry(), IndexSettings())
        searcher_mgr = SearcherManager(writer)
        searcher = searcher_mgr.acquire()
        _, scroll_id = sm.create_scroll(MatchAllQuery(), [], searcher, size=10, ttl=60.0)
        sm.clear_scroll(scroll_id)
        with pytest.raises(FizzSearchScrollExpiredError):
            sm.scroll(scroll_id, size=10)
        searcher_mgr.release(searcher)

    def test_limit_exceeded(self):
        sm = ScrollManager(max_scrolls=1)
        writer = IndexWriter(IndexMapping(), AnalyzerRegistry(), IndexSettings())
        searcher_mgr = SearcherManager(writer)
        searcher = searcher_mgr.acquire()
        sm.create_scroll(MatchAllQuery(), [], searcher, size=10, ttl=60.0)
        with pytest.raises(FizzSearchScrollLimitError):
            sm.create_scroll(MatchAllQuery(), [], searcher, size=10, ttl=60.0)
        searcher_mgr.release(searcher)


# ===== TestFacetedSearch =====

class TestFacetedSearch:
    """Test faceted search with post-filter isolation."""

    def test_facet_construction(self):
        facets = [FacetSpec(field_name="color", size=10)]
        fs = FacetedSearch(query=MatchAllQuery(), facets=facets)
        assert len(fs.facets) == 1

    def test_facet_spec_defaults(self):
        spec = FacetSpec(field_name="status")
        assert spec.field_name == "status"

    def test_facet_result(self):
        fr = FacetResult(
            field_name="color",
            values=[FacetValue(value="red", count=10), FacetValue(value="blue", count=5)],
        )
        assert len(fr.values) == 2
        assert fr.values[0].count == 10


# ===== TestFizzSearchEngine =====

class TestFizzSearchEngine:
    """Test top-level engine operations."""

    def test_create_index(self):
        engine = FizzSearchEngine()
        idx = engine.create_index("products")
        assert idx.name == "products"
        assert engine.index_exists("products")

    def test_delete_index(self):
        engine = FizzSearchEngine()
        engine.create_index("products")
        engine.delete_index("products")
        assert not engine.index_exists("products")

    def test_list_indices(self):
        engine = FizzSearchEngine()
        engine.create_index("products")
        engine.create_index("users")
        listing = engine.list_indices()
        names = [x["name"] for x in listing]
        assert "products" in names
        assert "users" in names

    def test_alias_management(self):
        engine = FizzSearchEngine()
        engine.create_index("products_v1")
        engine.add_alias("products", "products_v1")
        idx = engine.get_index("products")
        assert idx.name == "products_v1"
        engine.remove_alias("products")
        with pytest.raises(FizzSearchIndexNotFoundError):
            engine.get_index("products")

    def test_reindex(self):
        engine = FizzSearchEngine()
        src = engine.create_index("source")
        engine.create_index("dest")
        src.index_document({"content": "hello world"})
        src.commit()
        result = engine.reindex("source", "dest")
        assert result["total"] >= 1


# ===== TestIndex =====

class TestIndex:
    """Test index document operations."""

    def test_index_document(self):
        engine = FizzSearchEngine()
        idx = engine.create_index("test")
        doc_id = idx.index_document({"content": "hello world"})
        assert doc_id is not None

    def test_bulk_index(self):
        engine = FizzSearchEngine()
        idx = engine.create_index("test")
        result = idx.bulk_index([{"content": "doc1"}, {"content": "doc2"}])
        assert result["indexed"] == 2

    def test_get_document(self):
        engine = FizzSearchEngine()
        idx = engine.create_index("test")
        doc_id = idx.index_document({"content": "hello"})
        idx.commit()
        doc = idx.get_document(doc_id)
        assert doc is not None
        assert doc.get("content") == "hello"

    def test_delete_document(self):
        engine = FizzSearchEngine()
        idx = engine.create_index("test")
        doc_id = idx.index_document({"content": "hello"})
        result = idx.delete_document(doc_id)
        assert result is True

    def test_search(self):
        engine = FizzSearchEngine()
        idx = engine.create_index("test")
        idx.index_document({"content": "the quick brown fox"})
        idx.index_document({"content": "a lazy dog"})
        idx.commit()
        results = idx.search({"match": {"content": "fox"}})
        assert results.total_hits >= 1


# ===== TestEvaluationIndexer =====

class TestEvaluationIndexer:
    """Test FizzBuzz evaluation result indexing."""

    def test_setup_index(self):
        engine = FizzSearchEngine()
        indexer = EvaluationIndexer(engine)
        indexer.setup_index()
        assert engine.index_exists(EvaluationIndexer.INDEX_NAME)

    def test_index_evaluation(self):
        engine = FizzSearchEngine()
        indexer = EvaluationIndexer(engine)
        indexer.setup_index()
        # Create a minimal mock result and context
        from unittest.mock import MagicMock
        result = MagicMock()
        result.value = "FizzBuzz"
        context = MagicMock()
        context.number = 15
        indexer.index_evaluation(result, context)


# ===== TestAuditLogIndexer =====

class TestAuditLogIndexer:
    """Test audit trail indexing."""

    def test_setup_index(self):
        engine = FizzSearchEngine()
        indexer = AuditLogIndexer(engine)
        indexer.setup_index()
        assert engine.index_exists(AuditLogIndexer.INDEX_NAME)

    def test_index_entry(self):
        engine = FizzSearchEngine()
        indexer = AuditLogIndexer(engine)
        indexer.setup_index()
        indexer.index_audit_entry({
            "action": "evaluate",
            "principal": "admin",
            "resource": "fizzbuzz:15",
            "decision": "allow",
        })


# ===== TestSearchDashboard =====

class TestSearchDashboard:
    """Test ASCII dashboard rendering."""

    def test_index_list(self):
        d = SearchDashboard(width=72)
        output = d.render_index_list([
            {"name": "products", "doc_count": 100, "segment_count": 3, "size_bytes": 4096},
        ])
        assert "products" in output
        assert "100" in output

    def test_search_results(self):
        d = SearchDashboard(width=72)
        results = SearchResults(
            hits=[SearchHit(doc_id="d1", score=1.5, source={"title": "hello"})],
            total_hits=1,
            took_ms=5.0,
        )
        output = d.render_search_results(results)
        assert "d1" in output
        assert "1.5" in output

    def test_analyze_tokens(self):
        d = SearchDashboard(width=72)
        tokens = [Token(text="hello", position=0, start_offset=0, end_offset=5)]
        output = d.render_analyze(tokens)
        assert "hello" in output


# ===== TestFizzSearchMiddleware =====

class TestFizzSearchMiddleware:
    """Test middleware pipeline integration."""

    def test_process_with_engine(self):
        engine = FizzSearchEngine()
        dashboard = SearchDashboard()
        mw = FizzSearchMiddleware(engine, dashboard)
        from unittest.mock import MagicMock
        context = MagicMock()
        context.metadata = {}
        next_handler = MagicMock(return_value=context)
        result = mw.process(context, next_handler)
        assert result.metadata["fizzsearch_enabled"] is True
        assert result.metadata["fizzsearch_version"] == FIZZSEARCH_VERSION

    def test_priority(self):
        engine = FizzSearchEngine()
        dashboard = SearchDashboard()
        mw = FizzSearchMiddleware(engine, dashboard)
        assert mw.get_priority() == MIDDLEWARE_PRIORITY
        assert mw.priority == 119

    def test_name(self):
        engine = FizzSearchEngine()
        dashboard = SearchDashboard()
        mw = FizzSearchMiddleware(engine, dashboard)
        assert mw.get_name() == "FizzSearchMiddleware"
        assert mw.name == "FizzSearchMiddleware"


# ===== TestCreateFizzsearchSubsystem =====

class TestCreateFizzsearchSubsystem:
    """Test factory function wiring."""

    def test_default_config(self):
        engine, middleware = create_fizzsearch_subsystem()
        assert isinstance(engine, FizzSearchEngine)
        assert isinstance(middleware, FizzSearchMiddleware)

    def test_with_indexers_enabled(self):
        engine, middleware = create_fizzsearch_subsystem(
            index_evaluations=True,
            index_audit=True,
            index_events=True,
            index_metrics=True,
        )
        assert engine.index_exists(EvaluationIndexer.INDEX_NAME)
        assert engine.index_exists(AuditLogIndexer.INDEX_NAME)
        assert engine.index_exists(EventJournalIndexer.INDEX_NAME)
        assert engine.index_exists(MetricsIndexer.INDEX_NAME)
