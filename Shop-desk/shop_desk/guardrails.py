from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from shop_desk.models.shop import CatalogueEntry
import shop_desk.tools.catalogue as catalogue_module


@dataclass
class GuardrailResult:
    passed: bool
    corrected_response: Optional[str] = None
    violations: list[str] = None

    def __post_init__(self):
        if self.violations is None:
            self.violations = []


# SKU pattern: ANE-XX-XXX (e.g., ANE-EK-001)
SKU_PATTERN = re.compile(r'ANE-[A-Z]{2}-\d{3}', re.IGNORECASE)

# Price pattern: Must have currency prefix/suffix and capture the full number
# Matches: "PKR 4,200", "PKR 4200", "Rs 4200", "Rs. 4,200", "4,200 PKR", "4200 PKR", etc.
# Uses \d+ to match the full number (not limited to 1-3 digits)
# We'll filter out SKU-like matches (numbers < 100) in the extraction logic
PRICE_PATTERN = re.compile(
    r'(?:PKR|Rs\.?)\s*(\d+(?:,\d{3})*(?:\.\d{2})?)'
    r'|(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:PKR|Rs\.?)',
    re.IGNORECASE
)

# Orphan price pattern - same but for standalone price detection
ORPHAN_PRICE_PATTERN = re.compile(
    r'(?:PKR|Rs\.?)\s*(\d+(?:,\d{3})*(?:\.\d{2})?)'
    r'|(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:PKR|Rs\.?)',
    re.IGNORECASE
)

# Minimum valid price (all catalogue items are >= 1200)
MIN_VALID_PRICE = 100


def _get_catalogue_cache() -> dict[str, CatalogueEntry]:
    """Get the catalogue cache, loading if necessary."""
    catalogue_module._ensure_loaded()
    return catalogue_module._CATALOGUE_CACHE


