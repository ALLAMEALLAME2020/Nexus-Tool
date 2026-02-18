#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║          NEXUS CHAT CLIENT  v1.0                         ║
║          Multi-user Terminal Chat Application            ║
╚══════════════════════════════════════════════════════════╝

Dependencies:  pip install rich
"""

import socket
import threading
import json
import sys
import os
import time
from datetime import datetime

# ── Try importing Rich ────────────────────────────────────
try:
    from rich.console import Console
    from rich.panel   import Panel
    from rich.table   import Table
    from rich.text    import Text
    from rich.prompt  import Prompt, Confirm
    from rich import print as rprint
    from rich.live    import Live
    from rich.layout  import Layout
    from rich.columns import Columns
    from rich.rule    import Rule
    from rich.align   import Align
    from rich.style   import Style
    from rich.markup  import escape
except ImportError:
    print("Missing dependency. Run:  pip install rich")
    sys.exit(1)

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 9999
BUFFER      = 4096

console = Console()

# ─────────────────────────────────────────────
#  COLOUR PALETTE
# ─────────────────────────────────────────────
C_BRAND    = "bold cyan"
C_SYSTEM   = "bold yellow"
C_DM       = "bold magenta"
C_MSG      = "white"
C_ME       = "bold green"
C_TS       = "dim"
C_ERROR    = "bold red"
C_SUCCESS  = "bold green"
C_ROOM     = "bold blue"
C_HELP_CMD = "cyan"
C_HELP_DSC = "dim white"
C_BORDER   = "cyan"

# ─────────────────────────────────────────────
#  HELP TEXT
# ─────────────────────────────────────────────
COMMANDS = [
    ("/join  <room>",          "Join or switch to a chat room"),
    ("/create <room> [topic]", "Create a new room"),
    ("/delete <room>",         "Delete a room you own"),
    ("/rooms",                 "List all rooms"),
    ("/online",                "Show online users"),
    ("/dm  <user> <msg>",      "Send a private message"),
    ("/dms <user>",            "View DM history with a user"),
    ("/history [room] [n]",    "Show last n messages (default 50)"),
    ("/whois <user>",          "View user profile"),
    ("/bio <text>",            "Set your bio / status"),
    ("/clear",                 "Clear the screen"),
    ("/help",                  "Show this help"),
    ("/quit",                  "Disconnect and exit"),
]

def show_help():
    t = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 2))
    t.add_column("Command",     style=C_HELP_CMD, no_wrap=True)
    t.add_column("Description", style=C_HELP_DSC)
    for cmd, desc in COMMANDS:
        t.add_row(cmd, desc)
    console.print(Panel(t, title="[bold cyan]NEXUS CHAT — Commands[/]", border_style=C_BORDER))

# ─────────────────────────────────────────────
#  CLIENT STATE
# ─────────────────────────────────────────────
state = {
    "username": None,
    "room":     "general",
    "running":  True,
}

# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def ts_label():
    return f"[{C_TS}]{datetime.now().strftime('%H:%M')}[/{C_TS}]"

def print_msg(from_user, text, ts_val="", dm=False):
    pfx = "[DM] " if dm else f"[{C_ROOM}]#{{room}}[/{C_ROOM}] ".format(room=state["room"])
    is_me = from_user == state["username"]

    name_color = C_ME if is_me else "bold white"
    if dm:
        name_color = C_DM

    ts_str = f" [dim]{ts_val}[/dim]" if ts_val else ""
    console.print(f"{ts_str} [{name_color}]{escape(from_user)}[/{name_color}]: [white]{escape(text)}[/white]")

def print_system(msg):
    console.print(f"  [bold yellow]⚡[/bold yellow] [yellow]{escape(msg)}[/yellow]")

def print_error(msg):
    console.print(f"  [bold red]✗[/bold red] [red]{escape(msg)}[/red]")

def print_success(msg):
    console.print(f"  [bold green]✓[/bold green] [green]{escape(msg)}[/green]")

def print_dm(from_user, to_user, text, ts_val=""):
    arrow = "→" if from_user == state["username"] else "←"
    other = to_user if from_user == state["username"] else from_user
    ts_str = f" [dim]{ts_val}[/dim]" if ts_val else ""
    console.print(
        f"{ts_str} [bold magenta]✉ DM {arrow} {escape(other)}[/bold magenta]: [magenta]{escape(text)}[/magenta]"
    )

def separator(label=""):
    if label:
        console.print(Rule(f"[dim]{label}[/dim]", style="dim cyan"))
    else:
        console.print(Rule(style="dim cyan"))

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def banner():
    clear_screen()
    art = """
  ███╗   ██╗███████╗██╗  ██╗██╗   ██╗███████╗
  ████╗  ██║██╔════╝╚██╗██╔╝██║   ██║██╔════╝
  ██╔██╗ ██║█████╗   ╚███╔╝ ██║   ██║███████╗
  ██║╚██╗██║██╔══╝   ██╔██╗ ██║   ██║╚════██║
  ██║ ╚████║███████╗██╔╝ ██╗╚██████╔╝███████║
  ╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝
    """
    console.print(f"[bold cyan]{art}[/bold cyan]")
    console.print(Align.center("[dim]Terminal Chat Application  •  v1.0[/dim]\n"))

def room_header(room, topic, users):
    t = Text()
    t.append(f" #{room} ", style="bold white on blue")
    t.append(f"  {topic}" if topic else "  No topic set", style="dim")
    t.append(f"  [{len(users)} online]", style="dim cyan")
    console.print(Panel(t, border_style="blue", padding=(0, 1)))

# ─────────────────────────────────────────────
#  NETWORK
# ─────────────────────────────────────────────
def send_pkt(conn, pkt):
    try:
        conn.sendall((json.dumps(pkt) + "\n").encode())
    except Exception:
        pass

recv_buf = ""

def recv_pkt(conn):
    global recv_buf
    while "\n" not in recv_buf:
        chunk = conn.recv(BUFFER).decode(errors="replace")
        if not chunk:
            raise ConnectionError("Server closed connection")
        recv_buf += chunk
    line, recv_buf = recv_buf.split("\n", 1)
    return json.loads(line)

# ─────────────────────────────────────────────
#  INCOMING PACKET HANDLER
# ─────────────────────────────────────────────
def handle_incoming(conn):
    while state["running"]:
        try:
            pkt = recv_pkt(conn)
            t   = pkt.get("type")

            if t == "msg":
                print_msg(pkt["from"], pkt["text"], pkt.get("ts", ""))

            elif t == "dm":
                print_dm(pkt["from"], pkt["to"], pkt["text"], pkt.get("ts", ""))

            elif t == "system":
                print_system(pkt.get("msg", ""))

            elif t == "joined":
                state["room"] = pkt["room"]
                clear_screen()
                room_header(pkt["room"], pkt.get("topic", ""), pkt.get("users", []))
                separator("Last messages")
                for m in pkt.get("history", []):
                    print_msg(m["from"], m["text"], m.get("ts", ""))
                if pkt.get("history"):
                    separator()
                console.print(f"[dim]Type a message or[/dim] [cyan]/help[/cyan] [dim]for commands.[/dim]")

            elif t == "room_created":
                print_system(pkt.get("msg", ""))

            elif t == "rooms":
                _display_rooms(pkt["rooms"])

            elif t == "online":
                _display_online(pkt["users"])

            elif t == "history":
                separator(f"History: #{pkt['room']}")
                for m in pkt.get("messages", []):
                    print_msg(m["from"], m["text"], m.get("ts", ""))
                separator()

            elif t == "dm_history":
                separator(f"DM History with {pkt['with']}")
                for m in pkt.get("messages", []):
                    print_dm(m["from"], m["to"], m["text"], m.get("ts", ""))
                separator()

            elif t == "whois":
                _display_whois(pkt)

            elif t == "pong":
                pass  # keep-alive

        except (ConnectionError, json.JSONDecodeError):
            if state["running"]:
                print_error("Disconnected from server.")
                state["running"] = False
            break
        except Exception as e:
            print_error(f"Error: {e}")

def _display_rooms(rooms):
    t = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 2))
    t.add_column("Room",  style="bold blue")
    t.add_column("Topic", style="dim")
    t.add_column("Users", style="cyan", justify="right")
    t.add_column("Owner", style="dim")
    for r in rooms:
        t.add_row(f"#{r['name']}", r.get("topic", ""), str(r.get("users", 0)), r.get("owner", "?"))
    console.print(Panel(t, title="[bold cyan]Chat Rooms[/]", border_style=C_BORDER))

def _display_online(users):
    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_column("User", style="bold green")
    for u in users:
        badge = " [bold yellow]← you[/bold yellow]" if u == state["username"] else ""
        t.add_row(f"● {u}{badge}")
    console.print(Panel(t, title=f"[bold green]Online ({len(users)})[/]", border_style="green"))

def _display_whois(pkt):
    status = "[bold green]Online[/bold green]" if pkt["online"] else "[dim]Offline[/dim]"
    room   = f"[blue]#{pkt['room']}[/blue]" if pkt["online"] else "—"
    grid   = Table.grid(padding=(0, 2))
    grid.add_row("[dim]Status[/dim]",  status)
    grid.add_row("[dim]Room[/dim]",    room)
    grid.add_row("[dim]Joined[/dim]",  pkt.get("joined", "?"))
    grid.add_row("[dim]Bio[/dim]",     escape(pkt.get("bio", "No bio.")))
    console.print(Panel(grid, title=f"[bold cyan]@{pkt['user']}[/]", border_style=C_BORDER))

# ─────────────────────────────────────────────
#  AUTH FLOW
# ─────────────────────────────────────────────
def auth_flow(conn):
    console.print(Panel(
        "[bold cyan]1[/bold cyan] Login\n[bold cyan]2[/bold cyan] Register",
        title="[bold cyan]NEXUS CHAT — Connect[/]",
        border_style=C_BORDER,
        width=40,
    ))
    choice = Prompt.ask("[cyan]Choose[/cyan]", choices=["1", "2"], default="1")
    action = "login" if choice == "1" else "register"

    console.print()
    username = Prompt.ask("[cyan]Username[/cyan]").strip().lower()
    password = Prompt.ask("[cyan]Password[/cyan]", password=True).strip()

    send_pkt(conn, {"action": action, "username": username, "password": password})
    resp = recv_pkt(conn)

    if not resp.get("ok"):
        print_error(resp.get("msg", "Authentication failed."))
        return None

    state["username"] = resp["username"]
    print_success(resp.get("msg", ""))
    return resp

# ─────────────────────────────────────────────
#  INPUT LOOP
# ─────────────────────────────────────────────
def input_loop(conn):
    while state["running"]:
        try:
            prompt_str = f"[bold cyan]{state['username']}[/bold cyan][dim]@[/dim][blue]#{state['room']}[/blue] [dim]>[/dim] "
            line = console.input(prompt_str).strip()
        except (EOFError, KeyboardInterrupt):
            state["running"] = False
            send_pkt(conn, {"type": "quit"})
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not line:
            continue

        # ── COMMANDS ──────────────────────────────────────
        if line.startswith("/"):
            parts = line.split(maxsplit=2)
            cmd   = parts[0].lower()

            if cmd == "/help":
                show_help()

            elif cmd == "/quit" or cmd == "/exit":
                state["running"] = False
                console.print("[dim]Disconnecting…[/dim]")
                break

            elif cmd == "/clear":
                clear_screen()
                console.print(f"[dim]Back in[/dim] [blue]#{state['room']}[/blue][dim]. Type[/dim] [cyan]/help[/cyan] [dim]for commands.[/dim]")

            elif cmd == "/join":
                if len(parts) < 2:
                    print_error("Usage: /join <room>"); continue
                send_pkt(conn, {"type": "join", "room": parts[1].lower()})

            elif cmd == "/create":
                if len(parts) < 2:
                    print_error("Usage: /create <room> [topic]"); continue
                room  = parts[1].lower()
                topic = parts[2] if len(parts) > 2 else ""
                send_pkt(conn, {"type": "create_room", "name": room, "topic": topic})

            elif cmd == "/delete":
                if len(parts) < 2:
                    print_error("Usage: /delete <room>"); continue
                if Confirm.ask(f"[red]Delete room #{parts[1]}?[/red]"):
                    send_pkt(conn, {"type": "delete_room", "name": parts[1].lower()})

            elif cmd == "/rooms":
                send_pkt(conn, {"type": "rooms"})

            elif cmd == "/online":
                send_pkt(conn, {"type": "online"})

            elif cmd == "/dm":
                if len(parts) < 3:
                    print_error("Usage: /dm <user> <message>"); continue
                send_pkt(conn, {"type": "dm", "to": parts[1].lower(), "text": parts[2]})

            elif cmd == "/dms":
                if len(parts) < 2:
                    print_error("Usage: /dms <user>"); continue
                send_pkt(conn, {"type": "dm_history", "with": parts[1].lower()})

            elif cmd == "/history":
                room_arg  = parts[1] if len(parts) > 1 else state["room"]
                limit_arg = parts[2] if len(parts) > 2 else "50"
                send_pkt(conn, {"type": "history", "room": room_arg, "limit": limit_arg})

            elif cmd == "/whois":
                if len(parts) < 2:
                    print_error("Usage: /whois <user>"); continue
                send_pkt(conn, {"type": "whois", "user": parts[1].lower()})

            elif cmd == "/bio":
                bio = line[4:].strip()
                if not bio:
                    print_error("Usage: /bio <text>"); continue
                send_pkt(conn, {"type": "set_bio", "bio": bio})

            else:
                print_error(f"Unknown command: {cmd}  (type /help)")

        else:

            send_pkt(conn, {"type": "msg", "text": line})

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
def main():
    banner()

    # Optional: override server host from CLI arg
    host = sys.argv[1] if len(sys.argv) > 1 else SERVER_HOST
    port = int(sys.argv[2]) if len(sys.argv) > 2 else SERVER_PORT

    console.print(f"[dim]Connecting to[/dim] [cyan]{host}:{port}[/cyan] …")

    try:
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        conn.connect((host, port))
    except ConnectionRefusedError:
        print_error(f"Could not connect to {host}:{port} — is the server running?")
        sys.exit(1)

    print_success("Connected!")
    console.print()

    # Auth
    resp = auth_flow(conn)
    if not resp:
        conn.close()
        sys.exit(1)


    rx = threading.Thread(target=handle_incoming, args=(conn,), daemon=True)
    rx.start()


    time.sleep(0.3)


    input_loop(conn)

    # Cleanup
    state["running"] = False
    try:
        conn.close()
    except Exception:
        pass
    sys.exit(0)

if __name__ == "__main__":
    main()
