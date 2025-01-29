import asyncio
import aiohttp
import logging
import html
import json
from collections import defaultdict
from aiogram import Bot, Dispatcher, Router, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from aiogram.filters import Command
from aiogram.types.callback_query import CallbackQuery
from db import set_token, get_tokens, set_current_account, get_current_account, delete_token, set_user_filters, get_user_filters
from lounge import send_lounge
from chatroom import send_message_to_everyone
from unsubscribe import unsubscribe_everyone
from filters import filter_command, set_filter
from aio import aio_markup, aio_callback_handler, run_requests, aio_markup_processing, user_states
from datetime import datetime, timedelta

# Tokens
API_TOKEN = "7735279075:AAHvefFBqiRUE4NumS0JlwTAiSMzfrgTmqA"

# Admin user IDs
ADMIN_USER_IDS = [6387028671, 6816341239, 6204011131]  # Replace with actual admin user IDs

# Password access dictionary
password_access = {}

# Password for temporary access
TEMP_PASSWORD = "11223344"  # Replace with your chosen password

# Initialize logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Initialize bot and dispatcher
bot = Bot(token=API_TOKEN)
router = Router()
dp = Dispatcher()

# Global state variables
user_states = defaultdict(lambda: {
    "running": False,
    "status_message_id": None,
    "pinned_message_id": None,
    "total_added_friends": 0
})

# Inline keyboards
start_markup = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Start Requests", callback_data="start")],
    [InlineKeyboardButton(text="Manage Accounts", callback_data="manage_accounts")],
    [InlineKeyboardButton(text="Show Account Info", callback_data="show_account_info")]
])

stop_markup = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Stop Requests", callback_data="stop")]
])

back_markup = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Back", callback_data="back_to_menu")]
])

def is_admin(user_id):
    return user_id in ADMIN_USER_IDS
    
def has_valid_access(user_id):
    if is_admin(user_id):
        return True
    if user_id in password_access and password_access[user_id] > datetime.now():
        return True
    return False

async def fetch_users(session, token):
    url = "https://api.meeff.com/user/explore/v2/?lat=33.589510&lng=-117.860909"
    headers = {"meeff-access-token": token, "Connection": "keep-alive"}
    async with session.get(url, headers=headers) as response:
        if response.status != 200:
            logging.error(f"Failed to fetch users: {response.status}")
            return []
        return (await response.json()).get("users", [])

def format_user_details(user):
    return (
        f"<b>Name:</b> {html.escape(user.get('name', 'N/A'))}\n"
        f"<b>Description:</b> {html.escape(user.get('description', 'N/A'))}\n"
        f"<b>Birth Year:</b> {html.escape(str(user.get('birthYear', 'N/A')))}\n"
        f"<b>Distance:</b> {html.escape(str(user.get('distance', 'N/A')))} km\n"
        f"<b>Language Codes:</b> {html.escape(', '.join(user.get('languageCodes', [])))}\n"
        "Photos: " + ' '.join([f"<a href='{html.escape(url)}'>Photo</a>" for url in user.get('photoUrls', [])])
    )

async def process_users(session, users, token, user_id):
    state = user_states[user_id]
    batch_added_friends = 0
    for user in users:
        if not state["running"]:
            break
        url = f"https://api.meeff.com/user/undoableAnswer/v5/?userId={user['_id']}&isOkay=1"
        headers = {"meeff-access-token": token, "Connection": "keep-alive"}
        async with session.get(url, headers=headers) as response:
            data = await response.json()
            if data.get("errorCode") == "LikeExceeded":
                logging.info("Daily like limit reached.")
                await bot.edit_message_text(chat_id=user_id, message_id=state["status_message_id"],
                                            text=f"You've reached the daily limit. Total Added Friends: {state['total_added_friends']}. Try again tomorrow.",
                                            reply_markup=None)
                return True
            await bot.send_message(chat_id=user_id, text=format_user_details(user), parse_mode="HTML")
            batch_added_friends += 1
            state["total_added_friends"] += 1
            if state["running"]:
                await bot.edit_message_text(chat_id=user_id, message_id=state["status_message_id"],
                                            text=f"Batch: {state['batch_index']} Users Fetched: {len(users)}\n"
                                                 f"Batch: {state['batch_index']} Added Friends: {batch_added_friends}\n"
                                                 f"Total Added: {state['total_added_friends']}",
                                            reply_markup=stop_markup)
            await asyncio.sleep(1)
    return False

