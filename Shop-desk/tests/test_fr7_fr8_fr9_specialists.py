import pytest
from copy import deepcopy

from shop_desk.agents.base_config import (
    BaseAgentConfig,
    AgentTool,
    PricingQuery,
    PricingResult,
    EscalationQuery,
    EscalationResult,
)
from shop_desk.agents.specialists import (
    PRICING_SPECIALIST_CONFIG,
    ESCALATION_SPECIALIST_CONFIG,
    BASE_SPECIALIST_CONFIG,
    PricingSpecialistAgent,
    EscalationSpecialistAgent,
    PricingSpecialistTool,
    EscalationSpecialistTool,
    pricing_specialist,
    escalation_specialist,
    pricing_specialist_tool,
    escalation_specialist_tool,
    handle_pricing_query,
    handle_escalation,
    make_catalogue_tool,
    make_validate_order_tool,
)
from shop_desk.models import EscalationReason
from shop_desk.models.shop import ShopContext, Tier, Path
from shop_desk.context import with_context
from shop_desk.tools import create_session


@pytest.fixture
def walk_in_context():
    ctx = create_session(
        session_id="test-walk-in",
        shop="Al-Noor Electronics",
        currency="PKR",
        customer_id="walk-in-customer",
        tier="walk_in",
        catalogue_version="1.0.0",
    )
    return ctx


@pytest.fixture
def regular_context():
    ctx = create_session(
        session_id="test-regular",
        shop="Al-Noor Electronics",
        currency="PKR",
        customer_id="regular-customer",
        tier="regular",
        catalogue_version="1.0.0",
    )
    return ctx


class TestFR7TieredTools:
    """Tests for FR-7: Tiered tools - static and dynamic tool exposure."""

    def test_base_config_has_catalogue_tools(self):
        """Base config should have catalogue tools for walk_in tier."""
        tools = BASE_SPECIALIST_CONFIG.filter_tools_by_tier("walk_in")
        tool_names = [t.name for t in tools]
        assert "catalogue_lookup" in tool_names
        assert "multi_catalogue_lookup" in tool_names
        assert "validate_order" not in tool_names  # Regular tier only

    def test_base_config_regular_tier_gets_validate_order(self):
        """Regular tier should get validate_order tool."""
        tools = BASE_SPECIALIST_CONFIG.filter_tools_by_tier("regular")
        tool_names = [t.name for t in tools]
        assert "validate_order" in tool_names

    def test_pricing_specialist_config_has_validate_order(self):
        """Pricing specialist config should include validate_order."""
        tools = PRICING_SPECIALIST_CONFIG.tools
        tool_names = [t.name for t in tools]
        assert "validate_order" in tool_names
        assert "catalogue_lookup" in tool_names

    def test_escalation_specialist_config_no_catalogue_tools(self):
        """Escalation specialist should have no catalogue tools."""
        tools = ESCALATION_SPECIALIST_CONFIG.tools
        assert len(tools) == 0

    def test_seasonal_tools_excluded(self):
        """Seasonal tools should be excluded from all tiers."""
        seasonal_tool = AgentTool(
            name="seasonal_promo",
            description="Seasonal promotion tool",
            func=lambda: None,
            parameters_schema={},
            seasonal=True,
        )
        config = BASE_SPECIALIST_CONFIG.with_tools(seasonal_tool)
        
        walk_in_tools = config.filter_tools_by_tier("walk_in")
        regular_tools = config.filter_tools_by_tier("regular")
        
        seasonal_names = [t.name for t in walk_in_tools] + [t.name for t in regular_tools]
        assert "seasonal_promo" not in seasonal_names

    def test_tool_tier_required_walk_in(self):
        """Tools with tier_required='walk_in' available to both tiers."""
        tool = make_catalogue_tool()
        assert tool.tier_required == "walk_in"
        
        walk_in_tools = BASE_SPECIALIST_CONFIG.filter_tools_by_tier("walk_in")
        regular_tools = BASE_SPECIALIST_CONFIG.filter_tools_by_tier("regular")
        
        assert any(t.name == "catalogue_lookup" for t in walk_in_tools)
        assert any(t.name == "catalogue_lookup" for t in regular_tools)

    def test_tool_tier_required_regular(self):
        """Tools with tier_required='regular' only available to regular tier."""
        tool = make_validate_order_tool()
        assert tool.tier_required == "regular"
        
        walk_in_tools = BASE_SPECIALIST_CONFIG.filter_tools_by_tier("walk_in")
        regular_tools = BASE_SPECIALIST_CONFIG.filter_tools_by_tier("regular")
        
        assert not any(t.name == "validate_order" for t in walk_in_tools)
        assert any(t.name == "validate_order" for t in regular_tools)


