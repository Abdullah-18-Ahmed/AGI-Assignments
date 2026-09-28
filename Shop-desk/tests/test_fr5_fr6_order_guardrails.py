import pytest
from shop_desk.agents.quote import handle_quote, handle_order_confirm
from shop_desk.guardrails import (
    validate_response,
    validate_order_items,
    get_polite_refusal,
    CatalogueGuardrail,
)
from shop_desk.models.shop import LineItem, Order, OrderStatus
from shop_desk.context import with_context
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


class TestFR5TypedOrder:
    """Tests for FR-5: Typed Order with Python-side total computation."""

    def test_line_item_validates_line_total(self):
        """LineItem should validate that line_total = unit_price * quantity."""
        # Valid
        item = LineItem(sku="ANE-EK-001", name="Test", unit_price=100, quantity=2, line_total=200)
        assert item.line_total == 200
        
        # Invalid - should raise
        with pytest.raises(ValueError, match="line_total"):
            LineItem(sku="ANE-EK-001", name="Test", unit_price=100, quantity=2, line_total=300)

    def test_order_validates_totals(self):
        """Order should validate subtotal and grand_total."""
        items = [
            LineItem(sku="ANE-EK-001", name="Kettle", unit_price=4200, quantity=1, line_total=4200),
            LineItem(sku="ANE-HB-003", name="Blender", unit_price=3500, quantity=2, line_total=7000),
        ]
        # Valid order
        order = Order.create_from_items(items, tax=500, shipping=200)
        assert order.subtotal == 11200
        assert order.grand_total == 11900
        
        # Invalid subtotal
        with pytest.raises(ValueError, match="subtotal"):
            Order(
                items=items,
                subtotal=9999,  # wrong
                tax=500,
                shipping=200,
                grand_total=10699,
            )
        
        # Invalid grand_total
        with pytest.raises(ValueError, match="grand_total"):
            Order(
                items=items,
                subtotal=11200,
                tax=500,
                shipping=200,
                grand_total=9999,  # wrong
            )

    def test_order_create_from_items_computes_correctly(self):
        """Order.create_from_items should compute totals correctly."""
        items = [
            LineItem(sku="ANE-EK-001", name="Kettle", unit_price=4200, quantity=1, line_total=4200),
            LineItem(sku="ANE-HB-003", name="Blender", unit_price=3500, quantity=2, line_total=7000),
        ]
        order = Order.create_from_items(items, tax=560, shipping=200)  # 5% tax on 11200 = 560
        
        assert order.subtotal == 11200
        assert order.tax == 560
        assert order.shipping == 200
        assert order.grand_total == 11960
        assert order.status == OrderStatus.DRAFT
        assert order.order_id.startswith("ORD-")

    def test_order_id_generated_automatically(self):
        """Order ID should be auto-generated."""
        items = [LineItem(sku="ANE-EK-001", name="Kettle", unit_price=4200, quantity=1, line_total=4200)]
        order = Order.create_from_items(items)
        assert order.order_id.startswith("ORD-")
        assert len(order.order_id) > 4


