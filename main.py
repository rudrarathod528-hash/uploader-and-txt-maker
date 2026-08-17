#  MIT License
#
#  Copyright (c) 2019-present Dan <https://github.com/delivrance>
#
#  Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to deal
#  in the Software without restriction, including without limitation the rights
#  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#  copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in all
#  copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#  SOFTWARE
import os
import imageio_ffmpeg
# Automatically sets the ffmpeg binary path for yt-dlp and other tools
os.environ["PATH"] += os.pathsep + os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())
from pyrogram.errors.exceptions.bad_request_400 import StickerEmojiInvalid
import requests
import json
import subprocess
from pyrogram import Client, filters
from pyrogram.types.messages_and_media import message
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import FloodWait
from pyromod import listen
from pyrogram.types import Message
from pyrogram import Client, filters
from p_bar import progress_bar
from subprocess import getstatusoutput
from aiohttp import ClientSession
import helper
from logger import logging
import time
import asyncio
from pyrogram.types import User, Message
import sys
import re
import os
from logging.handlers import RotatingFileHandler
import logging
from io import BytesIO

from cookie_session import (
    CookieAuthenticationError,
    CookieAuthConfig,
    CookieSessionConfigurationError,
    CookieSessionManager,
    EmptyCookieSessionError,
    UnauthenticatedSessionError,
)


logging.basicConfig(
    level=logging.DEBUG,
    format=
    "%(asctime)s - %(levelname)s - %(message)s [%(filename)s:%(lineno)d]",
    datefmt="%d-%b-%y %H:%M:%S",
    handlers=[
        RotatingFileHandler("Assist.txt", maxBytes=50000000, backupCount=10),
        logging.StreamHandler(),
    ],
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)


logging = logging.getLogger()


def _required_environment(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} environment variable is required")
    return value


def _integer_list_from_environment(name):
    raw_value = os.getenv(name, "")
    try:
        return [int(value.strip()) for value in raw_value.split(",") if value.strip()]
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a comma-separated list of integers") from exc


def _optional_integer_from_environment(name):
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return None
    try:
        return int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


bot = Client(
    "bot",
    bot_token=_required_environment("BOT_TOKEN"),
    api_id=int(_required_environment("API_ID")),
    api_hash=_required_environment("API_HASH"),
    in_memory=True,
)
auth_users = _integer_list_from_environment("AUTH_USERS")
sudo_users = auth_users
sudo_groups = _integer_list_from_environment("GROUPS")
admin_user_id = _optional_integer_from_environment("ADMIN_USER_ID")
cookie_session_manager = CookieSessionManager(CookieAuthConfig.from_environment())

shell_usage = f"**USAGE:** Executes terminal commands directly via bot.\n\n<pre>/shell pip install requests</pre>"
def one(user_id):
    if user_id in sudo_users:
        return True
    return False
@bot.on_message(filters.command(["shell"]))
async def shell(client, message: Message):
    """
    Executes terminal commands via bot.
    """
    logging.info('hh')
    if not one(message.from_user.id):
        return

    if len(message.command) < 2:
        return await message.reply_text(shell_usage, quote=True)

    user_input = message.text.split(None, 1)[1].split(" ")

    try:
        shell = subprocess.Popen(
            user_input, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        stdout, stderr = shell.communicate()
        result = str(stdout.decode().strip()) + str(stderr.decode().strip())

    except Exception as error:
        logging.info(f"{error}")
        return await message.reply_text(f"**Error**:\n\n{error}", quote=True)

    if len(result) > 2000:
        file = BytesIO(result.encode())
        file.name = "output.txt"
        await message.reply_text("Output is too large (Sending it as File)", quote=True)
        await client.send_document(message.chat.id, file, caption=file.name)
    else:
        await message.reply_text(f"**Output:**:\n\n{result}", quote=True)


async def _active_cookies(force_refresh=False):
    if force_refresh or not cookie_session_manager.is_authenticated:
        return await asyncio.to_thread(cookie_session_manager.authenticate)
    try:
        return await asyncio.to_thread(cookie_session_manager.get_cookies)
    except (UnauthenticatedSessionError, EmptyCookieSessionError):
        return await asyncio.to_thread(cookie_session_manager.authenticate)


@bot.on_message(filters.command(["cookie"]))
async def cookie_handler(client: Client, message: Message):
    requester_id = message.from_user.id if message.from_user is not None else None
    if admin_user_id is None:
        await message.reply_text(
            "Cookie command is disabled because ADMIN_USER_ID is not configured."
        )
        return
    if requester_id != admin_user_id:
        await message.reply_text("You are not authorized to use this command.")
        return

    if len(message.command) > 1 and message.command[1].casefold() != "refresh":
        await message.reply_text("Usage: /cookie or /cookie refresh")
        return

    status_message = await message.reply_text("Checking the authenticated session...")
    try:
        cookies = await _active_cookies(
            force_refresh=len(message.command) > 1
        )
    except CookieSessionConfigurationError:
        await status_message.edit_text(
            "Cookie authentication is not configured. Check the COOKIE_AUTH_* "
            "Railway variables."
        )
        return
    except CookieAuthenticationError:
        await status_message.edit_text(
            "Cookie authentication failed. Verify the endpoint, credentials, and "
            "network availability."
        )
        return
    except EmptyCookieSessionError:
        await status_message.edit_text(
            "Authentication completed, but the endpoint returned no active cookies."
        )
        return
    except Exception as exc:
        logging.error("Unexpected cookie-session failure", exc_info=exc)
        await status_message.edit_text(
            "An unexpected error occurred while reading the authenticated session."
        )
        return

    cookie_json = json.dumps(cookies, ensure_ascii=False, indent=2, sort_keys=True)
    safe_json = cookie_json.replace("`", "\\u0060")
    try:
        if len(safe_json) <= 3500:
            await client.send_message(
                chat_id=admin_user_id,
                text=f"**Active session cookies**\n```json\n{safe_json}\n```",
            )
        else:
            cookie_file = BytesIO(cookie_json.encode("utf-8"))
            cookie_file.name = "cookies.json"
            await client.send_document(
                chat_id=admin_user_id,
                document=cookie_file,
                caption="Active session cookies",
            )
    except Exception as exc:
        logging.error("Could not deliver cookies to the admin chat", exc_info=exc)
        await status_message.edit_text(
            "Cookies were extracted, but they could not be delivered to your private "
            "admin chat. Start the bot privately and try again."
        )
        return

    if message.chat.id == admin_user_id:
        await status_message.delete()
    else:
        await status_message.edit_text("Cookies were sent to your private admin chat.")


keyboard = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton(
                text="Devloper",
                url="https://t.me/TIGER0054",
            ),
            InlineKeyboardButton(
                text="Repo",
                url="https://github.com/",
            ),
        ],
    ]
)


