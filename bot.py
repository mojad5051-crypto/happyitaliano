#!/usr/bin/env python3
import os
import asyncio
from datetime import datetime
from aiohttp import web
import discord
from discord import ui
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN", "test-token")
PORT = int(os.getenv("PORT", "8080"))

# Application workflow IDs from the request:
APPLICATION_CHANNEL_ID = 1497630261607792792
APPLICATION_REVIEW_ROLE_ID = 1496970697430536489
APPLICATION_LOG_CHANNEL_ID = 1497628703381917827
APPLICATION_ACCEPT_ROLE_ID = 1496970734919094303

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}

async def handle_health(request: web.Request) -> web.Response:
    return web.Response(text="OK", headers=CORS_HEADERS)

class FloridaRPBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
        self.config = {
            "logo_url": "https://example.com/logo.png",  # placeholder
        }

bot = FloridaRPBot()

class ApplicationReviewView(ui.View):
    def __init__(self, application_data: dict):
        super().__init__(timeout=None)
        self.application_data = application_data
        self.processed = False

    async def disable_buttons(self):
        for child in self.children:
            child.disabled = True

    async def handle_decision(self, interaction: discord.Interaction, accepted: bool):
        if self.processed:
            await interaction.response.send_message("This application has already been processed.", ephemeral=True)
            return

        if not reviewer_allowed(interaction.user):
            await interaction.response.send_message("You are not authorized to review applications.", ephemeral=True)
            return

        self.processed = True
        await self.disable_buttons()
        await interaction.response.defer(ephemeral=True)
        await interaction.message.edit(view=self)

        decision = "Accepted" if accepted else "Rejected"
        reviewer = interaction.user
        application = self.application_data

        guild = interaction.guild
        member = None
        role_assigned = False
        if guild:
            try:
                member = guild.get_member(int(application["discordUserId"]))
                if not member:
                    member = await guild.fetch_member(int(application["discordUserId"]))
            except Exception:
                member = None

        if accepted and member is not None:
            try:
                accepted_role = guild.get_role(APPLICATION_ACCEPT_ROLE_ID)
                if accepted_role is not None:
                    await member.add_roles(accepted_role, reason="Moderator application accepted")
                    role_assigned = True
            except Exception as error:
                print(f"Failed to assign role: {error}")

        await send_applicant_dm(application, accepted, reviewer, role_assigned)
        await log_application_decision(application, accepted, reviewer, role_assigned, member)

        await interaction.followup.send(f"Application {decision.lower()} and applicant notified.", ephemeral=True)

    @ui.button(label="Accept", style=discord.ButtonStyle.success, custom_id="application_accept")
    async def accept_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.handle_decision(interaction, accepted=True)

    @ui.button(label="Deny", style=discord.ButtonStyle.danger, custom_id="application_deny")
    async def deny_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.handle_decision(interaction, accepted=False)


def reviewer_allowed(user: discord.Member) -> bool:
    if not isinstance(user, discord.Member):
        return False
    if user.guild_permissions.manage_roles or user.guild_permissions.administrator:
        return True
    return any(role.id == APPLICATION_REVIEW_ROLE_ID for role in user.roles)


def validate_application_payload(data: dict) -> tuple[bool, str]:
    required = [
        "robloxUsername", "discordUserId", "discordUsername", "age",
        "rdm", "vdm", "nlr", "nitrp", "aama",
        "scenario1", "scenario2", "scenario3", "scenario4",
        "aiAgreement", "rushAgreement", "additional", "submittedAt"
    ]

    for field in required:
        if field not in data:
            return False, f"Missing required field: {field}"

    discord_id = str(data["discordUserId"]).strip()
    if not discord_id.isdigit() or not (17 <= len(discord_id) <= 20):
        return False, "Discord User ID must be a numeric ID with 17-20 digits."

    try:
        age = int(data["age"])
        if age < 13:
            return False, "Applicant must be at least 13 years old."
    except ValueError:
        return False, "Age must be a valid number."

    return True, ""


def make_application_embed(data: dict) -> discord.Embed:
    embed = discord.Embed(
        title="New Moderator Application",
        description="A new application has been submitted and is ready for review.",
        color=0x2F80ED,
        timestamp=datetime.utcnow()
    )

    embed.add_field(name="Roblox Username", value=data["robloxUsername"], inline=True)
    embed.add_field(name="Discord Username", value=data["discordUsername"], inline=True)
    embed.add_field(name="Discord ID", value=data["discordUserId"], inline=True)
    embed.add_field(name="Age", value=str(data["age"]), inline=True)
    embed.add_field(name="AI Agreement", value=str(data["aiAgreement"]), inline=True)
    embed.add_field(name="Rush Agreement", value=str(data["rushAgreement"]), inline=True)
    embed.add_field(name="Submitted At", value=data["submittedAt"], inline=False)
    embed.add_field(name="RDM", value=data["rdm"], inline=False)
    embed.add_field(name="VDM", value=data["vdm"], inline=False)
    embed.add_field(name="NLR", value=data["nlr"], inline=False)
    embed.add_field(name="NITRP", value=data["nitrp"], inline=False)
    embed.add_field(name="AA/MA", value=data["aama"], inline=False)
    embed.add_field(name="Scenario 1", value=data["scenario1"], inline=False)
    embed.add_field(name="Scenario 2", value=data["scenario2"], inline=False)
    embed.add_field(name="Scenario 3", value=data["scenario3"], inline=False)
    embed.add_field(name="Scenario 4", value=data["scenario4"], inline=False)
    embed.add_field(name="Additional Info", value=data["additional"] or "No additional info provided.", inline=False)

    embed.set_footer(text=f"Review role: <@&{APPLICATION_REVIEW_ROLE_ID}>")
    return embed


