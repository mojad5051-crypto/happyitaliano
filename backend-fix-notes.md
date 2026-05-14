# Backend Fix Notes

## Observed problem
The GitLab backend repository at `gitlab.com/mojad5051/mojad-bot` contains a syntactically invalid `cogs/applications.py` module. This will crash the bot on startup and prevent the Railway service from running.

## Recommended backend fixes
1. Fix `cogs/applications.py` so the `ApplicationModal` class includes properly defined fields and an `on_submit` method instead of executing `await` statements at class scope.
2. Add CORS headers to all `/apply` responses in `bot.py` so browser requests from GitHub Pages do not get blocked.
3. Ensure `DISCORD_TOKEN` and required channel/role environment variables are configured in Railway.
4. Confirm the Railway service is using the correct backend repository and not a stale GitHub Pages static deploy.

## Suggested `bot.py` CORS patch
In `bot.py`, add a helper and use it for both POST and OPTIONS responses:

```python
from aiohttp import web

# add after imports
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type"
}

# inside handle_apply, return responses like:
return web.json_response({"success": True}, headers=CORS_HEADERS)

# inside handle_options, return:
return web.Response(status=204, headers=CORS_HEADERS)
```

## Suggested `cogs/applications.py` structure
The file should look like:

```python
import discord
from discord.ext import commands

class ApplicationModal(discord.ui.Modal, title="Staff Application"):
    age = discord.ui.TextInput(...)
    experience = discord.ui.TextInput(...)
    availability = discord.ui.TextInput(...)
    motivation = discord.ui.TextInput(...)

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        db = self.bot.db
        application_id = db.add_application(...)
        # send embed and response

class ApplicationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def open_application_modal(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ApplicationModal(self.bot))

    async def open_verify_modal(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(VerifyRobloxModal(self.bot))


def setup(bot: commands.Bot) -> None:
    bot.add_cog(ApplicationCog(bot))
```