class TestFR5QuoteAgent:
    """Tests for FR-5: Quote agent computes totals in Python."""

    @pytest.mark.asyncio
    async def test_quote_valid_items(self, context):
        """Quote with valid catalogue items should succeed."""
        with with_context(context):
            result = await handle_quote(
                items=[{"sku": "ANE-EK-001", "quantity": 1}, {"sku": "ANE-HB-003", "quantity": 2}],
                tax_rate=0.05,
                shipping_flat=200,
                context=context,
            )
        
        assert result.ok is True
        assert "Order Quote" in result.data
        assert "ANE-EK-001" in result.data
        assert "ANE-HB-003" in result.data
        assert "4200" in result.data or "4,200" in result.data
        assert "3500" in result.data or "3,500" in result.data
        assert "Grand Total" in result.data
        assert "Order ID" in result.data

    @pytest.mark.asyncio
    async def test_quote_invalid_sku_rejected(self, context):
        """Quote with invalid SKU should be rejected."""
        with with_context(context):
            result = await handle_quote(
                items=[{"sku": "INVALID-SKU", "quantity": 1}],
                context=context,
            )
        
        assert result.ok is False
        assert result.error.code == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_quote_insufficient_stock_rejected(self, context):
        """Quote requesting more than available stock should be rejected."""
        with with_context(context):
            result = await handle_quote(
                items=[{"sku": "ANE-RF-012", "quantity": 10}],  # Only 1 in stock
                context=context,
            )
        
        assert result.ok is False
        assert result.error.code == "VALIDATION_ERROR"
        assert "stock" in result.error.message.lower() or "insufficient" in result.error.message.lower()

    @pytest.mark.asyncio
    async def test_quote_price_mismatch_rejected(self, context):
        """Quote with price different from catalogue should be rejected."""
        with with_context(context):
            result = await handle_quote(
                items=[{"sku": "ANE-EK-001", "quantity": 1, "unit_price": 9999}],  # Wrong price
                context=context,
            )
        
        assert result.ok is False
        assert result.error.code == "VALIDATION_ERROR"
        assert "price" in result.error.message.lower() or "mismatch" in result.error.message.lower()

    @pytest.mark.asyncio
    async def test_quote_totals_computed_in_python(self, context):
        """Verify totals are computed in Python, not by LLM."""
        with with_context(context):
            result = await handle_quote(
                items=[{"sku": "ANE-EK-001", "quantity": 2}],  # 4200 * 2 = 8400
                tax_rate=0.10,  # 840
                shipping_flat=500,
                context=context,
            )
        
        assert result.ok is True
        # Python computes: subtotal=8400, tax=840, shipping=500, grand=9740
        assert "8400" in result.data or "8,400" in result.data  # subtotal
        assert "840" in result.data  # tax
        assert "500" in result.data  # shipping
        assert "9740" in result.data or "9,740" in result.data  # grand total


class TestFR6CatalogueGuardrail:
    """Tests for FR-6: Catalogue output guardrail."""

    def test_guardrail_passes_valid_response(self):
        """Valid response with correct catalogue prices should pass."""
        response = "SKU: ANE-EK-001 | Product: Electric Kettle 1.7L | Price: PKR 4,200"
        result = validate_response(response)
        assert result.passed is True

    def test_guardrail_catches_hallucinated_sku(self):
        """Response with non-existent SKU should be caught."""
        response = "SKU: ANE-XX-999 | Product: Fake Item | Price: PKR 9999"
        result = validate_response(response)
        assert result.passed is False
        assert any("not found" in v.lower() for v in result.violations)

    def test_guardrail_catches_price_mismatch(self):
        """Response with wrong price for valid SKU should be caught."""
        response = "SKU: ANE-EK-001 | Product: Electric Kettle 1.7L | Price: PKR 9999"
        result = validate_response(response)
        assert result.passed is False
        assert any("mismatch" in v.lower() for v in result.violations)

    def test_guardrail_catches_zero_stock_sale(self):
        """Response offering out-of-stock item should be warned."""
        response = "SKU: ANE-PF-002 | Product: Pedestal Fan 18 inch | Price: PKR 9,800 | In stock!"
        result = validate_response(response)
        # Should have warning about stock
        assert any("out of stock" in v.lower() or "stock" in v.lower() for v in result.violations)

    def test_guardrail_catches_orphan_price(self):
        """Price not matching any catalogue item should be warned."""
        response = "Total: PKR 12345"  # No catalogue item has this exact price
        result = validate_response(response)
        assert any("orphan" in v.lower() for v in result.violations)

    def test_guardrail_corrected_response(self):
        """Guardrail should provide corrected response for price mismatches."""
        response = "SKU: ANE-EK-001 | Price: PKR 9999"
        result = validate_response(response)
        assert result.passed is False
        assert result.corrected_response is not None
        assert "4,200" in result.corrected_response or "4200" in result.corrected_response

    def test_polite_refusal_messages(self):
        """Guardrail violations should produce polite customer messages."""
        violations = [
            "SKU ANE-XX-999 not found in catalogue",
            "Price mismatch for ANE-EK-001: catalogue has 4200, response has 9999",
        ]
        message = get_polite_refusal(violations)
        assert "apologize" in message.lower() or "sorry" in message.lower()
        assert "catalogue" in message.lower()

    def test_validate_order_items_valid(self):
        """Valid order items should pass validation."""
        items = [{"sku": "ANE-EK-001", "quantity": 1}, {"sku": "ANE-HB-003", "quantity": 2}]
        valid, violations = validate_order_items(items)
        assert valid is True
        assert len(violations) == 0

    def test_validate_order_items_invalid_sku(self):
        """Order with invalid SKU should fail."""
        items = [{"sku": "INVALID-SKU", "quantity": 1}]
        valid, violations = validate_order_items(items)
        assert valid is False
        assert any("not found" in v.lower() for v in violations)

    def test_validate_order_items_insufficient_stock(self):
        """Order exceeding stock should fail."""
        items = [{"sku": "ANE-RF-012", "quantity": 5}]  # Only 1 in stock
        valid, violations = validate_order_items(items)
        assert valid is False
        assert any("insufficient" in v.lower() or "stock" in v.lower() for v in violations)

    def test_validate_order_items_price_mismatch(self):
        """Order with wrong price should fail."""
        items = [{"sku": "ANE-EK-001", "quantity": 1, "unit_price": 9999}]
        valid, violations = validate_order_items(items)
        assert valid is False
        assert any("price mismatch" in v.lower() for v in violations)


