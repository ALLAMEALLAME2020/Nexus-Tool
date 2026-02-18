# 💬 Nexus Chat

A terminal-based multi-user chat app built in pure Python. No web server, no fancy framework — just raw sockets, threads, and a slick CLI interface powered by [Rich](https://github.com/Textualize/rich).

You run one server, connect as many clients as you want, and chat in rooms or DM people privately. It saves everything to a JSON file so nothing gets lost when you restart.

---

## what it looks like

```
  ███╗   ██╗███████╗██╗  ██╗██╗   ██╗███████╗
  ████╗  ██║██╔════╝╚██╗██╔╝██║   ██║██╔════╝
  ██╔██╗ ██║█████╗   ╚███╔╝ ██║   ██║███████╗
  ██║╚██╗██║██╔══╝   ██╔██╗ ██║   ██║╚════██║
  ██║ ╚████║███████╗██╔╝ ██╗╚██████╔╝███████║

  alex@#general > hey everyone!
  ⚡ sara joined #general
  sara: hey! finally got this running lol
  ✉ DM ← mike: yo did you see the new room?
```

Colored messages, room headers, user panels, DM notifications — all in your terminal.

---

## features

- **accounts** — register/login with a username and password (passwords are hashed, not stored plain)
- **chat rooms** — multiple rooms, you can create your own or join the defaults
- **private messages** — DM anyone, even if they're offline (it saves the message)
- **chat history** — last 50 messages load when you join a room, or fetch more with a command
- **user profiles** — set a bio/status, look up other users with `/whois`
- **persistent storage** — everything is saved to a local JSON file, survives server restarts
- **pretty terminal UI** — built with Rich, so it actually looks good instead of just raw text dumps

---

## getting started

### requirements

- Python 3.8 or newer
- One dependency:

```bash
pip install rich
```

That's it. No database, no config files, nothing else.

### running it

**1. Start the server** (do this once, on the machine that will host the chat):

```bash
python server.py
```

The server starts on port `9999` by default and creates a `nexus_data.json` file to store users, rooms, and message history.

**2. Connect a client** (everyone who wants to chat runs this):

```bash
python client.py
```

To connect to a remote server instead of localhost:

```bash
python client.py 192.168.1.50 9999
```

When you first connect, you'll be asked to login or register. Pick a username and password and you're in.

---

## commands

Once you're in, here's everything you can do:

| command | what it does |
|---|---|
| `/join <room>` | switch to a different room |
| `/create <room> [topic]` | create a new room (you become the owner) |
| `/delete <room>` | delete a room you own |
| `/rooms` | see all rooms, how many people are in each |
| `/online` | list everyone currently connected |
| `/dm <user> <message>` | send a private message to someone |
| `/dms <user>` | read your DM history with that person |
| `/history [room] [n]` | load past messages from a room |
| `/whois <user>` | see someone's profile, bio, and what room they're in |
| `/bio <text>` | set your own bio or status message |
| `/clear` | clear the screen |
| `/help` | show the full command list |
| `/quit` | disconnect and exit |

---

## project structure

```
nexus-chat/
├── server.py          # run this on the host machine
├── client.py          # run this to connect and chat
├── nexus_data.json    # auto-created, stores all users/rooms/history
└── nexus_server.log   # auto-created, server logs
```

Two files. That's the whole project.

---

## how it works (roughly)

The server uses raw TCP sockets and spawns a new thread for each connected client. Messages are JSON objects sent over the wire with a newline delimiter. The client has two threads running — one that listens for incoming packets from the server and prints them, and one that sits in a loop reading your input and sending commands.

Everything gets saved to `nexus_data.json` — users, rooms, message history (capped at 500 per room so it doesn't grow forever), and DM history (capped at 200 per conversation).

Passwords are SHA-256 hashed before being stored. Not production-grade cryptography, but fine for a personal/LAN chat server.

---

## default rooms

Three rooms exist out of the box:

- `#general` — everyone lands here first
- `#random` — for whatever
- `#tech` — tech talk

You can create as many rooms as you want. Default rooms can't be deleted.

---

## running on a local network

Want to use this to chat with people on the same WiFi?

1. Find your local IP — something like `192.168.x.x` (run `ipconfig` on Windows or `ifconfig`/`ip a` on Linux/Mac)
2. Start the server on your machine: `python server.py`
3. Share your IP with whoever wants to connect
4. They run: `python client.py YOUR_IP 9999`

As long as your firewall allows port 9999, it'll work.

---

## known limitations

- No end-to-end encryption — don't use this for anything sensitive
- Single server, no clustering or redundancy
- If the server crashes mid-write, `nexus_data.json` could get corrupted (rare but possible)
- The JSON file will get large if you run this for a long time with heavy traffic — there's a cap on history per room but no overall size limit

---

## potential improvements

If you want to extend this, some ideas:

- swap JSON storage for SQLite
- add TLS for encrypted connections
- rate limiting to prevent spam
- admin roles / moderation commands
- file sharing or image previews
- a web frontend that connects to the same server

---

## license

Do whatever you want with this. MIT.

---

## contributing

PRs welcome. If you find a bug or have an idea, open an issue. If you just want to say the project is cool, a star works too ⭐
