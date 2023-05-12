# top-level module include hack for shared :|
import sys
from io import BytesIO

sys.path.append("../..")

import asyncio
import logging

import config
import disnake
from aiohttp import web

from messages import commands, events
from messages.broker import Broker
from messages.bus import MessageBus
from shared.log import logging_config
from shared.utils import timer

CHUNK_SIZE = 4 * 1024 * 1024

logging_config(config.DEBUG)
log = logging.getLogger(__name__)

tokens = set()
client = disnake.AutoShardedClient(intents=disnake.Intents.none())
bus = MessageBus()
broker = Broker(
    bus=bus,
    publish_commands={
        commands.ValidateUpload,
    },
    consume_events={
        events.UploadValidated,
    },
)


async def validated_upload(job_id: str, values: events.UploadValidated, binary_data: bytes):
    log.info("Uploading job %s", job_id)

    channel_id = values.channel_id
    user_id = values.user_id

    # strip backticks because of how we display this string
    video_title = values.video_title.replace("`", "")

    channel = await client.fetch_channel(channel_id)

    buttons = list()

    buttons.append(
        disnake.ui.Button(
            style=disnake.ButtonStyle.secondary,
            label="How to use the bot",
            emoji="\N{Black Question Mark Ornament}",
            custom_id="howtouse",
        )
    )

    if config.DISCORD_INVITE_URL is not None:
        buttons.append(
            disnake.ui.Button(
                style=disnake.ButtonStyle.url,
                label="Discord",
                emoji=":discord:1099362254731882597",
                url=config.DISCORD_INVITE_URL,
            )
        )

    if config.GITHUB_URL is not None:
        buttons.append(
            disnake.ui.Button(
                style=disnake.ButtonStyle.url,
                label="GitHub",
                emoji=":github:1099362911077544007",
                url=config.GITHUB_URL,
            )
        )

    buttons.append(
        disnake.ui.Button(
            style=disnake.ButtonStyle.secondary,
            label="Donate",
            emoji="\N{Hot Beverage}",
            custom_id="donatebutton",
        )
    )

    b = BytesIO(binary_data)

    await channel.send(
        content=f"<@{user_id}> `{video_title}`",
        file=disnake.File(fp=b, filename=job_id + ".mp4"),
        allowed_mentions=disnake.AllowedMentions(users=[disnake.Object(id=user_id)]),
        components=disnake.ui.ActionRow(*buttons),
    )


async def upload(request: web.Request) -> web.Response:
    args = request.query

    job_id = args.get("job_id")
    token = request.headers.get("Authorization")

    if job_id is None:
        return web.Response(status=400)
    if token is None:
        return web.Response(status=401)

    task = asyncio.create_task(
        bus.wait_for(events.UploadValidated, check=lambda e: e.job_id == job_id, timeout=32.0)
    )

    await broker.publish(commands.ValidateUpload(job_id, token))

    validated: events.UploadValidated = await task

    if validated is None:
        await broker.publish(events.UploaderFailure(job_id, reason="Unable to upload."))
        return web.Response(status=503)

    if not validated.authorized:
        await broker.publish(events.UploaderFailure(job_id, reason="Upload failed."))
        return web.Response(status=401)

    await validated_upload(job_id, validated, await request.read())

    await broker.publish(events.UploaderSuccess(job_id))
    return web.Response(status=200)


async def main():
    logging.getLogger("aiormq").setLevel(logging.INFO)

    asyncio.create_task(client.start(config.BOT_TOKEN))
    await client.wait_until_ready()
    await broker.start(config.RABBITMQ_HOST, prefetch_count=1)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    app = web.Application(client_max_size=30 * 1024 * 1024)
    app.add_routes([web.post("/upload", upload)])
    web.run_app(app, host="0.0.0.0", port=9000, loop=loop)
