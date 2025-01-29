import asyncio
import aiohttp
from aiogram import Bot, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from db import get_tokens, get_current_account, set_current_account
from lounge import send_lounge
from chatroom import send_message_to_everyone
from unsubscribe import unsubscribe_everyone

# Inline keyboards
aio_markup = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Start Requests", callback_data="aio_start_requests")],
    [InlineKeyboardButton(text="Hi to Lounge", callback_data="aio_hi_lounge")],
    [InlineKeyboardButton(text="Hi to Chatroom", callback_data="aio_hi_chatroom")],
    [InlineKeyboardButton(text="Skip", callback_data="aio_skip_confirm")]
])

aio_markup_processing = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Stop Requests", callback_data="aio_stop_requests")]
])

# User states for managing process statuses
user_states = {}

# Fetch users from the API
async def fetch_users(session, token, batch_size=50):
    url = "https://api.meeff.com/user/explore/v2/?lat=33.589510&lng=-117.860909"
    headers = {"meeff-access-token": token, "Connection": "keep-alive"}
    users = []
    async with session.get(url, headers=headers) as response:
        if response.status != 200:
            return users
        response_users = (await response.json()).get("users", [])
        users.extend(response_users[:batch_size])
    await asyncio.sleep(2)  # Add a delay of 1 second between requests
    return users

# Update status message
async def update_status_message(bot, user_id, state, template):
    current_message = (
        f"Total Accounts: {state['total_accounts']}\n\n" +
        "\n\n".join(state["messages"]) +
        f"\n\n{template}"
    )
    await bot.edit_message_text(
        chat_id=user_id,
        message_id=state["status_message_id"],
        text=current_message,
        reply_markup=aio_markup_processing,
    )

# Process fetched users
async def process_users(session, users, token, state, bot, user_id):
    async def process_user(user):
        url = f"https://api.meeff.com/user/undoableAnswer/v5/?userId={user['_id']}&isOkay=1"
        headers = {"meeff-access-token": token, "Connection": "keep-alive"}
        async with session.get(url, headers=headers) as response:
            data = await response.json()
            if data.get("errorCode") == "LikeExceeded":
                state["messages"][-1] += "\nDaily like limit reached."
                return True
            state["total_added_friends"] += 1
            if state["total_added_friends"] % 7 == 0:
                state["messages"][-1] = f"{state['messages'][-1].split('\n')[0]}\nAdded Friends: {state['total_added_friends']}"
                await update_status_message(bot, user_id, state, f"Total Added Friends: {state['total_added_friends']}")
        await asyncio.sleep(2)  # Add a delay of 1 second between requests
        return False

    tasks = [process_user(user) for user in users]
    results = await asyncio.gather(*tasks)
    return any(results)

# Core process for managing requests
async def run_requests(user_id, bot, status_message_id):
    tokens = get_tokens(user_id)
    state = {
        "running": True,
        "status_message_id": status_message_id,
        "total_added_friends": 0,
        "messages": [],
        "total_accounts": len(tokens),
    }
    user_states[user_id] = state

    async with aiohttp.ClientSession() as session:
        for index, token_info in enumerate(tokens):
            if not state["running"]:
                break
            token = token_info["token"]
            account_name = f"Account {index + 1}"
            state["messages"].append(
                f"{index + 1} Current Account: {account_name}\nAdded Friends: 0"
            )
            while True:
                users = await fetch_users(session, token)
                if not users or await process_users(session, users, token, state, bot, user_id):
                    break

    final_message = f"Total Accounts: {state['total_accounts']}\n\n" + "\n\n".join(state["messages"]) + f"\n\nTotal Added Friends: {state['total_added_friends']}"
    await bot.edit_message_text(
        chat_id=user_id,
        message_id=state["status_message_id"],
        text=final_message,
        reply_markup=aio_markup,
    )

