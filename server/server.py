#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║          NEXUS CHAT SERVER  v1.0                         ║
║          Multi-user Terminal Chat Application            ║
╚══════════════════════════════════════════════════════════╝
"""

import socket
import threading
import json
import hashlib
import os
import time
import logging
from datetime import datetime
from collections import defaultdict

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
HOST        = "0.0.0.0"
PORT        = 9999
BUFFER      = 4096
DATA_FILE   = "nexus_data.json"
LOG_FILE    = "nexus_server.log"

# ─────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
)

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    logging.info(msg)

# ─────────────────────────────────────────────
#  PERSISTENCE
# ─────────────────────────────────────────────
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {
        "users": {},
        "rooms": {
            "general": {"topic": "General chat for everyone", "history": [], "owner": "system"},
            "random":  {"topic": "Random topics",             "history": [], "owner": "system"},
            "tech":    {"topic": "Technology discussions",    "history": [], "owner": "system"},
        },
        "dm_history": {},
    }

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(db, f, indent=2)

db = load_data()

# ─────────────────────────────────────────────
#  RUNTIME STATE
# ─────────────────────────────────────────────
clients    = {}          # username -> {"conn", "addr", "room", "thread"}
room_users = defaultdict(set)   # room_name -> set of usernames
lock       = threading.Lock()

# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def ts():
    return datetime.now().strftime("%H:%M")

def full_ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def send(conn, pkt):
    try:
        conn.sendall((json.dumps(pkt) + "\n").encode())
    except Exception:
        pass

def broadcast_room(room, pkt, exclude=None):
    with lock:
        targets = list(room_users.get(room, []))
    for uname in targets:
        if uname == exclude:
            continue
        with lock:
            info = clients.get(uname)
        if info:
            send(info["conn"], pkt)

def broadcast_all(pkt, exclude=None):
    with lock:
        unames = list(clients.keys())
    for uname in unames:
        if uname == exclude:
            continue
        with lock:
            info = clients.get(uname)
        if info:
            send(info["conn"], pkt)

def online_list():
    with lock:
        return list(clients.keys())

def room_list_payload():
    rooms = []
    for name, data in db["rooms"].items():
        rooms.append({
            "name":    name,
            "topic":   data.get("topic", ""),
            "users":   len(room_users.get(name, [])),
            "owner":   data.get("owner", "system"),
        })
    return rooms

def append_history(room, entry):
    db["rooms"][room]["history"].append(entry)
    # cap at 500 messages per room
    if len(db["rooms"][room]["history"]) > 500:
        db["rooms"][room]["history"] = db["rooms"][room]["history"][-500:]

# ─────────────────────────────────────────────
#  CLIENT HANDLER
# ─────────────────────────────────────────────
def handle_client(conn, addr):
    username = None
    buf = ""

    def recv_pkt():
        nonlocal buf
        while "\n" not in buf:
            chunk = conn.recv(BUFFER).decode(errors="replace")
            if not chunk:
                raise ConnectionError("Client disconnected")
            buf += chunk
        line, buf = buf.split("\n", 1)
        return json.loads(line)

    try:
        # ── AUTH ──────────────────────────────────────────
        auth = recv_pkt()
        action = auth.get("action")
        uname  = auth.get("username", "").strip().lower()
        pw     = auth.get("password", "")

        if not uname or len(uname) < 2:
            send(conn, {"type": "auth", "ok": False, "msg": "Username must be ≥ 2 characters."})
            conn.close(); return

        if action == "register":
            if uname in db["users"]:
                send(conn, {"type": "auth", "ok": False, "msg": "Username already taken."})
                conn.close(); return
            db["users"][uname] = {"pw": hash_pw(pw), "joined": full_ts(), "bio": ""}
            save_data()
            log(f"NEW USER registered: {uname} from {addr}")

        elif action == "login":
            if uname not in db["users"]:
                send(conn, {"type": "auth", "ok": False, "msg": "User not found."})
                conn.close(); return
            if db["users"][uname]["pw"] != hash_pw(pw):
                send(conn, {"type": "auth", "ok": False, "msg": "Wrong password."})
                conn.close(); return
            with lock:
                if uname in clients:
                    send(conn, {"type": "auth", "ok": False, "msg": "Already logged in from another session."})
                    conn.close(); return
        else:
            send(conn, {"type": "auth", "ok": False, "msg": "Unknown action."})
            conn.close(); return

        username = uname
        with lock:
            clients[username] = {"conn": conn, "addr": addr, "room": "general", "thread": threading.current_thread()}

        send(conn, {
            "type":    "auth",
            "ok":      True,
            "msg":     f"Welcome to NEXUS CHAT, {username}!",
            "username": username,
            "rooms":   room_list_payload(),
            "online":  online_list(),
        })

        # join general by default
        _join_room(username, conn, "general", silent=False)
        log(f"{username} connected from {addr}")

        # notify others
        broadcast_all({"type": "system", "msg": f"◉ {username} has come online."}, exclude=username)

        # ── MESSAGE LOOP ──────────────────────────────────
        while True:
            pkt = recv_pkt()
            t   = pkt.get("type")

            if t == "msg":
                _handle_msg(username, conn, pkt)

            elif t == "join":
                _join_room(username, conn, pkt.get("room", "general"))

            elif t == "create_room":
                _create_room(username, conn, pkt)

            elif t == "delete_room":
                _delete_room(username, conn, pkt)

            elif t == "dm":
                _handle_dm(username, conn, pkt)

            elif t == "history":
                _send_history(username, conn, pkt)

            elif t == "dm_history":
                _send_dm_history(username, conn, pkt)

            elif t == "rooms":
                send(conn, {"type": "rooms", "rooms": room_list_payload()})

            elif t == "online":
                send(conn, {"type": "online", "users": online_list()})

            elif t == "whois":
                _whois(username, conn, pkt)

            elif t == "set_bio":
                bio = pkt.get("bio", "")[:200]
                db["users"][username]["bio"] = bio
                save_data()
                send(conn, {"type": "system", "msg": "Bio updated."})

            elif t == "ping":
                send(conn, {"type": "pong"})

    except (ConnectionError, json.JSONDecodeError, ConnectionResetError):
        pass
    except Exception as e:
        log(f"ERROR with {username or addr}: {e}")
    finally:
        _disconnect(username, conn)

# ─────────────────────────────────────────────
#  ACTIONS
# ─────────────────────────────────────────────
def _join_room(username, conn, room_name, silent=True):
    if room_name not in db["rooms"]:
        send(conn, {"type": "system", "msg": f"Room '{room_name}' does not exist."})
        return

    with lock:
        old_room = clients[username]["room"]
        if old_room == room_name:
            send(conn, {"type": "system", "msg": f"You are already in #{room_name}."})
            return
        room_users[old_room].discard(username)
        room_users[room_name].add(username)
        clients[username]["room"] = room_name

    if not silent:
        broadcast_room(old_room, {
            "type": "system",
            "msg":  f"← {username} left #{old_room}",
        }, exclude=username)

    broadcast_room(room_name, {
        "type": "system",
        "msg":  f"→ {username} joined #{room_name}",
    }, exclude=username)

    # send room info + last 50 messages
    history = db["rooms"][room_name]["history"][-50:]
    send(conn, {
        "type":    "joined",
        "room":    room_name,
        "topic":   db["rooms"][room_name].get("topic", ""),
        "history": history,
        "users":   list(room_users[room_name]),
    })


def _handle_msg(username, conn, pkt):
    with lock:
        room = clients[username]["room"]
    text = pkt.get("text", "").strip()
    if not text:
        return
    if len(text) > 1000:
        send(conn, {"type": "system", "msg": "Message too long (max 1000 chars)."})
        return

    entry = {"from": username, "text": text, "ts": ts()}
    append_history(room, entry)
    save_data()

    broadcast_room(room, {"type": "msg", "room": room, **entry})


def _create_room(username, conn, pkt):
    name  = pkt.get("name", "").strip().lower().replace(" ", "-")
    topic = pkt.get("topic", "").strip()[:200]

    if not name or len(name) < 2:
        send(conn, {"type": "system", "msg": "Room name must be ≥ 2 characters."}); return
    if name in db["rooms"]:
        send(conn, {"type": "system", "msg": f"Room #{name} already exists."}); return

    db["rooms"][name] = {"topic": topic, "history": [], "owner": username}
    save_data()
    log(f"{username} created room #{name}")

    broadcast_all({"type": "room_created", "room": name, "topic": topic, "owner": username,
                   "msg": f"✦ New room #{name} created by {username}!"})
    _join_room(username, conn, name, silent=False)


def _delete_room(username, conn, pkt):
    name = pkt.get("name", "").strip().lower()
    if name not in db["rooms"]:
        send(conn, {"type": "system", "msg": f"Room #{name} not found."}); return
    if db["rooms"][name]["owner"] != username:
        send(conn, {"type": "system", "msg": "Only the owner can delete a room."}); return
    if name in ("general", "random", "tech"):
        send(conn, {"type": "system", "msg": "Cannot delete default rooms."}); return

    # move everyone out to general
    evicted = list(room_users.get(name, []))
    for uname in evicted:
        with lock:
            info = clients.get(uname)
        if info:
            _join_room(uname, info["conn"], "general", silent=False)

    del db["rooms"][name]
    save_data()
    broadcast_all({"type": "system", "msg": f"✦ Room #{name} was deleted by {username}."})


def _handle_dm(username, conn, pkt):
    target = pkt.get("to", "").strip().lower()
    text   = pkt.get("text", "").strip()

    if not target or not text:
        return
    if target == username:
        send(conn, {"type": "system", "msg": "You can't DM yourself."}); return

    with lock:
        target_info = clients.get(target)

    entry = {"from": username, "to": target, "text": text, "ts": ts(), "full_ts": full_ts()}
    key   = ":".join(sorted([username, target]))
    db["dm_history"].setdefault(key, []).append(entry)
    if len(db["dm_history"][key]) > 200:
        db["dm_history"][key] = db["dm_history"][key][-200:]
    save_data()

    dm_pkt = {"type": "dm", **entry}
    send(conn, dm_pkt)  # echo to sender

    if target_info:
        send(target_info["conn"], dm_pkt)
    else:
        send(conn, {"type": "system", "msg": f"✉ {target} is offline. Message saved."})


def _send_history(username, conn, pkt):
    room  = pkt.get("room") or clients[username]["room"]
    limit = min(int(pkt.get("limit", 50)), 200)
    if room not in db["rooms"]:
        send(conn, {"type": "system", "msg": f"Room #{room} not found."}); return
    history = db["rooms"][room]["history"][-limit:]
    send(conn, {"type": "history", "room": room, "messages": history})


def _send_dm_history(username, conn, pkt):
    target = pkt.get("with", "").strip().lower()
    key    = ":".join(sorted([username, target]))
    msgs   = db["dm_history"].get(key, [])[-50:]
    send(conn, {"type": "dm_history", "with": target, "messages": msgs})


def _whois(username, conn, pkt):
    target = pkt.get("user", "").strip().lower()
    if target not in db["users"]:
        send(conn, {"type": "system", "msg": f"User '{target}' not found."}); return
    u     = db["users"][target]
    online = target in clients
    with lock:
        room = clients[target]["room"] if online else "—"
    send(conn, {
        "type":   "whois",
        "user":   target,
        "joined": u.get("joined", "?"),
        "bio":    u.get("bio", "No bio set."),
        "online": online,
        "room":   room,
    })


def _disconnect(username, conn):
    if username:
        with lock:
            room = clients.get(username, {}).get("room", "general")
            room_users[room].discard(username)
            clients.pop(username, None)
        broadcast_all({"type": "system", "msg": f"◎ {username} went offline."})
        log(f"{username} disconnected")
    try:
        conn.close()
    except Exception:
        pass

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(100)

    print(r"""
  _   _ _______  ___   _ _____     ____ _   _    _  _____
 | \ | | ____\ \/ / | | |  ___|   / ___| | | |  / \|_   _|
 |  \| |  _|  \  /| | | | |_     | |   | |_| | / _ \ | |
 | |\  | |___ /  \| |_| |  _|    | |___| | | |/ ___ \| |
 |_| \_|_____/_/\_\\___/|_|       \____|_| |_/_/   \_\_|

    """)
    log(f"Server listening on {HOST}:{PORT}")
    log(f"Loaded {len(db['users'])} users, {len(db['rooms'])} rooms")

    while True:
        try:
            conn, addr = srv.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
            log(f"New connection from {addr}")
        except KeyboardInterrupt:
            log("Shutting down server…")
            save_data()
            break

if __name__ == "__main__":
    main()