async def run_requests(user_id):
    state = user_states[user_id]
    state["total_added_friends"] = 0
    state["batch_index"] = 0
    async with aiohttp.ClientSession() as session:
        while state["running"]:
            try:
                token = get_current_account(user_id)
                if not token:
                    await bot.edit_message_text(chat_id=user_id, message_id=state["status_message_id"],
                                                text="No active account found. Please set an account before starting requests.",
                                                reply_markup=None)
                    state["running"] = False
                    if state["pinned_message_id"]:
                        await bot.unpin_chat_message(chat_id=user_id, message_id=state["pinned_message_id"])
                        state["pinned_message_id"] = None
                    return

                users = await fetch_users(session, token)
                state["batch_index"] += 1
                if not users:
                    await bot.edit_message_text(chat_id=user_id, message_id=state["status_message_id"],
                                                text=f"Batch: {state['batch_index']} Users Fetched: 0\n"
                                                     f"Total Added: {state['total_added_friends']}",
                                                reply_markup=stop_markup)
                else:
                    if await process_users(session, users, token, user_id):
                        state["running"] = False
                        if state["pinned_message_id"]:
                            await bot.unpin_chat_message(chat_id=user_id, message_id=state["pinned_message_id"])
                            state["pinned_message_id"] = None
                        break
                await asyncio.sleep(1)
            except Exception as e:
                logging.error(f"Error during processing: {e}")
                await bot.edit_message_text(chat_id=user_id, message_id=state["status_message_id"],
                                            text=f"An error occurred: {e}", reply_markup=None)
                state["running"] = False
                if state["pinned_message_id"]:
                    await bot.unpin_chat_message(chat_id=user_id, message_id=state["pinned_message_id"])
                    state["pinned_message_id"] = None
                break

async def fetch_account_info(token):
    url = "https://api.meeff.com/user/login/v4"
    payload = {
        "os": "iOS v16.4.1", "platform": "ios", "device": "BRAND: Apple, MODEL: iPhone 14 Pro",
        "deviceUniqueId": "6a92f1b4e7d54abc", "deviceLanguage": "en", "deviceRegion": "US",
        "simRegion": "US", "deviceGmtOffset": "-0800", "deviceRooted": 0, "deviceEmulator": 0,
        "appVersion": "6.3.9", "locale": "en"
    }
    headers = {
        'User-Agent': "okhttp/4.12.0",
        'Accept-Encoding': "gzip",
        'meeff-access-token': token,
        'content-type': "application/json; charset=utf-8"
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=json.dumps(payload), headers=headers) as response:
            if response.status != 200:
                logging.error(f"Failed to fetch account info: {response.status}")
                return None
            return (await response.json()).get('user')

@router.message(Command("password"))
async def password_command(message: types.Message):
    user_id = message.chat.id
    command_text = message.text.strip()
    if len(command_text.split()) < 2:
        await message.reply("Please provide the password. Usage: /password <password>")
        return

    provided_password = command_text.split()[1]
    if provided_password == TEMP_PASSWORD:
        password_access[user_id] = datetime.now() + timedelta(hours=1)
        await message.reply("Access granted for one hour.")
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    else:
        await message.reply("Incorrect password.")

@router.message(Command("start"))
async def start_command(message: types.Message):
    user_id = message.chat.id
    if not has_valid_access(user_id):
        await message.reply("You are not authorized to use this bot.")
        return
    state = user_states[user_id]
    state["status_message_id"] = (await message.answer("Welcome! Use the button below to start requests.", reply_markup=start_markup)).message_id
    state["pinned_message_id"] = None

@router.message(Command("chatroom"))
async def send_to_all_command(message: types.Message):
    user_id = message.chat.id
    if not has_valid_access(user_id):
        await message.reply("You are not authorized to use this bot.")
        return
    token = get_current_account(user_id)
    if not token:
        await message.reply("No active account found. Please set an account before sending messages.")
        return

    command_text = message.text.strip()
    if len(command_text.split()) < 2:
        await message.reply("Please provide a message to send. Usage: /send_to_all <message>")
        return

    custom_message = " ".join(command_text.split()[1:])
    status_message = await message.reply("Fetching chatrooms and sending messages...")
    await send_message_to_everyone(token, custom_message, status_message=status_message, bot=bot, chat_id=user_id)
    await status_message.edit_text("Messages sent to everyone in all chatrooms.")