class TestFR9BaseAgentCloning:
    """Tests for FR-9: Base agent configuration cloning and separation."""

    def test_base_config_clone_creates_new_instance(self):
        """Cloning should create a new independent instance."""
        cloned = BASE_SPECIALIST_CONFIG.clone(name="ClonedAgent")
        
        assert cloned is not BASE_SPECIALIST_CONFIG
        assert cloned.name == "ClonedAgent"
        assert cloned.model == BASE_SPECIALIST_CONFIG.model
        assert cloned.path == BASE_SPECIALIST_CONFIG.path

    def test_clone_overrides_only_specified_fields(self):
        """Clone should only override specified fields."""
        cloned = BASE_SPECIALIST_CONFIG.clone(
            name="CustomAgent",
            model="openai/gpt-4o",
            instructions="Custom instructions",
        )
        
        assert cloned.name == "CustomAgent"
        assert cloned.model == "openai/gpt-4o"
        assert cloned.instructions == "Custom instructions"
        assert cloned.path == BASE_SPECIALIST_CONFIG.path
        assert cloned.max_turns == BASE_SPECIALIST_CONFIG.max_turns

    def test_clone_tools_are_deep_copied(self):
        """Cloned tools should be independent (deep copy)."""
        cloned = BASE_SPECIALIST_CONFIG.clone()
        
        # Modify original
        BASE_SPECIALIST_CONFIG.tools.append(AgentTool(
            name="test_tool",
            description="Test",
            func=lambda: None,
            parameters_schema={},
        ))
        
        # Cloned should not have the new tool
        assert "test_tool" not in [t.name for t in cloned.tools]
        assert "test_tool" in [t.name for t in BASE_SPECIALIST_CONFIG.tools]

    def test_pricing_specialist_is_independent_from_base(self):
        """Pricing specialist config should be independent from base."""
        assert PRICING_SPECIALIST_CONFIG is not BASE_SPECIALIST_CONFIG
        assert PRICING_SPECIALIST_CONFIG.model == "openai/gpt-4o"
        assert BASE_SPECIALIST_CONFIG.model == "openai/gpt-4o-mini"
        
        # Modify base shouldn't affect pricing
        BASE_SPECIALIST_CONFIG.tools.append(AgentTool(
            name="base_only",
            description="Base only",
            func=lambda: None,
            parameters_schema={},
        ))
        
        base_tool_names = [t.name for t in BASE_SPECIALIST_CONFIG.tools]
        pricing_tool_names = [t.name for t in PRICING_SPECIALIST_CONFIG.tools]
        
        assert "base_only" in base_tool_names
        assert "base_only" not in pricing_tool_names

    def test_escalation_specialist_is_independent_from_base(self):
        """Escalation specialist config should be independent from base."""
        assert ESCALATION_SPECIALIST_CONFIG is not BASE_SPECIALIST_CONFIG
        assert ESCALATION_SPECIALIST_CONFIG.model == "openai/gpt-4o-mini"
        assert len(ESCALATION_SPECIALIST_CONFIG.tools) == 0
        
        # Modify base shouldn't affect escalation
        BASE_SPECIALIST_CONFIG.tools.append(AgentTool(
            name="base_only_2",
            description="Base only",
            func=lambda: None,
            parameters_schema={},
        ))
        
        assert "base_only_2" not in [t.name for t in ESCALATION_SPECIALIST_CONFIG.tools]

    def test_pricing_and_escalation_are_separate_instances(self):
        """Pricing and escalation specialists should be separate objects."""
        assert PRICING_SPECIALIST_CONFIG is not ESCALATION_SPECIALIST_CONFIG
        assert PRICING_SPECIALIST_CONFIG.model == "openai/gpt-4o"
        assert ESCALATION_SPECIALIST_CONFIG.model == "openai/gpt-4o-mini"
        assert PRICING_SPECIALIST_CONFIG.max_turns == 15
        assert ESCALATION_SPECIALIST_CONFIG.max_turns == 5

    def test_agent_instances_are_separate(self):
        """Agent instances should be separate objects (but share config by design)."""
        pricing1 = PricingSpecialistAgent()
        pricing2 = PricingSpecialistAgent()
        
        assert pricing1 is not pricing2
        # Agents share the same config object by design (singleton config pattern)
        assert pricing1.config is pricing2.config
        assert pricing1.config is PRICING_SPECIALIST_CONFIG
        assert pricing2.config is PRICING_SPECIALIST_CONFIG

    def test_agent_config_identity_preserved(self):
        """Agent should preserve config identity."""
        agent = PricingSpecialistAgent()
        assert agent.config is PRICING_SPECIALIST_CONFIG
        
        escalation = EscalationSpecialistAgent()
        assert escalation.config is ESCALATION_SPECIALIST_CONFIG


