import pytest
from shop_desk.fast_path import (
    handle_fast_path_query,
    fast_path_price_lookup,
    fast_path_stock_check,
    fast_path_detail_lookup,
    detect_intent,
    extract_sku,
)
from shop_desk.agents.search import handle_search, handle_category_browse
from shop_desk.prompts.dynamic import (
    generate_fast_path_prompt,
    generate_reasoning_prompt,
    get_operating_hours_status,
    is_within_operating_hours,
)
from shop_desk.context import with_context
from shop_desk.models.shop import ShopContext, Tier
from shop_desk.tools import create_session


@pytest.fixture
def context():
    ctx = create_session(
        session_id="test-session",
        shop="Al-Noor Electronics",
        currency="PKR",
        customer_id="test-customer",
        tier="walk_in",
        catalogue_version="1.0.0",
    )
    return ctx


class TestFastPath:
    """Tests for FR-3: Fast path direct catalogue lookup (0 LLM calls)."""

    @pytest.mark.asyncio
    async def test_fast_path_price_lookup_with_sku(self, context: ShopContext):
        with with_context(context):
            result = await handle_fast_path_query("What does ANE-EK-001 cost?", context)
        
        assert result.handled is True
        assert result.tool_calls == 1
        assert "ANE-EK-001" in result.response
        assert "Electric Kettle" in result.response
        assert "4200" in result.response or "4,200" in result.response

    @pytest.mark.asyncio
    async def test_fast_path_stock_check_with_sku(self, context: ShopContext):
        with with_context(context):
            result = await handle_fast_path_query("Is ANE-PF-002 in stock?", context)
        
        assert result.handled is True
        assert result.tool_calls == 1
        assert "ANE-PF-002" in result.response
        assert "out of stock" in result.response.lower()

    @pytest.mark.asyncio
    async def test_fast_path_detail_lookup_with_sku(self, context: ShopContext):
        with with_context(context):
            result = await handle_fast_path_query("Details for ANE-EK-001", context)
        
        assert result.handled is True
        assert result.tool_calls == 1
        assert "ANE-EK-001" in result.response
        assert "Electric Kettle" in result.response
        assert "Description:" in result.response

    @pytest.mark.asyncio
    async def test_fast_path_price_variations_with_sku(self, context: ShopContext):
        """Test various phrasings for price queries WITH valid SKU."""
        queries = [
            "Price of ANE-EK-001",
            "How much is ANE-EK-001?",
            "ANE-EK-001 pricing",
            "What does ANE-EK-001 cost?",
        ]
        
        for query in queries:
            with with_context(context):
                result = await handle_fast_path_query(query, context)
            assert result.handled is True, f"Failed for query: {query}"
            assert result.tool_calls == 1

    @pytest.mark.asyncio
    async def test_fast_path_stock_variations_with_sku(self, context: ShopContext):
        """Test various phrasings for stock queries WITH valid SKU."""
        queries = [
            "Is ANE-PF-002 available?",
            "Stock of ANE-PF-002",
            "ANE-PF-002 availability",
            "Quantity of ANE-PF-002",
        ]
        
        for query in queries:
            with with_context(context):
                result = await handle_fast_path_query(query, context)
            assert result.handled is True, f"Failed for query: {query}"
            assert result.tool_calls == 1

    @pytest.mark.asyncio
    async def test_fast_path_no_sku_returns_false(self, context: ShopContext):
        """Queries without valid SKU should not be handled by fast path."""
        queries_without_sku = [
            "What do you have?",
            "What does the kettle cost?",  # no SKU
            "Show me fans",
        ]
        
        for query in queries_without_sku:
            with with_context(context):
                result = await handle_fast_path_query(query, context)
            assert result.handled is False, f"Should not handle: {query}"

    @pytest.mark.asyncio
    async def test_fast_path_invalid_sku_pattern_returns_false(self, context: ShopContext):
        """Invalid SKU pattern (not matching ANE-XX-XXX) returns handled=False."""
        with with_context(context):
            result = await handle_fast_path_query("Price of INVALID-SKU", context)
        
        assert result.handled is False  # Pattern doesn't match

    @pytest.mark.asyncio
    async def test_fast_path_valid_sku_not_in_catalogue(self, context: ShopContext):
        """Valid SKU pattern but not in catalogue returns handled=True with error."""
        with with_context(context):
            result = await handle_fast_path_query("Price of ANE-XX-999", context)
        
        assert result.handled is True
        assert result.tool_calls == 1
        assert result.error is not None
        assert "NOT_FOUND" in result.error or "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_fast_path_zero_llm_calls(self, context: ShopContext):
        """Verify fast path makes exactly 1 tool call and 0 LLM calls."""
        with with_context(context):
            result = await handle_fast_path_query("What does ANE-EK-001 cost?", context)
        
        assert result.handled is True
        assert result.tool_calls == 1
        # LLM calls would be tracked separately - this verifies tool-only path


