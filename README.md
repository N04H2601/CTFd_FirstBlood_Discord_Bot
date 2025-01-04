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

- **Real-time Monitoring:** Continuously checks your CTFd API for new first bloods.
- **Automated Announcements:** Sends beautifully formatted embeds to your Discord channel.
- **Persistent Storage:** Keeps track of announced first bloods to avoid duplicates using a CSV file.
- **Customizable:** Easily configure API endpoints, Discord channel, and other settings via a `.env` file.
- **Error Handling:** Robust error logging to help you troubleshoot issues effectively.

## Prerequisites

Before you begin, ensure you have met the following requirements:

- **Python 3.8+** installed on your machine. You can download it [here](https://www.python.org/downloads/).
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

   Create a `.env` file in the root directory of the project with the following content:

   ```env
   CTFD_API_KEY="ctfd_abcd123..."
   CTFD_API_URL="https://ctf.example.com/api/v1/challenges"
   DISCORD_CHANNEL_ID=123456789012345678
   DISCORD_BOT_TOKEN="YOUR_DISCORD_BOT_TOKEN"
   MESSAGE_THUMBNAIL="https://ctf.example.com/files/123abc/image.png"
   ```

   - **CTFD_API_KEY:** Your CTFd API key with necessary permissions.
   - **CTFD_API_URL:** The API endpoint for fetching challenges.
   - **DISCORD_CHANNEL_ID:** The ID of the Discord channel where announcements will be sent.
     - To get the channel ID, enable Developer Mode in Discord (User Settings > Advanced > Developer Mode), right-click the channel, and select **Copy ID**.
   - **DISCORD_BOT_TOKEN:** The token you saved from the Discord Developer Portal.
   - **MESSAGE_THUMBNAIL:** URL of the image to be used as the thumbnail in the embed messages.

## Usage

1. **Run the Bot**

   ```bash
   python main.py
   ```

   Upon successful launch, you should see a message like:

   ```
   Logged in as YourBotName#1234
   ```

2. **Bot Behavior**

   - The bot will check for new first bloods every 5 seconds (configurable via `CHECK_INTERVAL`).
   - When a first blood is detected, it will send an embed message to the specified Discord channel with details about the challenge, team, and time solved.

## Customization

- **Check Interval:** Modify the `CHECK_INTERVAL` variable in `main.py` to change how frequently the bot checks for new first bloods.

  ```python
  CHECK_INTERVAL = 5  # Seconds between each check for new first bloods
  ```

- **Embed Message:** Customize the appearance and content of the embed messages by editing the `embed` object in the `check_first_blood` function.

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