class TestGuardrailIntegration:
    """Integration tests for guardrail with agents."""

    @pytest.mark.asyncio
    async def test_quote_output_guardrail_catches_errors(self, context):
        """Quote agent output should be guardrail-validated."""
        with with_context(context):
            result = await handle_quote(
                items=[{"sku": "ANE-EK-001", "quantity": 1}],
                context=context,
            )
        
        # The quote agent internally validates, so result should be clean
        assert result.ok is True
        # Verify the response contains correct catalogue price
        assert "4200" in result.data or "4,200" in result.data

    @pytest.mark.asyncio
    async def test_fake_edited_price_caught(self):
        """Test with deliberately fake edited price (simulating LLM hallucination)."""
        # Simulate an LLM response with a hallucinated price
        fake_response = "The Electric Kettle (ANE-EK-001) costs PKR 15000 which is a great deal!"
        result = validate_response(fake_response)
        
        assert result.passed is False
        assert any("mismatch" in v.lower() for v in result.violations)
        # Corrected response should have the right price
        assert result.corrected_response is not None
        assert "4200" in result.corrected_response or "4,200" in result.corrected_response


class TestGuardrailEdgeCases:
    """Edge cases for guardrail."""

    def test_multiple_skus_in_response(self):
        """Response with multiple SKUs should validate all."""
        response = "Kettle ANE-EK-001 PKR 4200, Fan ANE-PF-002 PKR 9800, Blender ANE-HB-003 PKR 3500"
        result = validate_response(response)
        assert result.passed is True

    def test_mixed_valid_invalid(self):
        """Response with mix of valid and invalid SKUs."""
        response = "Good: ANE-EK-001 PKR 4200. Bad: ANE-XX-999 PKR 9999"
        result = validate_response(response)
        assert result.passed is False
        assert any("not found" in v.lower() for v in result.violations)

    def test_case_insensitive_sku(self):
        """SKU matching should be case-insensitive."""
        response = "Price of ane-ek-001 is PKR 4200"
        result = validate_response(response)
        assert result.passed is True

    def test_price_formats(self):
        """Various price formats should be parsed."""
        formats = ["PKR 4,200", "PKR 4200", "Rs 4200", "Rs. 4,200", "4200 PKR"]
        for fmt in formats:
            response = f"ANE-EK-001 costs {fmt}"
            result = validate_response(response)
            # Should pass validation (correct price for valid SKU)
            assert result.passed is True, f"Failed for format: {fmt}"