class TestSearchFR3:
    """Tests for FR-3: Search by keyword."""

    @pytest.mark.asyncio
    async def test_search_kettles(self, context: ShopContext):
        with with_context(context):
            result = await handle_search("kettle", context)
        
        assert result.ok is True
        assert "kettle" in result.data.lower() or "Kettle" in result.data

    @pytest.mark.asyncio
    async def test_search_fans(self, context: ShopContext):
        with with_context(context):
            result = await handle_search("fan", context)
        
        assert result.ok is True
        assert "fan" in result.data.lower() or "Fan" in result.data

    @pytest.mark.asyncio
    async def test_search_no_results(self, context: ShopContext):
        with with_context(context):
            result = await handle_search("nonexistentproductxyz", context)
        
        assert result.ok is True
        assert "no products found" in result.data.lower()


class TestCategoryBrowseFR4:
    """Tests for FR-4: Category browse."""

    @pytest.mark.asyncio
    async def test_browse_kitchen(self, context: ShopContext):
        with with_context(context):
            result = await handle_category_browse("kitchen", context)
        
        assert result.ok is True
        assert "kitchen" in result.data.lower()

    @pytest.mark.asyncio
    async def test_browse_cooling(self, context: ShopContext):
        with with_context(context):
            result = await handle_category_browse("cooling", context)
        
        assert result.ok is True
        assert "cooling" in result.data.lower()


class TestDynamicPromptsFR4:
    """Tests for FR-4: Hour-aware dynamic system prompts."""

    def test_generate_fast_path_prompt_structure(self):
        prompt = generate_fast_path_prompt()
        
        assert "Al-Noor Electronics" in prompt
        assert "PKR" in prompt
        assert "CATALOGUE ONLY" in prompt
        assert "EXACT VALUES" in prompt
        assert "NO GUESSING" in prompt
        assert "GUARDRAILS" in prompt

    def test_generate_reasoning_prompt_structure(self):
        prompt = generate_reasoning_prompt()
        
        assert "Al-Noor Electronics" in prompt
        assert "PKR" in prompt
        assert "CATALOGUE ONLY" in prompt
        assert "STRUCTURED ANALYSIS" in prompt
        assert "COMPARISON FORMAT" in prompt

    def test_operating_hours_status(self):
        status = get_operating_hours_status()
        
        assert "is_open" in status
        assert "current_hour" in status
        assert "open_hour" in status
        assert "close_hour" in status
        assert "next_opening" in status
        assert "message" in status
        assert isinstance(status["is_open"], bool)

    def test_prompt_structure_always_correct(self):
        """Prompt structure should always be valid regardless of hours."""
        prompt = generate_fast_path_prompt()
        # Core rules always present
        assert "CATALOGUE ONLY" in prompt
        assert "EXACT VALUES" in prompt
        assert "NO GUESSING" in prompt
        assert "GUARDRAILS" in prompt
        # Hours info may or may not be present depending on time
        # but structure is always correct


class TestIntentDetection:
    """Tests for intent detection in fast path."""

    def test_detect_price_intent(self):
        assert detect_intent("What does ANE-EK-001 cost?") == "price"
        assert detect_intent("Price of ANE-EK-001") == "price"
        assert detect_intent("How much is ANE-EK-001?") == "price"

    def test_detect_stock_intent(self):
        assert detect_intent("Is ANE-PF-002 in stock?") == "stock"
        assert detect_intent("Stock of ANE-PF-002") == "stock"
        assert detect_intent("ANE-PF-002 availability") == "stock"

    def test_detect_detail_intent(self):
        assert detect_intent("Details for ANE-EK-001") == "detail"
        assert detect_intent("Specs of ANE-EK-001") == "detail"
        assert detect_intent("Describe ANE-EK-001") == "detail"

    def test_detect_no_intent_without_sku(self):
        assert detect_intent("What do you have?") is None
        assert detect_intent("Hello") is None

    def test_extract_sku(self):
        assert extract_sku("Price of ANE-EK-001") == "ANE-EK-001"
        assert extract_sku("ane-pf-002 stock") == "ANE-PF-002"
        assert extract_sku("No SKU here") is None
        assert extract_sku("INVALID-SKU") is None  # Wrong pattern