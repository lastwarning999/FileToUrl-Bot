import asyncio
import os
import time
import random
import string
import urllib.parse
import uuid
import telethon
from aiohttp import web
from telethon import TelegramClient, events

# Please fill this with IP or domain for your server. The IP is used to generate the links for users
Domain = "127.0.0.1"
Port = 8080
if Port != 80:
	Domain += ":" + str(Port)

# These example values won't work. You must get your own api_id and
# api_hash from https://my.telegram.org, under API Development.
api_id = 20401009
api_hash = '6445b43e4af228532e84848d1bb2eb64'
bot_token = '6882280996:AAFHCrV0s8yep4LGtYBXxoQQWMDS4oVy0i0'

# Set the admin of the bot that can use it. These values must be your ID. Get it from @myidbot
admins = {}

# This is the dictionary that is used for downloading files
# The keys are uuid4 of files given to user
# The value is an array with length of three. ary[0] is the file, ary[1] is the expiry date, and ary[2] is filename
files = {}

# A function to clear the old entries of files
async def ClearCache():
	while 1:
		await asyncio.sleep(3600) # You can change this if you want; This is some kind of garbage collector timer.
		for i in list(files):
			if files[i][1] < int(time.time()):
				files.pop(i)

# Generates a random filename for downloading session
def RandomName():
	return ''.join(random.choice(string.ascii_letters) for i in range(8))

# Listen for bot updates
async def StartBot():
	async with TelegramClient('session_name', api_id, api_hash) as client:
		# Get the updates
		@client.on(events.NewMessage)
		async def my_event_handler(event):
			if len(admins) != 0 and event.peer_id.user_id not in admins and event.message.from_id not in admins: # Check admins; If you want to create a public, empty the admin set
				return
			if event.document == None: # Check if they have file
				await event.reply('Please send me a file to convert it into a link. Links are valid for 24 hours')
				return

			# get filename
			filename = ""
			for i in event.document.attributes:
				if isinstance(i,telethon.tl.types.DocumentAttributeFilename):
					filename = urllib.parse.quote(i.file_name)
					break

			uid = str(uuid.uuid4())
			files[uid] = [event.document, int(time.time()) + 86400, filename] # store them

			# send the uid back
			await event.reply("http://" + Domain + "/" + uid + "/" + filename)

		# run the bot
		await client.start(bot_token=bot_token)
		await client.run_until_disconnected()

async def handle(request):
	uid = request.match_info.get('id', '')
	# check the id
	if uid not in files:
		return web.Response(status=404, text="404")
	# get the range header
	r = request.headers.get("range")
	# start a session
	name = RandomName()
	client = TelegramClient(name, api_id, api_hash)
	await client.start(bot_token=bot_token)
	if r == None:
		resp = web.StreamResponse()
		# set headers
		resp.content_length = files[uid][0].size
		resp.content_type = files[uid][0].mime_type
		resp.headers.add("Content-Disposition", 'attachment; filename="' + files[uid][2] + '"')
		resp.headers.add("Accept-Ranges","bytes")
		await resp.prepare(request)
		# normally stream the file
		await client.download_media(message=files[uid][0],file=resp)
	else:
		resp = web.StreamResponse(status=206)
		resp.content_type = files[uid][0].mime_type
		resp.headers.add("Content-Disposition", 'attachment; filename="' + files[uid][2] + '"')
		resp.headers.add("Accept-Ranges","bytes")
		# get the range
		r = r[6:]
		splitRange = r.split("-")
		begin = int(splitRange[0])
		end = files[uid][0].size
		if splitRange[1] != "":
			end = int(splitRange[1])
		toGet = end - begin + 1
		resp.content_length = toGet
		await resp.prepare(request)
		# now get them
		downloaded = 0
		async for chunk in client.iter_download(file=files[uid][0], offset=begin, file_size=files[uid][0].size, request_size=4096): # I cannot change the request-size
			downloaded += len(chunk)
			if downloaded <= toGet:
				await resp.write(chunk)
			else:
				await resp.write(chunk[:toGet % 65536])
				break
		
	# delete the session files
	await resp.write_eof()
	await client.disconnect()
	os.remove(name + ".session")
	return resp

async def RunServer():
	app = web.Application()
	app.add_routes([web.get('/{id}', handle),web.get('/{id}/{filename}', handle)])
	await web._run_app(app, port=Port)

loop = asyncio.get_event_loop()
loop.create_task(ClearCache())
loop.create_task(RunServer())
loop.create_task(StartBot())
loop.run_forever()