class TestFR8PricingSpecialistToolAndTurnBudget:
    """Tests for FR-8: Pricing Specialist tool & turn budget."""

    @pytest.mark.asyncio
    async def test_pricing_specialist_returns_exact_numerical_values(self, walk_in_context):
        """Pricing specialist should return exact numerical pricing."""
        with with_context(walk_in_context):
            result = await handle_pricing_query("ANE-EK-001", walk_in_context, quantity=2)
        
        assert result.ok is True
        pricing: PricingResult = result.data
        assert pricing.unit_price == 4200  # Exact catalogue price
        assert pricing.quantity == 2
        assert pricing.line_total == 8400  # 4200 * 2
        assert isinstance(pricing.line_total, int)

    @pytest.mark.asyncio
    async def test_pricing_specialist_with_tax_and_shipping(self, walk_in_context):
        """Pricing specialist should compute tax and shipping correctly."""
        with with_context(walk_in_context):
            result = await handle_pricing_query(
                "ANE-EK-001", 
                walk_in_context, 
                quantity=1,
                include_tax=True,
                include_shipping=True,
            )
        
        assert result.ok is True
        pricing: PricingResult = result.data
        assert pricing.unit_price == 4200
        assert pricing.tax == 756  # 4200 * 0.18
        assert pricing.shipping == 500  # Under 50k threshold
        assert pricing.grand_total == 5456  # 4200 + 756 + 500

    @pytest.mark.asyncio
    async def test_pricing_specialist_free_shipping_over_threshold(self, walk_in_context):
        """Pricing specialist should give free shipping over 50k."""
        with with_context(walk_in_context):
            result = await handle_pricing_query(
                "ANE-RF-012",  # 58000
                walk_in_context, 
                quantity=1,
                include_tax=True,
                include_shipping=True,
            )
        
        assert result.ok is True
        pricing: PricingResult = result.data
        assert pricing.unit_price == 58000
        assert pricing.shipping == 0  # Free shipping over 50k
        assert pricing.grand_total == 58000 + int(58000 * 0.18)

    @pytest.mark.asyncio
    async def test_pricing_specialist_invalid_sku(self, walk_in_context):
        """Pricing specialist should reject invalid SKU."""
        with with_context(walk_in_context):
            result = await handle_pricing_query("INVALID-SKU", walk_in_context)
        
        assert result.ok is False
        assert result.error.code == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_pricing_specialist_tool_returns_structured_result(self, walk_in_context):
        """Pricing specialist tool should return PricingResult object."""
        with with_context(walk_in_context):
            result = await pricing_specialist_tool(
                PricingQuery(sku="ANE-EK-001", quantity=3),
                walk_in_context,
            )
        
        assert isinstance(result, PricingResult)
        assert result.sku == "ANE-EK-001"
        assert result.quantity == 3
        assert result.line_total == 12600

    @pytest.mark.asyncio
    async def test_turn_budget_enforced(self, walk_in_context):
        """Pricing specialist should enforce turn budget (max_turns=15)."""
        # Create context with high turn count
        walk_in_context.turn_count = 15
        
        with with_context(walk_in_context):
            result = await handle_pricing_query("ANE-EK-001", walk_in_context)
        
        assert result.ok is False
        assert result.error.code == "TURN_LIMIT_EXCEEDED"
        assert "maximum number of steps" in result.error.message.lower()

    @pytest.mark.asyncio
    async def test_turn_budget_polite_fallback(self, walk_in_context):
        """Turn limit should return polite fallback message."""
        walk_in_context.turn_count = 15
        
        with with_context(walk_in_context):
            result = await handle_pricing_query("ANE-EK-001", walk_in_context)
        
        assert result.ok is False
        assert "connect you with a specialist" in result.error.message.lower()
        assert "rephrasing" in result.error.message.lower()

    @pytest.mark.asyncio
    async def test_escalation_specialist_returns_structured_result(self, walk_in_context):
        """Escalation specialist should return structured EscalationResult."""
        with with_context(walk_in_context):
            result = await handle_escalation(
                EscalationReason.DISPUTE,
                walk_in_context,
                "Customer bought kettle, arrived damaged",
            )
        
        assert result.ok is True
        escalation: EscalationResult = result.data
        assert escalation.escalated is True
        assert escalation.case_id.startswith("ESC-")
        assert "24 hours" in escalation.estimated_response_time  # walk_in tier

    @pytest.mark.asyncio
    async def test_escalation_regular_tier_faster_response(self, regular_context):
        """Regular tier should get faster escalation response."""
        with with_context(regular_context):
            result = await handle_escalation(
                EscalationReason.DISPUTE,
                regular_context,
            )
        
        assert result.ok is True
        escalation: EscalationResult = result.data
        assert "2 hours" in escalation.estimated_response_time

    @pytest.mark.asyncio
    async def test_escalation_turn_budget(self, walk_in_context):
        """Escalation specialist should enforce its turn budget (max_turns=5)."""
        walk_in_context.turn_count = 5
        
        with with_context(walk_in_context):
            result = await handle_escalation(
                EscalationReason.TURN_LIMIT_REACHED,
                walk_in_context,
            )
        
        assert result.ok is False
        assert result.error.code == "TURN_LIMIT_EXCEEDED"

    def test_pricing_specialist_model_is_gpt4o(self):
        """Pricing specialist should use gpt-4o model."""
        assert PRICING_SPECIALIST_CONFIG.model == "openai/gpt-4o"
        assert pricing_specialist.model == "openai/gpt-4o"

    def test_escalation_specialist_model_is_gpt4o_mini(self):
        """Escalation specialist should use gpt-4o-mini model."""
        assert ESCALATION_SPECIALIST_CONFIG.model == "openai/gpt-4o-mini"
        assert escalation_specialist.model == "openai/gpt-4o-mini"

    def test_pricing_specialist_higher_turn_budget(self):
        """Pricing specialist should have higher turn budget than escalation."""
        assert PRICING_SPECIALIST_CONFIG.max_turns == 15
        assert ESCALATION_SPECIALIST_CONFIG.max_turns == 5
        assert pricing_specialist.max_turns == 15
        assert escalation_specialist.max_turns == 5


