import aiohttp
import asyncio
import logging

CHATROOM_URL = "https://api.meeff.com/chatroom/dashboard/v1"
MORE_CHATROOMS_URL = "https://api.meeff.com/chatroom/more/v1"
SEND_MESSAGE_URL = "https://api.meeff.com/chat/send/v2"
HEADERS = {
    'User-Agent': "okhttp/4.12.0",
    'Accept-Encoding': "gzip",
    'content-type': "application/json; charset=utf-8"
}

async def fetch_chatrooms(session, token, from_date=None):
    headers = HEADERS.copy()
    headers['meeff-access-token'] = token
    params = {'locale': "en"}
    if from_date:
        params['fromDate'] = from_date

    async with session.get(CHATROOM_URL, params=params, headers=headers) as response:
        if response.status != 200:
            logging.error(f"Failed to fetch chatrooms: {response.status}")
            return None, None
        data = await response.json()
        return data.get("rooms", []), data.get("next")

async def fetch_more_chatrooms(session, token, from_date):
    headers = HEADERS.copy()
    headers['meeff-access-token'] = token
    payload = {
        "fromDate": from_date,
        "locale": "en"
    }

    async with session.post(MORE_CHATROOMS_URL, json=payload, headers=headers) as response:
        if response.status != 200:
            logging.error(f"Failed to fetch more chatrooms: {response.status}")
            return None, None
        data = await response.json()
        return data.get("rooms", []), data.get("next")

async def send_message(session, token, chatroom_id, message):
    headers = HEADERS.copy()
    headers['meeff-access-token'] = token
    payload = {
        "chatRoomId": chatroom_id,
        "message": message,
        "locale": "en"
    }

    async with session.post(SEND_MESSAGE_URL, json=payload, headers=headers) as response:
        if response.status != 200:
            logging.error(f"Failed to send message: {response.status}")
            return None
        return await response.json()

async def send_message_to_everyone(token, message, status_message=None, bot=None, chat_id=None):
    sent_count = 0
    total_chatrooms = 0
    from_date = None

    async with aiohttp.ClientSession() as session:
        while True:
            chatrooms, next_from_date = await fetch_chatrooms(session, token, from_date) if from_date is None else await fetch_more_chatrooms(session, token, from_date)
            if not chatrooms:
                logging.info("No more chatrooms found.")
                break

            total_chatrooms += len(chatrooms)
            tasks = [send_message(session, token, chatroom["_id"], message) for chatroom in chatrooms]
            await asyncio.gather(*tasks)
            sent_count += len(chatrooms)

            if bot and chat_id and status_message:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_message.message_id,
                    text=f"Chatrooms: {total_chatrooms} Messages sent: {sent_count}",
                )
            logging.info(f"Sent messages to {len(chatrooms)} chatrooms.")

            if not next_from_date:
                break
            from_date = next_from_date

    logging.info(f"Finished sending messages. Total Chatrooms: {total_chatrooms}, Messages sent: {sent_count}")
    if bot and chat_id and status_message:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_message.message_id,
            text=f"Finished sending messages. Total Chatrooms: {total_chatrooms}, Messages sent: {sent_count}"
        )
