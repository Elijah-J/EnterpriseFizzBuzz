import pytest
from unittest.mock import MagicMock, patch
from enterprise_fizzbuzz.domain.interfaces import IRuleEngine
from enterprise_fizzbuzz.domain.models import FizzBuzzResult

# Expected to fail in TDD since it's not implemented yet
from enterprise_fizzbuzz.infrastructure.fizzchat import FizzChatEngine

@pytest.fixture
def mock_chroma():
    """Mock ChromaDB for RAG pipeline context retrieval."""
    with patch("enterprise_fizzbuzz.infrastructure.fizzchat.ChromaDB", autospec=True) as mock:
        yield mock.return_value

@pytest.fixture
def mock_llm():
    """Mock LLM used for generation."""
    with patch("enterprise_fizzbuzz.infrastructure.fizzchat.LLM", autospec=True) as mock:
        yield mock.return_value

@pytest.fixture
def engine(mock_chroma, mock_llm):
    """Instantiate the FizzChatEngine with mocked dependencies."""
    return FizzChatEngine(chroma=mock_chroma, llm=mock_llm)

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
def test_fizzchat_correct_returns(engine, mock_llm, mock_chroma, number, expected_output):
    """Verify that FizzChatEngine returns the correct FizzBuzz strings using the LLM."""
    # Setup mock LLM to return the expected output
    mock_llm.generate.return_value = expected_output
    
    # Provide empty rules as the LLM handles logic via RAG context
    rules = []
    
    result = engine.evaluate(number, rules)
    
    assert isinstance(result, FizzBuzzResult)
    assert result.output == expected_output
    assert result.number == number
    
    # Ensure LLM and ChromaDB were interacted with
    mock_chroma.query.assert_called()
    mock_llm.generate.assert_called()

def test_rlhf_bob_correction(engine, mock_llm, mock_chroma):
    """Verify the RLHF mechanism where Bob corrects an LLM hallucination."""
    number = 3
    # LLM hallucinates "Bazz" instead of "Fizz" initially
    mock_llm.generate.side_effect = ["Bazz", "Fizz"]
    
    # We mock Bob's RLHF feedback mechanism within the engine
    with patch.object(engine, "apply_rlhf_correction", return_value="Fizz") as mock_rlhf:
        result = engine.evaluate(number, [])
        
        # Engine should detect the hallucination, consult Bob (RLHF), and correct the output
        assert isinstance(result, FizzBuzzResult)
        assert result.output == "Fizz"
        
        # Verify RLHF was triggered
        mock_rlhf.assert_called_once()
        # Verify LLM might have been asked twice (initial + correction) or RLHF handled it
        assert mock_llm.generate.call_count >= 1
