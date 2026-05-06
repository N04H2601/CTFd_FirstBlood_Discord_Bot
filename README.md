# CTFd First Blood Discord Bot

A Discord bot that monitors your CTFd platform for first bloods on challenges and announces them in your specified Discord channel.

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgements](#acknowledgements)

## Features

- **Real-time Monitoring:** Continuously checks your CTFd API for first blood changes.
- **Automated Announcements:** Sends beautifully formatted embeds to your Discord channel.
- **Persistent Storage:** Keeps track of announced first bloods in SQLite to avoid duplicates and retry failed announcements.
- **Solve Reconciliation:** Re-checks already announced challenges so a replacement first blood is announced if solves are removed and a new earliest solve appears.
- **CTFd Resilience:** Handles CTFd being down, paused, not started, or temporarily unreachable without crashing.
- **Customizable:** Easily configure API endpoints, Discord channel, and other settings via a `.env` file.
- **Error Handling:** Robust error logging to help you troubleshoot issues effectively.

## Prerequisites

Before you begin, ensure you have met the following requirements:

- **Python 3.10+** installed on your machine. You can download it [here](https://www.python.org/downloads/).
- **Discord Account** and a **Discord Server** where you have permission to add bots.
- **CTFd Platform** with API access.

## Installation

1. **Clone the Repository**

   ```bash
   git clone https://github.com/N04H2601/CTFd_FirstBlood_Discord_Bot.git
   cd CTFd_FirstBlood_Discord_Bot
   ```

2. **Create a Virtual Environment (Optional but Recommended)**

   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install Dependencies**

   ```bash
   pip install -r requirements.txt
   ```

## Configuration

1. **Create a Discord Bot**

   - Go to the [Discord Developer Portal](https://discord.com/developers/applications).
   - Click on **New Application** and provide a name.
   - Navigate to the **Bot** section and click **Add Bot**.
   - **Save the Bot Token**; you'll need it for the `.env` file.
   - Under **Privileged Gateway Intents**, enable the necessary intents based on your bot's requirements.

2. **Invite the Bot to Your Server**

   - Go to the **OAuth2** section.
   - Under **Scopes**, select `bot`.
   - Under **Bot Permissions**, select the permissions your bot needs (e.g., `Send Messages`, `Embed Links`).
   - Copy the generated URL and open it in your browser to invite the bot to your Discord server.

3. **Set Up the `.env` File**

   Create a `.env` file in the root directory of the project. You can start from `.env.example`:

   ```env
   CTFD_API_KEY="ctfd_abcd123..."
   CTFD_API_URL="https://ctf.example.com"
   DISCORD_CHANNEL_ID=123456789012345678
   DISCORD_BOT_TOKEN="YOUR_DISCORD_BOT_TOKEN"
   MESSAGE_THUMBNAIL="https://ctf.example.com/files/123abc/image.png"
   CHECK_INTERVAL_SECONDS=5
   ANNOUNCE_DELAY_SECONDS=5
   FIRST_BLOOD_DB_PATH="first_bloods.sqlite3"
   DISPLAY_TIMEZONE="Europe/Paris"
   ```

   - **CTFD_API_KEY:** Your CTFd API key with necessary permissions.
   - **CTFD_API_URL:** Your CTFd base URL. The bot also accepts `https://ctf.example.com/api/v1` and `https://ctf.example.com/api/v1/challenges`.
   - **DISCORD_CHANNEL_ID:** The ID of the Discord channel where announcements will be sent.
     - To get the channel ID, enable Developer Mode in Discord (User Settings > Advanced > Developer Mode), right-click the channel, and select **Copy ID**.
   - **DISCORD_BOT_TOKEN:** The token you saved from the Discord Developer Portal.
   - **MESSAGE_THUMBNAIL:** URL of the image to be used as the thumbnail in the embed messages.
   - **CHECK_INTERVAL_SECONDS:** How often the bot polls CTFd. Defaults to `5`.
   - **ANNOUNCE_DELAY_SECONDS:** Delay between Discord first blood messages. Defaults to `5`.
   - **FIRST_BLOOD_DB_PATH:** SQLite state database path. Defaults to `first_bloods.sqlite3`.
   - **DISPLAY_TIMEZONE:** Timezone used in Discord embeds. Defaults to `Europe/Paris`.

   Optional variables:

   ```env
   SOLVE_FETCH_CONCURRENCY=8
   REQUEST_TIMEOUT_SECONDS=15
   CTFD_SITE_PASSWORD="optional_site_password_cookie"
   ```

## Usage

1. **Run the Bot**

   ```bash
   python3 main.py
   ```

   Upon successful launch, you should see a message like:

   ```
   Connecte a Discord en tant que YourBotName#1234
   ```

2. **Bot Behavior**

   - The bot checks CTFd every 5 seconds by default.
   - Discord announcements are queued and sent one by one with a 5 second delay by default.
   - The SQLite database stores the current first solve fingerprint per challenge. This prevents duplicate announcements and lets the bot detect a new first blood if the original solve is deleted.
   - If `announced_first_bloods.csv` exists from an older version, it is migrated once into SQLite. Existing CSV entries are treated as already announced to avoid duplicate announcements.
   - If CTFd is down, paused, not started, or returns a non-200 response, the bot logs the problem and retries on the next interval.
   - When a first blood is detected, it will send an embed message to the specified Discord channel with details about the challenge, team, and time solved.

## Customization

- **Check Interval:** Set `CHECK_INTERVAL_SECONDS` in `.env` to change how frequently the bot checks for first bloods.

  ```env
  CHECK_INTERVAL_SECONDS=5
  ```

- **Embed Message:** Customize the appearance and content of the embed messages by editing `build_announcement_embed` in `main.py`.

## Verification

Run the local checks before deploying:

```bash
python3 -m py_compile main.py
python3 -m unittest discover -v
```

## Contributing

Contributions are welcome! If you have suggestions or find issues, please open an [issue](https://github.com/N04H2601/CTFd_FirstBlood_Discord_Bot/issues) or submit a [pull request](https://github.com/N04H2601/CTFd_FirstBlood_Discord_Bot/pulls).

### Steps to Contribute

1. **Fork the Repository**

2. **Create a Feature Branch**

   ```bash
   git checkout -b feature/YourFeature
   ```

3. **Commit Your Changes**

   ```bash
   git commit -m "Add Your Feature"
   ```

4. **Push to the Branch**

   ```bash
   git push origin feature/YourFeature
   ```

5. **Open a Pull Request**

---

*Happy Hacking! 🩸*
