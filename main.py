# -*- coding: utf-8 -*-
# Import the required libraries
import discord
from discord.ext import tasks, commands
from datetime import datetime
import aiohttp
from datetime import timedelta
import csv
import os
from dotenv import load_dotenv

# Configuration variables are loaded from a `.env` file in the same directory as the script.
load_dotenv()  # Load environment variables from .env file
CTFD_API_KEY = os.getenv("CTFD_API_KEY")  # Get the CTFd API key from the environment
CTFD_API_URL = os.getenv("CTFD_API_URL")  # Get the CTFd API URL from the environment
DISCORD_CHANNEL_ID = int(
    os.getenv("DISCORD_CHANNEL_ID")
)  # Get the Discord channel ID from the environment
DISCORD_BOT_TOKEN = os.getenv(
    "DISCORD_BOT_TOKEN"
)  # Get the Discord bot token from the environment
MESSAGE_THUMBNAIL = os.getenv(
    "MESSAGE_THUMBNAIL"
)  # Get the message thumbnail from the environment
CHECK_INTERVAL = 5  # Seconds between each check for new first bloods

intents = discord.Intents.default()
client = commands.Bot(command_prefix="!", intents=intents)

# CSV file to store IDs of challenges that have already had a first blood announcement
FIRST_BLOOD_FILE = "announced_first_bloods.csv"

# Keep track of which challenges have been announced (in-memory)
first_blood_announced = set()


def load_first_bloods_from_csv():
    """
    Load previously announced challenge IDs from a CSV file into the in-memory set.
    """
    if os.path.isfile(FIRST_BLOOD_FILE):
        with open(FIRST_BLOOD_FILE, mode="r", encoding="utf-8") as csv_file:
            reader = csv.reader(csv_file)
            for row in reader:
                if row:
                    challenge_id_str = row[0].strip()
                    if challenge_id_str.isdigit():
                        first_blood_announced.add(int(challenge_id_str))


def save_first_blood_to_csv(challenge_id):
    """
    Append a newly announced challenge ID to the CSV file.
    """
    with open(FIRST_BLOOD_FILE, mode="a", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow([challenge_id])


async def fetch_challenge_list():
    """
    Fetch the list of challenges from the CTFd API.
    Returns a list of challenge objects, or an empty list on failure.
    """
    headers = {
        "Authorization": "Token " + CTFD_API_KEY,
        "Content-Type": "application/json",
    }
    url = CTFD_API_URL
    try:
        async with client.session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                return data.get("data", [])
            else:
                print(f"[ERROR] Failed to fetch challenges. Status: {response.status}")
                return []
    except Exception as e:
        print(f"[ERROR] Exception while fetching challenge list: {e}")
        return []


async def fetch_solves_for_challenge(challenge_id):
    """
    Fetch the solves for a given challenge from the CTFd API.
    Returns a list of solve objects (sorted from earliest to latest) or an empty list on failure.
    """
    headers = {
        "Authorization": "Token " + CTFD_API_KEY,
        "Content-Type": "application/json",
    }
    solves_url = f"{CTFD_API_URL}/{challenge_id}/solves"
    try:
        async with client.session.get(solves_url, headers=headers) as response:
            if response.status == 200:
                solves_data = await response.json()
                # The data might already be in chronological order (earliest first)
                return solves_data.get("data", [])
            else:
                print(
                    f"[ERROR] Failed to fetch solves for challenge {challenge_id}. "
                    f"Status: {response.status}"
                )
                return []
    except Exception as e:
        print(
            f"[ERROR] Exception while fetching solves for challenge {challenge_id}: {e}"
        )
        return []


@tasks.loop(seconds=CHECK_INTERVAL)
async def check_first_blood():
    """
    Periodically check each visible challenge from the CTFd API.
    Announce the first blood if not already announced.
    """
    channel = client.get_channel(DISCORD_CHANNEL_ID)
    # Fetch the current list of challenges (including new or newly un-hidden ones)
    current_challenge_list = await fetch_challenge_list()

    # Iterate over the challenges
    for challenge in current_challenge_list:
        challenge_id = challenge["id"]
        challenge_name = challenge["name"]

        # If we've already announced this challenge's first blood, skip it
        if challenge_id in first_blood_announced:
            continue

        # Fetch the solves for this challenge
        solves = await fetch_solves_for_challenge(challenge_id)

        # If there are solves, the first in the list is presumably the first blood
        if solves:
            first_blood = solves[0]
            user = first_blood.get("name", "Inconnue")
            # Calculate time solved, adjusting for offset (e.g., +1 hour)
            time_solved = (
                datetime.strptime(first_blood["date"], "%Y-%m-%dT%H:%M:%S.%fZ")
                + timedelta(hours=1)
            ).strftime("%d/%m/%Y %H:%M:%S")

            embed = discord.Embed(
                title="🩸 First Blood! 🩸",
                description=(
                    f"**Challenge :** ``{challenge_name}``\n"
                    f"**Équipe :** {user}\n"
                    f"**Résolu :** {time_solved}"
                ),
                color=0xFF0000,
            )
            embed.set_thumbnail(url=MESSAGE_THUMBNAIL)
            await channel.send(embed=embed)

            # Mark this challenge as announced in memory
            first_blood_announced.add(challenge_id)
            # Also append it to the CSV file
            save_first_blood_to_csv(challenge_id)


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    # Create a shared aiohttp session for all requests
    client.session = aiohttp.ClientSession()

    # Load any previously announced first bloods from the CSV before starting the loop
    load_first_bloods_from_csv()

    # Start the task loop
    check_first_blood.start()


@client.event
async def on_disconnect():
    """
    Clean up the aiohttp session when the bot disconnects.
    """
    if hasattr(client, "session"):
        await client.session.close()


client.run(DISCORD_BOT_TOKEN)