def make_decision_embed(data: dict, accepted: bool, reviewer: discord.Member, role_assigned: bool) -> discord.Embed:
    if accepted:
        title = "Application Accepted"
        description = (
            "Congratulations! Your moderator application has been accepted. "
            "A staff member will follow up with you soon."
        )
        color = 0x2ECC71
    else:
        title = "Application Decision"
        description = (
            "Thank you for applying. After review, your application was not accepted at this time. "
            "You are welcome to improve your application and reapply later."
        )
        color = 0xE74C3C

    embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.utcnow())
    embed.add_field(name="Applicant", value=data["discordUsername"], inline=True)
    embed.add_field(name="Reviewer", value=reviewer.display_name, inline=True)
    embed.add_field(name="Decision", value="Accepted" if accepted else "Denied", inline=True)
    if accepted:
        embed.add_field(name="Role Granted", value="Yes" if role_assigned else "No (member not found or role assignment failed)", inline=False)
        embed.add_field(name="Next Step", value="Please join the staff server and check your messages for next instructions.", inline=False)
    else:
        embed.add_field(name="Next Step", value="Review the rules and consider applying again later.", inline=False)

    embed.set_footer(text="Florida State Roleplay Staff Application")
    return embed


def make_log_embed(data: dict, accepted: bool, reviewer: discord.Member, role_assigned: bool, member: discord.Member | None) -> discord.Embed:
    status_text = "Accepted" if accepted else "Rejected"
    color = 0x2ECC71 if accepted else 0xE74C3C
    embed = discord.Embed(
        title=f"Application {status_text}",
        description=f"Application review completed by {reviewer.mention}",
        color=color,
        timestamp=datetime.utcnow()
    )

    embed.add_field(name="Applicant", value=data["discordUsername"], inline=True)
    embed.add_field(name="Discord ID", value=data["discordUserId"], inline=True)
    embed.add_field(name="Reviewer", value=reviewer.mention, inline=True)
    embed.add_field(name="Decision", value=status_text, inline=True)
    embed.add_field(name="Role Assigned", value="Yes" if role_assigned else "No", inline=True)
    embed.add_field(name="Member in Guild", value="Yes" if member else "No", inline=True)
    embed.add_field(name="Application Submitted", value=data["submittedAt"], inline=False)
    return embed


async def send_applicant_dm(application: dict, accepted: bool, reviewer: discord.Member, role_assigned: bool):
    try:
        user = await bot.fetch_user(int(application["discordUserId"]))
        embed = make_decision_embed(application, accepted, reviewer, role_assigned)
        await user.send(embed=embed)
    except Exception as error:
        print(f"Failed to DM applicant: {error}")


async def log_application_decision(application: dict, accepted: bool, reviewer: discord.Member, role_assigned: bool, member: discord.Member | None):
    channel = bot.get_channel(APPLICATION_LOG_CHANNEL_ID)
    if channel is None:
        print("Log channel not found")
        return
    embed = make_log_embed(application, accepted, reviewer, role_assigned, member)
    await channel.send(embed=embed)


async def handle_apply(request: web.Request) -> web.Response:
    if request.method == "OPTIONS":
        return web.Response(status=204, headers=CORS_HEADERS)

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"success": False, "error": "Invalid JSON payload."}, status=400, headers=CORS_HEADERS)

    valid, message = validate_application_payload(data)
    if not valid:
        return web.json_response({"success": False, "error": message}, status=400, headers=CORS_HEADERS)

    review_channel = bot.get_channel(APPLICATION_CHANNEL_ID)
    if review_channel is None:
        return web.json_response({"success": False, "error": "Review channel not available."}, status=500, headers=CORS_HEADERS)

    embed = make_application_embed(data)
    view = ApplicationReviewView(data)
    try:
        await review_channel.send(
            content=f"<@&{APPLICATION_REVIEW_ROLE_ID}> A new moderator application has been submitted.",
            embed=embed,
            view=view
        )
    except Exception as error:
        print(f"Failed to send review message: {error}")
        return web.json_response({"success": False, "error": "Unable to post application to review channel."}, status=500, headers=CORS_HEADERS)

    return web.json_response({"success": True}, headers=CORS_HEADERS)


@bot.event
async def on_ready():
    print(f"Bot ready: {bot.user} (ID: {bot.user.id})")
    print(f"Listening for applications on /apply and Discord review interactions.")
    
    # Start web server
    app = web.Application()
    app.add_routes([
        web.post("/apply", handle_apply),
        web.options("/apply", handle_apply),
        web.get("/health", handle_health),
    ])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"Web server listening on 0.0.0.0:{PORT}")



async def start_http_server() -> web.AppRunner:
    app = web.Application()
    app.router.add_route("POST", "/apply", handle_apply)
    app.router.add_route("OPTIONS", "/apply", handle_apply)
    app.router.add_get("/", handle_health)
    app.router.add_get("/health", handle_health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"HTTP server running on port {PORT}")
    return runner


async def main():
    runner = await start_http_server()
    try:
        await bot.start(TOKEN)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    bot.run(TOKEN)