@router.message(Command("skip"))
async def unsubscribe_all_command(message: types.Message):
    user_id = message.chat.id
    if not has_valid_access(user_id):
        await message.reply("You are not authorized to use this bot.")
        return
    token = get_current_account(user_id)
    if not token:
        await message.reply("No active account found. Please set an account before unsubscribing.")
        return

    status_message = await message.reply("Fetching chatrooms and unsubscribing...")
    await unsubscribe_everyone(token, status_message=status_message, bot=bot, chat_id=user_id)
    await status_message.edit_text("Unsubscribed from all chatrooms.")

@router.message(Command("lounge"))
async def lounge_command(message: types.Message):
    user_id = message.chat.id
    if not has_valid_access(user_id):
        await message.reply("You are not authorized to use this bot.")
        return
    token = get_current_account(user_id)
    if not token:
        await message.reply("No active account found. Please set an account before sending messages.")
        return

    command_text = message.text.strip()
    if len(command_text.split()) < 2:
        await message.reply("Please provide a message to send. Usage: /lounge <message>")
        return

    custom_message = " ".join(command_text.split()[1:])
    status_message = await message.reply("Fetching lounge users and sending messages...")
    await send_lounge(token, custom_message, status_message=status_message, bot=bot, chat_id=user_id)
    await status_message.edit_text("Messages sent to everyone in the lounge.")

@router.message(Command("filter"))
async def filter_handler(message: types.Message):
    if not has_valid_access(message.chat.id):
        await message.reply("You are not authorized to use this bot.")
        return
    await filter_command(message)

@router.message(Command("invoke"))
async def invoke_command(message: types.Message):
    user_id = message.chat.id
    if not has_valid_access(user_id):
        await message.reply("You are not authorized to use this bot.")
        return

    tokens = get_tokens(user_id)
    expired_tokens = []
    for token in tokens:
        account_info = await fetch_account_info(token["token"])
        if account_info is None:
            expired_tokens.append(token)

    if expired_tokens:
        for token in expired_tokens:
            delete_token(user_id, token["token"])
            await message.reply(f"Deleted expired token for account: {token['name']}")
    else:
        await message.reply("No expired tokens found.")

@router.message(Command("aio"))
async def aio_command(message: types.Message):
    if not has_valid_access(message.chat.id):
        await message.reply("You are not authorized to use this bot.")
        return
    await message.answer("Choose an action:", reply_markup=aio_markup)

@router.message()
async def handle_new_token(message: types.Message):
    if message.text and message.text.startswith("/"):
        return
    user_id = message.from_user.id
    
    # Ignore bot's own messages
    if message.from_user.is_bot:
        return
    
    if not has_valid_access(user_id):
        await message.reply("You are not authorized to use this bot.")
        return
    
    if message.text:
        token = message.text.strip()
        if len(token) < 10:
            await message.reply("Invalid token. Please try again.")
            return

        account_info = await fetch_account_info(token)
        if account_info is None:
            await message.reply("Failed to sign in. Token is expired or invalid.")
            return

        set_token(user_id, token, account_info['name'])
        await message.reply("Your access token has been verified and saved. Use the menu to manage accounts.")
    else:
        await message.reply("Message text is empty. Please provide a valid token.")