class CatalogueGuardrail:
    """Output guardrail that validates all prices and SKUs in LLM responses against catalogue.json."""

    def __init__(self):
        self._catalogue_cache: dict[str, CatalogueEntry] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self._catalogue_cache = _get_catalogue_cache()
            self._loaded = True

    def get_entry(self, sku: str) -> Optional[CatalogueEntry]:
        self._ensure_loaded()
        return self._catalogue_cache.get(sku.upper())

    def validate_sku_exists(self, sku: str) -> tuple[bool, Optional[str]]:
        self._ensure_loaded()
        sku_upper = sku.upper()
        if sku_upper not in self._catalogue_cache:
            return False, f"SKU {sku} not found in catalogue"
        return True, None

    def validate_price(self, sku: str, price: int) -> tuple[bool, Optional[str]]:
        self._ensure_loaded()
        entry = self._catalogue_cache.get(sku.upper())
        if not entry:
            return False, f"SKU {sku} not found in catalogue"
        if entry.price != price:
            return False, f"Price mismatch for {sku}: catalogue has {entry.price}, response has {price}"
        return True, None

    def validate_stock_available(self, sku: str) -> tuple[bool, Optional[str]]:
        self._ensure_loaded()
        entry = self._catalogue_cache.get(sku.upper())
        if not entry:
            return False, f"SKU {sku} not found in catalogue"
        if entry.stock <= 0:
            return False, f"SKU {sku} is out of stock (stock: {entry.stock})"
        return True, None

    def extract_skus_and_prices(self, text: str) -> list[tuple[str, Optional[int]]]:
        """Extract all SKU-price pairs from text. Returns list of (sku, price) tuples."""
        self._ensure_loaded()
        results = []
        
        # Find all SKUs in text
        skus_found = SKU_PATTERN.findall(text.upper())
        
        for sku in skus_found:
            # Look for price near this SKU
            sku_pos = text.upper().find(sku)
            # Search for price within 200 chars after SKU
            context = text[sku_pos:sku_pos + 200]
            price_match = PRICE_PATTERN.search(context)
            price = None
            if price_match:
                # Get the first non-None group
                price_str = None
                for g in price_match.groups():
                    if g is not None:
                        price_str = g
                        break
                if price_str:
                    price_str = price_str.replace(",", "")
                    try:
                        price_val = int(float(price_str))
                        # Filter out SKU-like numbers (e.g., "001" from ANE-EK-001)
                        if price_val >= MIN_VALID_PRICE:
                            price = price_val
                    except ValueError:
                        pass
            results.append((sku, price))
        
        return results

    def check_response(self, response: str) -> GuardrailResult:
        """
        Check a response for guardrail violations.
        Returns GuardrailResult with corrected response if needed.
        """
        self._ensure_loaded()
        violations = []
        
        # Extract all SKU-price mentions
        sku_price_pairs = self.extract_skus_and_prices(response)
        
        corrected = response
        
        for sku, price in sku_price_pairs:
            # Validate SKU exists
            sku_ok, sku_err = self.validate_sku_exists(sku)
            if not sku_ok:
                violations.append(sku_err)
                # Mark the hallucinated SKU in response
                corrected = corrected.replace(sku, f"[INVALID SKU: {sku}]")
                continue
            
            # Validate price if present
            if price is not None:
                price_ok, price_err = self.validate_price(sku, price)
                if not price_ok:
                    violations.append(price_err)
                    # Correct the price in response
                    correct_price = self._catalogue_cache[sku.upper()].price
                    corrected = self._replace_price_near_sku(corrected, sku, price, correct_price)
            
            # Validate stock availability (warn but don't block)
            stock_ok, stock_err = self.validate_stock_available(sku)
            if not stock_ok:
                violations.append(f"WARNING: {stock_err}")
        
        # Check for orphan prices (prices without valid SKU nearby)
        all_prices = ORPHAN_PRICE_PATTERN.findall(response)
        for price_match in all_prices:
            price_str = None
            for g in price_match:
                if g is not None:
                    price_str = g
                    break
            if price_str:
                price_val = int(float(price_str.replace(",", "")))
                # Only flag as orphan if it's a plausible product price (>= MIN_VALID_PRICE)
                if price_val >= MIN_VALID_PRICE:
                    # Check if this price matches any catalogue item
                    matching_skus = [sku for sku, entry in self._catalogue_cache.items() if entry.price == price_val]
                    if not matching_skus:
                        violations.append(f"WARNING: Price {price_val} not found in catalogue (orphan price)")
        
        # Only consider non-WARNING violations as failures
        errors = [v for v in violations if not v.startswith("WARNING")]
        passed = len(errors) == 0
        
        return GuardrailResult(
            passed=passed,
            corrected_response=corrected if not passed else None,
            violations=violations
        )

    def _replace_price_near_sku(self, text: str, sku: str, old_price: int, new_price: int) -> str:
        """Replace a specific price near a SKU with the correct price."""
        sku_pos = text.upper().find(sku.upper())
        if sku_pos == -1:
            return text
        
        # Search in a window around the SKU
        start = max(0, sku_pos - 50)
        end = min(len(text), sku_pos + 200)
        window = text[start:end]
        
        old_price_str = f"{old_price:,}"
        new_price_str = f"{new_price:,}"
        
        # Try to replace in the window
        if old_price_str in window:
            new_window = window.replace(old_price_str, new_price_str, 1)
            return text[:start] + new_window + text[end:]
        
        # Try without comma
        old_price_str_nc = str(old_price)
        if old_price_str_nc in window:
            new_window = window.replace(old_price_str_nc, new_price_str, 1)
            return text[:start] + new_window + text[end:]
        
        return text

    def format_polite_refusal(self, violations: list[str]) -> str:
        """Convert guardrail violations into polite customer-facing messages."""
        messages = []
        for v in violations:
            if v.startswith("WARNING:"):
                continue  # Don't show warnings to customers
            if "not found in catalogue" in v:
                messages.append("I apologize, but that product doesn't appear in our current catalogue.")
            elif "Price mismatch" in v:
                messages.append("I notice there was an error in the pricing. Let me provide the correct price from our catalogue.")
            elif "out of stock" in v:
                messages.append("That item is currently out of stock.")
            else:
                messages.append("I need to verify that information with our catalogue.")
        
        if not messages:
            return "Let me check that for you."
        
        return " ".join(messages)


# Global instance
_guardrail = CatalogueGuardrail()


def validate_response(response: str) -> GuardrailResult:
    """Validate an LLM response against catalogue."""
    return _guardrail.check_response(response)


def get_polite_refusal(violations: list[str]) -> str:
    """Get polite customer message for violations."""
    return _guardrail.format_polite_refusal(violations)


def validate_order_items(items: list[dict]) -> tuple[bool, list[str]]:
    """Validate order items against catalogue before creating order."""
    catalogue = _get_catalogue_cache()
    violations = []
    
    for item in items:
        sku = item.get("sku", "").upper()
        qty = item.get("quantity", 1)
        price = item.get("unit_price")
        
        if not sku:
            violations.append("Missing SKU in order item")
            continue
            
        entry = catalogue.get(sku)
        if not entry:
            violations.append(f"SKU {sku} not found in catalogue")
            continue
            
        if entry.stock < qty:
            violations.append(f"Insufficient stock for {sku}: requested {qty}, available {entry.stock}")
            
        if price is not None and entry.price != price:
            violations.append(f"Price mismatch for {sku}: catalogue {entry.price}, provided {price}")
    
    return len(violations) == 0, violations


def force_reload_catalogue() -> None:
    """Force reload the catalogue cache. Useful for tests."""
    global _guardrail
    _guardrail._loaded = False
    _guardrail._catalogue_cache = {}
    # This will trigger reload on next use