@bot.on_message(filters.command(["start"]))
async def account_login(bot: Client, m: Message):
    editable = await m.reply_text(f"HELLO I AM TXT DOWNLOADER BOT  [{m.from_user.first_name}](tg://user?id={m.from_user.id})\nPress /txt")


@bot.on_message(filters.command("STOP"))
async def restart_handler(_, m):
    await m.reply_text("**STOPPED**🚦", True)
    os.execl(sys.executable, sys.executable, *sys.argv)



@bot.on_message(filters.command(["txt"]))
async def account_login(bot: Client, m: Message):
    user = m.from_user.id if m.from_user is not None else None
    if user is not None and user not in sudo_users:
        await m.reply("**https://telegra.ph/file/38ce86dda9d6b3572a6a8.jpg", quote=True)
        return
    else:
        editable = await m.reply_text(
            "SEND TXT FILE 🗃️")
    input: Message = await bot.listen(editable.chat.id)
    x = await input.download()
    await input.delete(True)
    logging.info(2333)



    path = f"./downloads/{m.chat.id}"

    try:
       with open(x, "r") as f:
           content = f.read()
       content = content.split("\n")
       links = []
       for i in content:
           links.append(i.split("://", 1))
       os.remove(x)
            # print(len(links)
    except:
           await m.reply_text("Invalid file input.")
           os.remove(x)
           return
    
   
    await editable.edit(f"Total links found are **{len(links)}**\n\nSEND FROM WHERE YOU WANT TO DOWNLOAD INITIAL is **1**")
    input0: Message = await bot.listen(editable.chat.id)
    raw_text = input0.text
    await input0.delete(True)

    await editable.edit("**ENTER BATCH NAME**")
    input1: Message = await bot.listen(editable.chat.id)
    raw_text0 = input1.text
    await input1.delete(True)
    

    await editable.edit("**ENTER RESOLUTION**")
    input2: Message = await bot.listen(editable.chat.id)
    raw_text2 = input2.text
    await input2.delete(True)
    try:
        if raw_text2 == "144":
            res = "256x144"
        elif raw_text2 == "240":
            res = "426x240"
        elif raw_text2 == "360":
            res = "640x360"
        elif raw_text2 == "480":
            res = "854x480"
        elif raw_text2 == "720":
            res = "1280x720"
        elif raw_text2 == "1080":
            res = "1920x1080" 
        else: 
            res = "UN"
    except Exception:
            res = "UN"
    
    

    await editable.edit("**ENTER A HIGHLIGHTER OTHERWISE SEND 👉CO👈 **")
    input3: Message = await bot.listen(editable.chat.id)
    raw_text3 = input3.text
    await input3.delete(True)
    highlighter  = f"️ ⁪⁬⁮⁮⁮"
    if raw_text3 == 'Co':
        MR = highlighter 
    else:
        MR = raw_text3
   
    await editable.edit("NOW SEND THE **THUMB URL**\nEG : ```https://telegra.ph/file/0633f8b6a6f110d34f044.jpg```\n\nor SEND `no`")
    input6 = message = await bot.listen(editable.chat.id)
    raw_text6 = input6.text
    await input6.delete(True)
    await editable.delete()

    thumb = input6.text
    if thumb.startswith("http://") or thumb.startswith("https://"):
        getstatusoutput(f"wget '{thumb}' -O 'thumb.jpg'")
        thumb = "thumb.jpg"
    else:
        thumb == "no"

    if len(links) == 1:
        count = 1
    else:
        count = int(raw_text)

    try:
        for i in range(count - 1, len(links)):

            V = links[i][1].replace("file/d/","uc?export=download&id=").replace("www.youtube-nocookie.com/embed", "youtu.be").replace("?modestbranding=1", "").replace("/view?usp=sharing","") # .replace("mpd","m3u8")
            url = "https://" + V

            if "visionias" in url:
                async with ClientSession() as session:
                    async with session.get(url, headers={'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9', 'Accept-Language': 'en-US,en;q=0.9', 'Cache-Control': 'no-cache', 'Connection': 'keep-alive', 'Pragma': 'no-cache', 'Referer': 'http://www.visionias.in/', 'Sec-Fetch-Dest': 'iframe', 'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Site': 'cross-site', 'Upgrade-Insecure-Requests': '1', 'User-Agent': 'Mozilla/5.0 (Linux; Android 12; RMX2121) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Mobile Safari/537.36', 'sec-ch-ua': '"Chromium";v="107", "Not=A?Brand";v="24"', 'sec-ch-ua-mobile': '?1', 'sec-ch-ua-platform': '"Android"',}) as resp:
                        text = await resp.text()
                        url = re.search(r"(https://.*?playlist.m3u8.*?)\"", text).group(1)

            elif 'videos.classplusapp' in url:
             classplus_token = _required_environment("CLASSPLUS_ACCESS_TOKEN")
             url = requests.get(
                 f'https://api.classplusapp.com/cams/uploader/video/jw-signed-url?url={url}',
                 headers={'x-access-token': classplus_token},
                 timeout=30,
             ).json()['url']

            elif '/master.mpd' in url:
             id =  url.split("/")[-2]
             url =  "https://d26g5bnklkwsh4.cloudfront.net/" + id + "/master.m3u8"

            name1 = links[i][0].replace("\t", "").replace(":", "").replace("/", "").replace("+", "").replace("#", "").replace("|", "").replace("@", "").replace("*", "").replace(".", "").replace("https", "").replace("http", "").strip()
            name = f'{str(count).zfill(3)}) {name1[:60]}'

            if "youtu" in url:
                ytf = f"b[height<={raw_text2}][ext=mp4]/bv[height<={raw_text2}][ext=mp4]+ba[ext=m4a]/b[ext=mp4]"
            else:
                ytf = f"b[height<={raw_text2}]/bv[height<={raw_text2}]+ba/b/bv+ba"

            if "jw-prod" in url:
                cmd = f'yt-dlp -o "{name}.mp4" "{url}"'
            else:
                cmd = f'yt-dlp -f "{ytf}" "{url}" -o "{name}.mp4"'

            try:  
                
                cc = f'**[ 🎬 ] Vid ID :** {str(count).zfill(3)}\n**File Title :** {name1} {res} {MR}.mp4\n**Batch Name :** {raw_text0}\n**Extracted By ➤ ** CRAZY GAMER™ ••'
                cc1 = f'**[ 📕 ] Pdf ID :** {str(count).zfill(3)}\n**File Title :** {name1} {MR}.pdf \n**Batch Name :** {raw_text0}\n**Extracted By ➤ ** CRAZY GAMER™ ••'
                if "drive" in url:
                    try:
                        ka = await helper.download(url, name)
                        copy = await bot.send_document(chat_id=m.chat.id,document=ka, caption=cc1)
                        count+=1
                        os.remove(ka)
                        time.sleep(1)
                    except FloodWait as e:
                        await m.reply_text(str(e))
                        time.sleep(e.x)
                        continue
                
                elif ".pdf" in url:
                    try:
                        cmd = f'yt-dlp -o "{name}.pdf" "{url}"'
                        download_cmd = f"{cmd} -R 25 --fragment-retries 25"
                        os.system(download_cmd)
                        copy = await bot.send_document(chat_id=m.chat.id, document=f'{name}.pdf', caption=cc1)
                        count += 1
                        os.remove(f'{name}.pdf')
                    except FloodWait as e:
                        await m.reply_text(str(e))
                        time.sleep(e.x)
                        continue
                else:
                    Show = f"**Downloading:-**\n\n**Name :-** `{name}\nQuality - {raw_text2}`\n\n**Url :-** `{url}`"
                    prog = await m.reply_text(Show)
                    res_file = await helper.download_video(url, cmd, name)
                    filename = res_file
                    await prog.delete(True)
                    await helper.send_vid(bot, m, cc, filename, thumb, name, prog)
                    count += 1
                    time.sleep(1)

            except Exception as e:
                await m.reply_text(
                    f"**DOWNLOADING FAILED 🥺**\n{str(e)}\n**Name** - {name}\n**Link** - `{url}`"
                )
                continue

    except Exception as e:
        await m.reply_text(e)
    await m.reply_text("BATCH SUCCESSFULLY DOWNLOADED ✅")


if __name__ == "__main__":
    bot.run()