@router.callback_query()
async def callback_handler(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    state = user_states[user_id]

    if not has_valid_access(user_id):
        await callback_query.answer("You are not authorized to use this bot.")
        return

    if callback_query.data.startswith("aio_"):
        await aio_callback_handler(callback_query)
        return

    if callback_query.data == "manage_accounts":
        tokens = get_tokens(user_id)
        current_token = get_current_account(user_id)
        if not tokens:
            await callback_query.message.edit_text("No accounts saved. Send a new token to add an account.", reply_markup=back_markup)
            return
        buttons = [
            [InlineKeyboardButton(text=f"{token['name']} {'(Current)' if token['token'] == current_token else ''}", callback_data=f"set_account_{i}"),
             InlineKeyboardButton(text="Delete", callback_data=f"delete_account_{i}")]
            for i, token in enumerate(tokens)
        ]
        buttons.append([InlineKeyboardButton(text="Back", callback_data="back_to_menu")])
        await callback_query.message.edit_text("Manage your accounts:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

    elif callback_query.data.startswith("set_account_"):
        index = int(callback_query.data.split("_")[-1])
        tokens = get_tokens(user_id)
        if index < len(tokens):
            set_current_account(user_id, tokens[index]["token"])
            await callback_query.message.edit_text("Account set as active. You can now start requests.")
        else:
            await callback_query.answer("Invalid account selected.")

    elif callback_query.data.startswith("delete_account_"):
        index = int(callback_query.data.split("_")[-1])
        tokens = get_tokens(user_id)
        if index < len(tokens):
            delete_token(user_id, tokens[index]["token"])
            await callback_query.message.edit_text("Account has been deleted.", reply_markup=back_markup)
        else:
            await callback_query.answer("Invalid account selected.")

    elif callback_query.data == "start":
        if state["running"]:
            await callback_query.answer("Requests are already running!")
        else:
            state["running"] = True
            try:
                status_message = await callback_query.message.edit_text("Initializing requests...", reply_markup=stop_markup)
                state["status_message_id"] = status_message.message_id
                state["pinned_message_id"] = status_message.message_id
                await bot.pin_chat_message(chat_id=user_id, message_id=state["status_message_id"])
                asyncio.create_task(run_requests(user_id))
                await callback_query.answer("Requests started!")
            except Exception as e:
                logging.error(f"Error while starting requests: {e}")
                await callback_query.message.edit_text("Failed to start requests. Please try again later.", reply_markup=start_markup)
                state["running"] = False

    elif callback_query.data == "stop":
        if not state["running"]:
            await callback_query.answer("Requests are not running!")
        else:
            state["running"] = False
            message_text = f"Requests stopped. Use the button below to start again.\nTotal Added Friends: {state['total_added_friends']}"
            await callback_query.message.edit_text(message_text, reply_markup=start_markup)
            await callback_query.answer("Requests stopped.")
            if state["pinned_message_id"]:
                await bot.unpin_chat_message(chat_id=user_id, message_id=state["pinned_message_id"])
                state["pinned_message_id"] = None

    elif callback_query.data == "show_account_info":
        token = get_current_account(user_id)
        if not token:
            await callback_query.message.edit_text("No active account token found. Please set an account before requesting account info.", reply_markup=back_markup)
            return
        account_info = await fetch_account_info(token)
        if account_info:
            await callback_query.message.edit_text(
                f"<b>Name:</b> {html.escape(account_info.get('name', 'N/A'))}\n"
                f"<b>Email:</b> {html.escape(account_info.get('email', 'N/A'))}\n"
                f"<b>Birth Year:</b> {html.escape(str(account_info.get('birthYear', 'N/A')))}\n"
                f"<b>Nationality:</b> {html.escape(account_info.get('nationalityCode', 'N/A'))}\n"
                f"<b>Languages:</b> {html.escape(', '.join(account_info.get('languageCodes', [])))}\n"
                f"<b>Description:</b> {html.escape(account_info.get('description', 'N/A'))}\n"
                "Photos: " + ' '.join([f"<a href='{html.escape(url)}'>Photo</a>" for url in account_info.get('photoUrls', [])]),
                parse_mode="HTML", reply_markup=back_markup)
        else:
            await callback_query.message.edit_text("Failed to retrieve account information.", reply_markup=back_markup)

    elif callback_query.data == "back_to_menu":
        await callback_query.message.edit_text("Welcome! Use the buttons below to navigate.", reply_markup=start_markup)

    if callback_query.data.startswith("filter_"):
        await set_filter(callback_query)

async def set_bot_commands():
    commands = [
        BotCommand(command="start", description="Start the bot"),
        BotCommand(command="lounge", description="Send message to everyone in the lounge"),
        BotCommand(command="chatroom", description="Send a message to everyone"),
        BotCommand(command="aio", description="Show aio commands"),  # Reorder aio command
        BotCommand(command="filter", description="Set filter preferences"),
        BotCommand(command="invoke", description="Invoke expired token cleanup"),
        BotCommand(command="skip", description="Skip everyone in the chatroom"),
        BotCommand(command="password", description="Enter password for temporary access")
    ]
    await bot.set_my_commands(commands)

async def main():
    await set_bot_commands()
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
