# answerrouter-bot

A Telegram auto-reply bot that answers in your personal chats on your behalf via the Telegram Business "Chatbots" feature. Writes in your style, reads text and photos, runs on free OpenRouter models.

## Features
- Replies as you in every chat where the bot is connected as a chatbot
- Multimodal: reads text and photos (photos are processed in RAM, never written to disk)
- Personalization: a persona prompt with real message examples (see prompt.txt), plus style-extraction-prompt.txt - a meta-prompt for building a style prompt from your chat export
- Prompt and model management commands right from the chat (owner only)
- Context: last 10+10 messages, kept in RAM only
- Live log via stdout (convenient in tmux)

## Requirements
- Python 3.8+ (standard library only, no pip installs)
- A VPS/PC that can reach Telegram (use an HTTP proxy if it is blocked in your region)
- Telegram Premium on the owner's account
- An openrouter.ai account (free registration)

## Setup

1. Create a bot with [@BotFather](https://t.me/BotFather) (/newbot). Make sure Business Mode is allowed (BotFather -> /mybots -> Bot Settings -> Business Mode).

2. Connect the bot to your account: Telegram -> Settings -> Business -> Chatbots -> add your bot and grant access to the chats you want.

3. Get an OpenRouter key: https://openrouter.ai/settings/keys

4. Unpack the archive (or clone this repo) and create .env:

```
cp .env.example .env
nano .env
```

Fill it in:

```
OPENROUTER_API_KEY=sk-or-v1-...   # OpenRouter key
TELEGRAM_BOT_TOKEN=123456:...     # token from BotFather
PROXY=http://127.0.0.1:10809      # HTTP proxy for Telegram; leave empty if not needed
```

5. Put your Telegram id into bot.py (this unlocks the commands):

```
OWNER_IDS = {712783140}   # replace with your numeric id
```

You can get your id from @userinfobot.

6. Run:

```
python3 bot.py
```

Run in the background:

```
tmux new-session -d -s answerrouter "python3 bot.py"
tmux capture-pane -t answerrouter -p   # view the log
```

## Commands (owner's private chat with the bot only)

| Command | Action |
|---|---|
| /prompt | send the current prompt as a file |
| /prompt text | replace the prompt with short text |
| /promptadd text | append text to the end of the prompt |
| /promptset + .txt file | replace the prompt with the file contents |
| /model | show the current model |
| /model name | switch the model (validated with a test request first) |
| /help | show help |

## How to teach the bot to write like you

1. Export your chat history (Telegram Desktop -> Settings -> Export data)
2. Send the export file together with the text of style-extraction-prompt.txt to any powerful LLM
3. Save the resulting prompt to a file and load it into the bot with /promptset

## Security
- .env with keys is not stored in the repo and never included in archives
- Prompt-injection defense: the contact's text is wrapped in <message> tags; the system prompt forbids following instructions from inside them
- Photos and voice notes are never written to disk

## Files
- bot.py - the whole bot in one file
- prompt.txt - the system prompt (role + style + examples)
- style-extraction-prompt.txt - meta-prompt for building a style prompt from a chat export
- .env.example - config template
