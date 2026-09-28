from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List

from shop_desk.models.shop import HistoryEntry, ShopContext, Order, LineItem


@dataclass
class ActiveOrderState:
    """Tracks the current active order being built in the conversation."""
    order: Optional[Order] = None
    draft_items: List[LineItem] = field(default_factory=list)
    last_mentioned_skus: List[str] = field(default_factory=list)
    last_search_results: List[dict] = field(default_factory=list)
    awaiting_confirmation: bool = False


class HistoryManager:
    """Manages conversation history with trimming rules that preserve active order state."""
    
    MAX_HISTORY_TURNS = 10
    MAX_ESSENTIAL_TURNS = 6  # Minimum turns to keep (including active order context)
    
    def __init__(self, context: ShopContext):
        self.context = context
        self.active_order = ActiveOrderState()
    
    def add_user_message(self, content: str) -> None:
        """Add a user message to history."""
        entry = HistoryEntry(
            role="user",
            content=content,
            path=None,
            tokens=None,
            timestamp=__import__('time').time(),
        )
        self.context.history.append(entry)
        self.context.turn_count += 1
        self._trim_history()
    
    def add_assistant_message(
        self,
        content: str,
        path: Optional[str] = None,
        tokens: Optional[dict] = None,
    ) -> None:
        """Add an assistant message to history."""
        from shop_desk.models.shop import Path, TokenUsage
        
        entry = HistoryEntry(
            role="assistant",
            content=content,
            path=Path(path) if path else None,
            tokens=TokenUsage(**tokens) if tokens else None,
            timestamp=__import__('time').time(),
        )
        self.context.history.append(entry)
        # Don't increment turn_count for assistant messages (turn = user + assistant pair)
        self._trim_history()
    
    def _trim_history(self) -> None:
        """Trim history while preserving essential context.
        
        Rules:
        1. Keep at least MAX_ESSENTIAL_TURNS * 2 entries (user + assistant pairs)
        2. Always keep the active order state context
        3. Prefer removing oldest turns that don't reference the active order
        """
        max_entries = self.MAX_HISTORY_TURNS * 2  # user + assistant per turn
        essential_entries = self.MAX_ESSENTIAL_TURNS * 2
        
        if len(self.context.history) <= max_entries:
            return
        
        # Identify essential entries that must be kept
        essential_indices = set()
        
        # Keep the most recent essential_entries
        for i in range(len(self.context.history) - essential_entries, len(self.context.history)):
            if i >= 0:
                essential_indices.add(i)
        
        # Also keep any entries that reference the active order
        if self.active_order.order or self.active_order.draft_items:
            active_skus = set()
            if self.active_order.order:
                active_skus.update(item.sku for item in self.active_order.order.items)
            active_skus.update(self.active_order.draft_items)
            
            for i, entry in enumerate(self.context.history):
                content_lower = entry.content.lower()
                for sku in active_skus:
                    if sku.lower() in content_lower:
                        essential_indices.add(i)
                        break
        
        # Build trimmed history
        trimmed = [entry for i, entry in enumerate(self.context.history) if i in essential_indices]
        self.context.history = trimmed
    
    def update_active_order(
        self,
        order: Optional[Order] = None,
        draft_items: Optional[List[LineItem]] = None,
        mentioned_skus: Optional[List[str]] = None,
        search_results: Optional[List[dict]] = None,
        awaiting_confirmation: Optional[bool] = None,
    ) -> None:
        """Update the active order state."""
        if order is not None:
            self.active_order.order = order
        if draft_items is not None:
            self.active_order.draft_items = draft_items
        if mentioned_skus is not None:
            self.active_order.last_mentioned_skus = mentioned_skus[-5:]  # Keep last 5
        if search_results is not None:
            self.active_order.last_search_results = search_results
        if awaiting_confirmation is not None:
            self.active_order.awaiting_confirmation = awaiting_confirmation
    
    def get_active_order_context(self) -> str:
        """Get a string representation of active order for context injection."""
        parts = []
        
        if self.active_order.order:
            parts.append(f"ACTIVE ORDER (ID: {self.active_order.order.order_id}):")
            for item in self.active_order.order.items:
                parts.append(f"  - {item.name} (SKU: {item.sku}) x{item.quantity} = PKR {item.line_total:,}")
            parts.append(f"  Subtotal: PKR {self.active_order.order.subtotal:,}")
            parts.append(f"  Tax: PKR {self.active_order.order.tax:,}")
            parts.append(f"  Shipping: PKR {self.active_order.order.shipping:,}")
            parts.append(f"  Grand Total: PKR {self.active_order.order.grand_total:,}")
            parts.append(f"  Status: {self.active_order.order.status.value}")
        
        elif self.active_order.draft_items:
            parts.append("DRAFT ORDER (not confirmed):")
            for item in self.active_order.draft_items:
                parts.append(f"  - {item.name} (SKU: {item.sku}) x{item.quantity} = PKR {item.line_total:,}")
            subtotal = sum(item.line_total for item in self.active_order.draft_items)
            parts.append(f"  Subtotal: PKR {subtotal:,}")
        
        if self.active_order.last_mentioned_skus:
            parts.append(f"RECENTLY MENTIONED SKUs: {', '.join(self.active_order.last_mentioned_skus)}")
        
        return "\n".join(parts) if parts else "No active order context."
    
    def clear_active_order(self) -> None:
        """Clear active order state (e.g., after confirmation or cancellation)."""
        self.active_order = ActiveOrderState()


# Global manager instance per session
_history_manager: Optional[HistoryManager] = None


def get_history_manager(context: ShopContext) -> HistoryManager:
    """Get or create history manager for a session."""
    global _history_manager
    if _history_manager is None:
        _history_manager = HistoryManager(context)
    return _history_manager


def reset_history_manager() -> None:
    """Reset history manager (for new session)."""
    global _history_manager
    _history_manager = None