# Callback handler for user interactions
async def aio_callback_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    bot = callback_query.bot

    if callback_query.data == "aio_start_requests":
        await callback_query.message.edit_text(
            "Starting requests...",
            reply_markup=aio_markup_processing
        )
        asyncio.create_task(run_requests(user_id, bot, callback_query.message.message_id))
        await callback_query.answer("Requests started!")

    elif callback_query.data == "aio_stop_requests":
        state = user_states.get(user_id)
        if state:
            state["running"] = False
            await callback_query.message.edit_text(
                "Requests stopped.",
                reply_markup=aio_markup
            )
            await callback_query.answer("Requests stopped!")
        else:
            await callback_query.answer("No requests are running.")

    elif callback_query.data == "aio_hi_lounge":
        await handle_hi(callback_query, send_lounge, "lounge")

    elif callback_query.data == "aio_hi_chatroom":
        await handle_hi(callback_query, send_message_to_everyone, "chatroom")

    elif callback_query.data == "aio_skip_confirm":
        await callback_query.message.edit_text(
            "Are you sure you want to skip all chatrooms?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Yes", callback_data="aio_skip")],
                [InlineKeyboardButton(text="No", callback_data="aio_cancel")]
            ])
        )
        await callback_query.answer("Please confirm your action.")

    elif callback_query.data == "aio_skip":
        await handle_skip(callback_query)

    elif callback_query.data == "aio_cancel":
        await callback_query.message.edit_text(
            "Cancelled skipping chatrooms.",
            reply_markup=aio_markup
        )
        await callback_query.answer("Action cancelled.")

# Helper functions
async def handle_hi(callback_query, action, target):
    user_id = callback_query.from_user.id
    bot = callback_query.bot
    tokens = get_tokens(user_id)
    state = {
        "running": True,
        "status_message_id": callback_query.message.message_id,
        "messages": [],
        "total_accounts": len(tokens),
    }
    user_states[user_id] = state

    for index, token_info in enumerate(tokens):
        if not state["running"]:
            break
        token = token_info["token"]
        account_name = f"Account {index + 1}"
        state["messages"].append(
            f"{index + 1} Current Account: {account_name}\nSending 'Hi' to {target}..."
        )
        await update_status_message(bot, user_id, state, f"Sending 'Hi' to {target}...")
        await action(token, "hi", bot, user_id)
        state["messages"][-1] = f"{state['messages'][-1].split('\n')[0]}\n'Hi' sent to {target}."
        await update_status_message(bot, user_id, state, f"'Hi' sent to {target}.")
        
    final_message = f"Total Accounts: {state['total_accounts']}\n\n" + "\n\n".join(state["messages"])
    await bot.edit_message_text(
        chat_id=user_id,
        message_id=state["status_message_id"],
        text=final_message,
        reply_markup=aio_markup,
    )
    await callback_query.answer(f"'Hi' sent to {target}!")

async def handle_skip(callback_query):
    user_id = callback_query.from_user.id
    bot = callback_query.bot
    tokens = get_tokens(user_id)
    state = {
        "running": True,
        "status_message_id": callback_query.message.message_id,
        "messages": [],
        "total_accounts": len(tokens),
    }
    user_states[user_id] = state

    for index, token_info in enumerate(tokens):
        if not state["running"]:
            break
        token = token_info["token"]
        account_name = f"Account {index + 1}"
        state["messages"].append(
            f"{index + 1} Current Account: {account_name}\nSkipping chatrooms..."
        )
        await update_status_message(bot, user_id, state, "Skipping chatrooms...")
        await unsubscribe_everyone(token, bot, user_id)
        state["messages"][-1] = f"{state['messages'][-1].split('\n')[0]}\nSkipped all chatrooms."
        await update_status_message(bot, user_id, state, "Skipped all chatrooms.")
        
    final_message = f"Total Accounts: {state['total_accounts']}\n\n" + "\n\n".join(state["messages"])
    await bot.edit_message_text(
        chat_id=user_id,
        message_id=state["status_message_id"],
        text=final_message,
        reply_markup=aio_markup,
    )
    await callback_query.answer("Skipped chatrooms!")
