from __future__ import annotations

import chainlit as cl
import uuid

from shop_desk.agents.agents_sdk import run_desk_agent
from shop_desk.context import with_context, set_current_context
from shop_desk.models.shop import ShopContext, Tier
from shop_desk.tools import create_session
from shop_desk.config.settings import get_settings
from shop_desk.prompts.dynamic import get_operating_hours_status
from shop_desk.history import reset_history_manager


@cl.on_chat_start
async def on_chat_start():
    """Initialize a new conversation session."""
    settings = get_settings()
    session_id = cl.user_session.get("id") or str(uuid.uuid4())
    
    ctx = create_session(
        session_id=session_id,
        shop="Al-Noor Electronics",
        currency="PKR",
        customer_id=None,
        tier="walk_in",
        catalogue_version=settings.catalogue_version,
    )
    
    cl.user_session.set("context", ctx)
    set_current_context(ctx)
    
    hours_status = get_operating_hours_status()
    status_emoji = "🟢" if hours_status["is_open"] else "🔴"
    
    # Clean, conversational welcome message
    welcome_msg = (
        f"{status_emoji} **Welcome to Al-Noor Electronics!**\n\n"
        f"{hours_status['message']}\n\n"
        f"I'm here to help you find the right products. You can ask me things like:\n\n"
        f"💰 **Prices** — \"How much is the electric kettle?\" or \"Price of ANE-EK-001\"\n"
        f"📦 **Stock** — \"Is the pedestal fan available?\" or \"Stock for ANE-PF-002\"\n"
        f"🔍 **Search** — \"Show me blenders under 5000\" or \"Find kitchen appliances\"\n"
        f"📊 **Compare** — \"Compare the microwave and air cooler\"\n"
        f"🧾 **Quotes** — \"Quote for 2 kettles and 1 blender with tax\"\n"
        f"🤝 **Help** — \"I need to speak to someone about an issue\"\n\n"
        f"Just type naturally — I'll understand."
    )
    
    await cl.Message(content=welcome_msg).send()


@cl.on_message
async def on_message(message: cl.Message):
    """Handle incoming messages with a clean conversational flow."""
    ctx = cl.user_session.get("context")
    if not ctx:
        await cl.Message(content="Session expired. Please refresh the page.").send()
        return
    
    with with_context(ctx):
        user_text = message.content.strip()
        
        # Show thinking indicator
        async with cl.Step(name="Processing", type="run") as step:
            try:
                response = await run_desk_agent(user_text, ctx)
                step.output = response
            except Exception as e:
                error_msg = f"Sorry, I ran into an issue: {str(e)}"
                step.output = error_msg
                await cl.Message(content=error_msg).send()
                return
        
        # Send the actual response
        if response:
            await cl.Message(content=response).send()


@cl.on_chat_end
async def on_chat_end():
    """Clean up on chat end."""
    reset_history_manager()


# Optional: Add a nice avatar/action buttons for common actions
@cl.action_callback("quick_price")
async def on_quick_price(action: cl.Action):
    await on_message(cl.Message(content=f"Price of {action.payload['sku']}"))


@cl.action_callback("quick_stock")
async def on_quick_stock(action: cl.Action):
    await on_message(cl.Message(content=f"Stock for {action.payload['sku']}"))