class TestConfigWithTools:
    """Tests for config tool manipulation."""

    def test_with_tools_adds_tools(self):
        """with_tools should add tools to config."""
        custom_tool = AgentTool(
            name="custom",
            description="Custom tool",
            func=lambda: None,
            parameters_schema={},
        )
        config = BASE_SPECIALIST_CONFIG.with_tools(custom_tool)
        
        assert "custom" in [t.name for t in config.tools]
        assert len(config.tools) == len(BASE_SPECIALIST_CONFIG.tools) + 1

    def test_without_tools_removes_tools(self):
        """without_tools should remove tools from config."""
        config = BASE_SPECIALIST_CONFIG.without_tools("catalogue_lookup")
        
        assert "catalogue_lookup" not in [t.name for t in config.tools]
        assert len(config.tools) == len(BASE_SPECIALIST_CONFIG.tools) - 1

    def test_without_tools_multiple(self):
        """without_tools should handle multiple tool names."""
        # Create a fresh config for this test
        config = BaseAgentConfig(
            name="TestConfig",
            model="openai/gpt-4o-mini",
            path=Path.FAST,
            instructions="Test",
            tools=[
                AgentTool(name="catalogue_lookup", description="Test", func=lambda: None, parameters_schema={}),
                AgentTool(name="multi_catalogue_lookup", description="Test", func=lambda: None, parameters_schema={}),
                AgentTool(name="validate_order", description="Test", func=lambda: None, parameters_schema={}),
            ],
            max_turns=5,
        )
        config = config.without_tools("catalogue_lookup", "multi_catalogue_lookup")
        
        assert "catalogue_lookup" not in [t.name for t in config.tools]
        assert "multi_catalogue_lookup" not in [t.name for t in config.tools]
        assert len(config.tools) == 1  # Only validate_order remains

    def test_original_config_unchanged_by_with_tools(self):
        """Original config should be unchanged by with_tools."""
        original_count = len(BASE_SPECIALIST_CONFIG.tools)
        BASE_SPECIALIST_CONFIG.with_tools(AgentTool(
            name="temp", description="Temp", func=lambda: None, parameters_schema={}
        ))
        
        assert len(BASE_SPECIALIST_CONFIG.tools) == original_count