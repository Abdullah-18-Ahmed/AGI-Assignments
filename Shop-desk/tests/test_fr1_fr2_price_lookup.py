import pytest
from shop_desk.agents.price_lookup import handle_price_lookup, handle_stock_check, handle_detail_lookup
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


@pytest.mark.asyncio
async def test_fr1_price_lookup_valid_sku(context: ShopContext):
    with with_context(context):
        result = await handle_price_lookup("ANE-EK-001", context)
    
    assert result.ok is True
    assert "ANE-EK-001" in result.data
    assert "Electric Kettle 1.7L" in result.data
    assert "4200" in result.data or "4,200" in result.data


@pytest.mark.asyncio
async def test_fr1_price_lookup_invalid_sku(context: ShopContext):
    with with_context(context):
        result = await handle_price_lookup("INVALID-SKU", context)
    
    assert result.ok is False
    assert result.error.code == "NOT_FOUND"


@pytest.mark.asyncio
async def test_fr2_stock_check_available(context: ShopContext):
    with with_context(context):
        result = await handle_stock_check("ANE-EK-001", context)
    
    assert result.ok is True
    assert "ANE-EK-001" in result.data
    assert "12" in result.data


@pytest.mark.asyncio
async def test_fr2_stock_check_out_of_stock(context: ShopContext):
    with with_context(context):
        result = await handle_stock_check("ANE-PF-002", context)
    
    assert result.ok is True
    assert "ANE-PF-002" in result.data
    assert "out of stock" in result.data.lower()


@pytest.mark.asyncio
async def test_fr2_stock_check_invalid_sku(context: ShopContext):
    with with_context(context):
        result = await handle_stock_check("INVALID-SKU", context)
    
    assert result.ok is False
    assert result.error.code == "NOT_FOUND"


@pytest.mark.asyncio
async def test_fr8_detail_lookup(context: ShopContext):
    with with_context(context):
        result = await handle_detail_lookup("ANE-EK-001", context)
    
    assert result.ok is True
    assert "ANE-EK-001" in result.data
    assert "Electric Kettle 1.7L" in result.data
    assert "4200" in result.data or "4,200" in result.data
    assert "12" in result.data
    assert "kitchen" in result.data.lower()