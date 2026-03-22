#!/usr/bin/env python3
"""
📤 SendPai — Dateien senden wie ein Senpai!
Dein Gerät wird zum Server. Link teilen. Fertig.
Lokal + Internet. Kein Cloud. Kein Account. Kein Bullshit.
"""

import tkinter as tk
from tkinter import filedialog, messagebox
import http.server
import socketserver
import socket
import threading
import os
import sys
import json
import urllib.request
import urllib.parse
import hashlib
import time
import io
import zipfile
import base64
from pathlib import Path

APP_NAME = "SendPai"
APP_VERSION = "1.1.2"
PORT = 7777

# === COLORS ===
BG_DARK = "#1a1720"
BG_CARD = "#2a2632"
BG_INPUT = "#33303c"
FG_WHITE = "#f0ece4"
FG_GRAY = "#8a8a9a"
FG_PURPLE = "#a832b8"
FG_ORANGE = "#e8724a"
FG_GREEN = "#00b464"
FG_RED = "#c0392b"
FG_BLUE = "#3498db"


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_public_ip():
    import ssl
    # SSL Context der auch in PyInstaller-Bundles funktioniert
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    for url in ["https://api.ipify.org", "https://ifconfig.me/ip", "http://ifconfig.me/ip"]:
        try:
            if url.startswith("https"):
                with urllib.request.urlopen(url, timeout=5, context=ctx) as r:
                    return r.read().decode().strip()
            else:
                with urllib.request.urlopen(url, timeout=5) as r:
                    return r.read().decode().strip()
        except Exception:
            continue
    return None


def _xor_crypt(data, key="SendPai2026!ShinpaiAI"):
    """Einfache XOR-Verschlüsselung — macht den Token unlesbar."""
    result = bytearray()
    for i, b in enumerate(data.encode()):
        result.append(b ^ ord(key[i % len(key)]))
    return result


def encode_link(local_ip, public_ip, port):
    """Verschlüsselt die IPs im Link — nicht erkennbar."""
    timestamp = str(int(time.time()))[-6:]  # Jeder Link sieht anders aus
    data = f"{timestamp}:{local_ip}|{public_ip or ''}|{port}"
    encrypted = _xor_crypt(data)
    token = base64.urlsafe_b64encode(encrypted).decode().rstrip("=")
    return token


def decode_link(token):
    """Entschlüsselt den Token zurück zu IPs."""
    padding = 4 - len(token) % 4
    if padding != 4:
        token += "=" * padding
    encrypted = base64.urlsafe_b64decode(token)
    decrypted = _xor_crypt(encrypted.decode("latin-1"))
    data = decrypted.decode("latin-1")
    # Timestamp wegschneiden
    data = data.split(":", 1)[1] if ":" in data else data
    parts = data.split("|")
    return parts[0], parts[1] if len(parts) > 1 else "", parts[2] if len(parts) > 2 else str(PORT)


class SendPaiHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        try:
            if self.path == "/" or self.path == "/download":
                self._serve_download_page()
            elif self.path.startswith("/s/"):
                self._serve_smart_page()
            elif self.path == "/download/all":
                self._serve_zip()
            elif self.path.startswith("/download/file/"):
                self._serve_single_file()
            elif self.path == "/api/info":
                self._serve_info()
            else:
                self.send_error(404)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def _serve_download_page(self):
        files = self.server.shared_files
        file_list_html = ""
        total_size = 0

        for i, f in enumerate(files):
            size = os.path.getsize(f)
            total_size += size
            name = os.path.basename(f)
            size_str = f"{size / 1024 / 1024:.1f} MB" if size > 1024 * 1024 else f"{size / 1024:.0f} KB"
            file_list_html += f"""
            <a href="/download/file/{i}" download style="display:flex;justify-content:space-between;align-items:center;padding:16px 20px;background:#2a2632;border-radius:12px;margin:8px 0;text-decoration:none;border:1px solid #33303c;transition:all 0.2s;" onmouseover="this.style.borderColor='#a832b8'" onmouseout="this.style.borderColor='#33303c'">
                <span style="color:#f0ece4;font-size:1em;">📄 {name}</span>
                <div style="display:flex;align-items:center;gap:12px;">
                    <span style="color:#8a8a9a;">{size_str}</span>
                    <span style="background:linear-gradient(135deg,#a832b8,#e8724a);color:white;padding:10px 24px;border-radius:8px;font-weight:bold;font-size:1em;">⬇️ Download</span>
                </div>
            </a>"""

        total_str = f"{total_size / 1024 / 1024:.1f} MB" if total_size > 1024 * 1024 else f"{total_size / 1024:.0f} KB"

        html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SendPai — Download</title>
<style>
body {{ background:#1a1720; color:#f0ece4; font-family:-apple-system,BlinkMacSystemFont,sans-serif; margin:0; padding:20px; min-height:100vh; }}
.container {{ max-width:600px; margin:0 auto; }}
h1 {{ text-align:center; font-size:2em; margin-bottom:4px; }}
.sub {{ text-align:center; color:#8a8a9a; margin-bottom:24px; font-size:1.1em; }}
.all-btn {{ display:block; text-align:center; background:linear-gradient(135deg,#a832b8,#e8724a); color:white; padding:18px; border-radius:12px; text-decoration:none; font-weight:bold; font-size:1.2em; margin:20px 0; box-shadow:0 4px 20px rgba(168,50,184,0.3); }}
.footer {{ text-align:center; color:#8a8a9a; font-size:0.8em; margin-top:40px; }}
</style></head><body>
<div class="container">
<h1>📤 SendPai</h1>
<p class="sub">{len(files)} Datei{"en" if len(files) != 1 else ""} • {total_str}</p>
{"<a href='/download/all' download class='all-btn'>📦 Alles als ZIP herunterladen</a>" if len(files) > 1 else "<a href='/download/file/0' download class='all-btn'>⬇️ Herunterladen</a>"}
{file_list_html}
<p class="footer">⚠️ Dieser Link ist nur für den vorgesehenen Empfänger bestimmt.<br>SendPai by Shinpai-AI • shinpai.de</p>
</div></body></html>"""

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

        if hasattr(self.server, 'on_page_visit'):
            self.server.on_page_visit(self.client_address[0])

    def _serve_smart_page(self):
        """Smart-Seite mit verschleiertem Token."""
        token = self.path.split("/s/")[-1]
        try:
            local_ip, public_ip, port = decode_link(token)
        except Exception:
            self.send_error(400, "Ungültiger Link")
            return

        html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SendPai — Verbinde...</title>
<style>
body {{ background:#1a1720; color:#f0ece4; font-family:-apple-system,sans-serif; margin:0; display:flex; align-items:center; justify-content:center; min-height:100vh; }}
.box {{ text-align:center; padding:40px; }}
h1 {{ font-size:2em; }}
p {{ color:#8a8a9a; font-size:1.1em; }}
.spinner {{ font-size:2em; animation:spin 1s linear infinite; display:inline-block; }}
@keyframes spin {{ to {{ transform:rotate(360deg); }} }}
a {{ color:#a832b8; text-decoration:none; padding:12px 24px; border:1px solid #a832b8; border-radius:8px; display:inline-block; margin:8px; }}
</style>
<script>
async function tryConnect() {{
    const local = "http://{local_ip}:{port}/download";
    const pub = "{f'http://{public_ip}:{port}/download' if public_ip else ''}";
    try {{
        const ctrl = new AbortController();
        setTimeout(() => ctrl.abort(), 2000);
        await fetch("http://{local_ip}:{port}/api/info", {{ signal: ctrl.signal, mode: 'no-cors' }});
        window.location = local; return;
    }} catch(e) {{}}
    if (pub) {{ window.location = pub; return; }}
    document.getElementById("status").innerHTML = "❌ Keine Verbindung!<br><br>" +
        "<a href='" + local + "'>🏠 Lokal</a>" +
        (pub ? "<a href='" + pub + "'>🌐 Internet</a>" : "");
}}
tryConnect();
</script>
</head><body>
<div class="box">
<h1>📤 SendPai</h1>
<p id="status"><span class="spinner">⏳</span><br>Verbinde automatisch...</p>
</div></body></html>"""

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def _serve_single_file(self):
        try:
            idx = int(self.path.split("/")[-1])
            filepath = self.server.shared_files[idx]
            filename = os.path.basename(filepath)
            filesize = os.path.getsize(filepath)

            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", f'attachment; filename="{urllib.parse.quote(filename)}"')
            self.send_header("Content-Length", str(filesize))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

            with open(filepath, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        return

            if hasattr(self.server, 'on_download'):
                self.server.on_download(filename, self.client_address[0])

        except (IndexError, FileNotFoundError):
            self.send_error(404)

    def _serve_zip(self):
        try:
            files = self.server.shared_files

            # ZIP-Name aus dem Paketname-Feld
            zip_name = getattr(self.server, 'package_name', 'SendPai-Dateien') + ".zip"

            # Originale Ordnerstruktur beibehalten
            common = os.path.commonpath(files) if len(files) > 1 else str(Path(files[0]).parent)

            buf = io.BytesIO()
            with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                for filepath in files:
                    # Relativer Pfad ab gemeinsamem Ordner
                    arcname = os.path.relpath(filepath, common)
                    zf.write(filepath, arcname)

            data = buf.getvalue()
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", f'attachment; filename="{urllib.parse.quote(zip_name)}"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                return

            if hasattr(self.server, 'on_download'):
                self.server.on_download(zip_name, self.client_address[0])

        except Exception:
            self.send_error(500)

    def _serve_info(self):
        files = [{"name": os.path.basename(f), "size": os.path.getsize(f)} for f in self.server.shared_files]
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({"files": files}).encode())


class SendPaiApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"SendPai v{APP_VERSION}")
        self.root.geometry("520x720")
        self.root.configure(bg=BG_DARK)
        self.root.resizable(False, False)

        icon_path = Path(__file__).parent / "assets" / "icon.png"
        if icon_path.exists():
            try:
                icon = tk.PhotoImage(file=str(icon_path))
                self.root.iconphoto(True, icon)
                self._icon_ref = icon
            except Exception:
                pass

        self.shared_files = []
        self.server = None
        self.server_thread = None
        self.running = False
        self.smart_link = ""

        self._build_ui()

    def _build_ui(self):
        # === HEADER ===
        header = tk.Frame(self.root, bg=BG_DARK, pady=12)
        header.pack(fill="x")
        tk.Label(header, text="📤 SendPai", font=("Helvetica", 22, "bold"),
                 fg=FG_WHITE, bg=BG_DARK).pack()
        tk.Label(header, text="Dateien senden wie ein Senpai!",
                 font=("Helvetica", 9), fg=FG_GRAY, bg=BG_DARK).pack()

        # === DATEIEN ===
        file_frame = tk.Frame(self.root, bg=BG_DARK, padx=20, pady=5)
        file_frame.pack(fill="x")
        tk.Label(file_frame, text="📁 DATEIEN", font=("Helvetica", 8, "bold"),
                 fg=FG_ORANGE, bg=BG_DARK, anchor="w").pack(fill="x")

        btn_row = tk.Frame(file_frame, bg=BG_DARK)
        btn_row.pack(fill="x", pady=5)
        tk.Button(btn_row, text="📄 Dateien", font=("Helvetica", 10),
                  bg=BG_CARD, fg=FG_WHITE, relief="flat", padx=15, pady=5,
                  command=self._add_files, cursor="hand2").pack(side="left", padx=2)
        tk.Button(btn_row, text="📂 Ordner", font=("Helvetica", 10),
                  bg=BG_CARD, fg=FG_WHITE, relief="flat", padx=15, pady=5,
                  command=self._add_folder, cursor="hand2").pack(side="left", padx=2)
        tk.Button(btn_row, text="🗑️", font=("Helvetica", 10),
                  bg=BG_CARD, fg=FG_GRAY, relief="flat", padx=10, pady=5,
                  command=self._clear_files, cursor="hand2").pack(side="right")

        self.file_listbox = tk.Listbox(file_frame, height=5, font=("Consolas", 9),
                                        bg=BG_INPUT, fg=FG_WHITE, relief="flat", bd=8,
                                        selectbackground=FG_PURPLE)
        self.file_listbox.pack(fill="x", pady=3)
        self.file_count_label = tk.Label(file_frame, text="Keine Dateien",
                                          font=("Helvetica", 9), fg=FG_GRAY, bg=BG_DARK)
        self.file_count_label.pack(anchor="w")

        # === PAKETNAME ===
        name_frame = tk.Frame(self.root, bg=BG_DARK, padx=20, pady=3)
        name_frame.pack(fill="x")
        tk.Label(name_frame, text="📦 PAKETNAME (für ZIP)", font=("Helvetica", 8, "bold"),
                 fg=FG_ORANGE, bg=BG_DARK, anchor="w").pack(fill="x")
        self.package_name_var = tk.StringVar(value="SendPai-Dateien")
        self.package_name_entry = tk.Entry(name_frame, textvariable=self.package_name_var,
                                            font=("Helvetica", 10), bg=BG_INPUT, fg=FG_WHITE,
                                            insertbackground=FG_WHITE, relief="flat", bd=8)
        self.package_name_entry.pack(fill="x", pady=3)
        self.package_name_entry.bind("<FocusIn>", self._clear_default_name)

        # === BEREITSTELLEN ===
        ctrl_frame = tk.Frame(self.root, bg=BG_DARK, padx=20, pady=8)
        ctrl_frame.pack(fill="x")
        self.share_btn = tk.Button(ctrl_frame, text="🚀 BEREITSTELLEN",
                                    font=("Helvetica", 13, "bold"),
                                    bg=FG_GREEN, fg=BG_DARK, relief="flat",
                                    padx=30, pady=8, cursor="hand2",
                                    command=self._toggle_sharing)
        self.share_btn.pack()

        # === LINK BEREICH ===
        link_outer = tk.Frame(self.root, bg=BG_DARK, padx=20, pady=5)
        link_outer.pack(fill="x")

        self.link_frame = tk.Frame(link_outer, bg=BG_CARD, padx=15, pady=15)
        self.link_frame.pack(fill="x")

        self.status_label = tk.Label(self.link_frame,
                                      text="⏸️ Dateien hinzufügen → BEREITSTELLEN",
                                      font=("Helvetica", 10), fg=FG_GRAY, bg=BG_CARD,
                                      anchor="w", wraplength=460)
        self.status_label.pack(fill="x")

        # Link-Anzeige + Kopieren Button
        self.link_display_frame = tk.Frame(self.link_frame, bg=BG_CARD)
        self.link_display_frame.pack(fill="x", pady=(8, 0))

        self.link_entry = tk.Entry(self.link_display_frame, font=("Consolas", 9),
                                    bg=BG_INPUT, fg=FG_BLUE, relief="flat", bd=8,
                                    readonlybackground=BG_INPUT, state="readonly",
                                    justify="center")
        self.link_entry.pack(side="left", fill="x", expand=True)

        self.copy_btn = tk.Button(self.link_display_frame, text="📋 Kopieren",
                                   font=("Helvetica", 10, "bold"),
                                   bg=FG_PURPLE, fg=FG_WHITE, relief="flat",
                                   padx=15, pady=5, cursor="hand2",
                                   command=self._copy_link)
        self.copy_btn.pack(side="right", padx=(5, 0))

        # Initial verstecken
        self.link_display_frame.pack_forget()

        self.hint_label = tk.Label(self.link_frame, text="",
                                    font=("Helvetica", 9), fg=FG_GRAY, bg=BG_CARD)
        self.hint_label.pack(fill="x", pady=(5, 0))

        # === LOG ===
        log_frame = tk.Frame(self.root, bg=BG_DARK, padx=20, pady=5)
        log_frame.pack(fill="both", expand=True)
        tk.Label(log_frame, text="📋 AKTIVITÄT", font=("Helvetica", 8, "bold"),
                 fg=FG_ORANGE, bg=BG_DARK, anchor="w").pack(fill="x")
        self.log_text = tk.Text(log_frame, height=6, font=("Consolas", 9),
                                 bg=BG_INPUT, fg=FG_GRAY, relief="flat", bd=8,
                                 wrap="word", state="disabled")
        self.log_text.pack(fill="both", expand=True, pady=3)
        self.log_text.tag_configure("success", foreground=FG_GREEN)
        self.log_text.tag_configure("info", foreground=FG_PURPLE)
        self.log_text.tag_configure("visit", foreground=FG_BLUE)

        tk.Label(self.root, text="shinpai.de | AGPL-3.0",
                 font=("Helvetica", 8), fg=FG_GRAY, bg=BG_DARK).pack(pady=(0, 6))

    def _clear_default_name(self, event=None):
        if self.package_name_var.get() == "SendPai-Dateien":
            self.package_name_var.set("")

    def _add_files(self):
        files = filedialog.askopenfilenames(title="Dateien auswählen")
        for f in files:
            if f not in self.shared_files:
                self.shared_files.append(f)
        self._update_file_list()

    def _add_folder(self):
        folder = filedialog.askdirectory(title="Ordner auswählen")
        if folder:
            for root, dirs, files in os.walk(folder):
                for f in files:
                    fp = os.path.join(root, f)
                    if fp not in self.shared_files:
                        self.shared_files.append(fp)
        self._update_file_list()

    def _clear_files(self):
        self.shared_files.clear()
        self._update_file_list()

    def _update_file_list(self):
        self.file_listbox.delete(0, tk.END)
        total = 0
        for f in self.shared_files:
            name = os.path.basename(f)
            size = os.path.getsize(f)
            total += size
            s = f"{size/1024/1024:.1f}MB" if size > 1048576 else f"{size/1024:.0f}KB"
            self.file_listbox.insert(tk.END, f"  {name}  ({s})")
        if self.shared_files:
            ts = f"{total/1024/1024:.1f} MB" if total > 1048576 else f"{total/1024:.0f} KB"
            self.file_count_label.configure(text=f"{len(self.shared_files)} Dateien • {ts}")
        else:
            self.file_count_label.configure(text="Keine Dateien")

    def _log(self, msg, tag=None):
        self.log_text.configure(state="normal")
        t = time.strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{t}] {msg}\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _copy_link(self):
        if self.smart_link:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.smart_link)
            link_type = "Lokal" if getattr(self, '_link_is_local', True) else "Internet"
            self.copy_btn.configure(text=f"✅ {link_type} kopiert!", bg=FG_GREEN)
            self._log(f"📋 {link_type}-Link kopiert!", "success")
            self.root.after(2000, lambda: self.copy_btn.configure(text="📋 Kopieren", bg=FG_PURPLE))

    def _toggle_link_type(self):
        """Wechselt zwischen Lokal und Internet Link."""
        if getattr(self, '_link_is_local', True) and self.public_link:
            self.smart_link = self.public_link
            self.link_entry.configure(state="normal")
            self.link_entry.delete(0, tk.END)
            self.link_entry.insert(0, self.public_link)
            self.link_entry.configure(state="readonly")
            self.toggle_btn.configure(text="🏠 Lokal-Link kopieren")
            self._link_is_local = False
        else:
            self.smart_link = self.local_link
            self.link_entry.configure(state="normal")
            self.link_entry.delete(0, tk.END)
            self.link_entry.insert(0, self.local_link)
            self.link_entry.configure(state="readonly")
            self.toggle_btn.configure(text="🌐 Internet-Link kopieren")
            self._link_is_local = True

    def _toggle_sharing(self):
        if self.running:
            self._stop_sharing()
        else:
            self._start_sharing()

    def _start_sharing(self):
        if not self.shared_files:
            messagebox.showwarning("SendPai", "Keine Dateien ausgewählt!")
            return

        try:
            socketserver.TCPServer.allow_reuse_address = True
            self.server = socketserver.TCPServer(("0.0.0.0", PORT), SendPaiHandler)
            self.server.allow_reuse_address = True
            self.server.shared_files = self.shared_files
            pkg_name = self.package_name_var.get().strip()
            self.server.package_name = pkg_name if pkg_name else "SendPai-Dateien"
            self.server.on_page_visit = lambda ip: self.root.after(0, lambda: self._log(f"👀 Besucher: {ip}", "visit"))
            self.server.on_download = lambda name, ip: self.root.after(0, lambda: self._log(f"⬇️ {name} → {ip}", "success"))
        except OSError:
            messagebox.showerror("SendPai", f"Port {PORT} belegt!")
            return

        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.running = True

        self.share_btn.configure(text="⏹ STOPPEN", bg=FG_RED)
        self.status_label.configure(text="🟢 Bereit! Link kopieren und teilen:", fg=FG_GREEN)
        self.link_display_frame.pack(fill="x", pady=(8, 0))

        self._log("🚀 Server gestartet!", "info")
        threading.Thread(target=self._generate_link, daemon=True).start()

    def _generate_link(self):
        local_ip = get_local_ip()
        self._log(f"🏠 Lokale IP: {local_ip}", "info")

        local_link = f"http://{local_ip}:{PORT}"
        self.local_link = local_link
        self.smart_link = local_link

        # Lokal sofort anzeigen
        self.root.after(0, lambda: self._set_local_link(local_link))

        # Öffentliche IP laden
        public_ip = get_public_ip()
        if public_ip:
            public_link = f"http://{public_ip}:{PORT}"
            self.public_link = public_link
            self.root.after(0, lambda: self._set_public_link(public_link, local_ip))
        else:
            self.public_link = None
            self.root.after(0, lambda: self._set_public_link_failed(local_ip))

    def _set_local_link(self, local_link):
        self.link_entry.configure(state="normal")
        self.link_entry.delete(0, tk.END)
        self.link_entry.insert(0, local_link)
        self.link_entry.configure(state="readonly")
        self.hint_label.configure(text="🏠 Gleiches WLAN: Sofort nutzbar!\n\n"
                                       "⚠️ Link nur an den gewünschten Empfänger teilen!",
                                  fg=FG_GRAY, justify="left")

    def _set_public_link(self, public_link, local_ip):
        """Wird aufgerufen wenn öffentliche IP gefunden wurde."""
        self.hint_label.configure(
            text=f"🏠 Gleiches WLAN: Sofort nutzbar!\n"
                 f"🌐 Übers Internet: Port {PORT} im Router freigeben!\n"
                 f"    Router → Port-Forwarding → Port {PORT} → {local_ip}\n\n"
                 f"⚠️ Link nur an den gewünschten Empfänger teilen!",
            fg=FG_GRAY, justify="left")

        # Toggle Button
        if hasattr(self, 'toggle_btn'):
            try:
                self.toggle_btn.destroy()
            except Exception:
                pass
        self.toggle_btn = tk.Button(self.link_frame, text="🌐 Internet-Link kopieren",
                                     font=("Helvetica", 10, "bold"), bg=BG_INPUT, fg=FG_ORANGE,
                                     relief="flat", padx=15, pady=5, cursor="hand2",
                                     command=self._toggle_link_type)
        self.toggle_btn.pack(pady=(8, 0))
        self._link_is_local = True

        self._log(f"🌐 Internet: {public_link}", "info")

    def _set_public_link_failed(self, local_ip):
        """Öffentliche IP nicht gefunden — trotzdem Hinweis zeigen."""
        self.hint_label.configure(
            text=f"🏠 Gleiches WLAN: Sofort nutzbar!\n"
                 f"🌐 Übers Internet: Öffentliche IP nicht ermittelt.\n"
                 f"    Prüfe: https://api.ipify.org im Browser\n"
                 f"    Dann: http://DEINE-IP:{PORT} als Link nutzen\n"
                 f"    + Port {PORT} im Router freigeben → {local_ip}\n\n"
                 f"⚠️ Link nur an den gewünschten Empfänger teilen!",
            fg=FG_GRAY, justify="left")
        self._log("🌐 Öffentliche IP nicht ermittelt", "info")

    def _stop_sharing(self):
        if self.server:
            self.server.shutdown()
            try:
                self.server.server_close()
            except Exception:
                pass
            self.server = None
        self.running = False
        self.smart_link = ""
        self.share_btn.configure(text="🚀 BEREITSTELLEN", bg=FG_GREEN)
        self.status_label.configure(text="⏸️ Gestoppt", fg=FG_GRAY)
        self.link_display_frame.pack_forget()
        self.link_entry.configure(state="normal")
        self.link_entry.delete(0, tk.END)
        self.link_entry.configure(state="readonly")
        self.hint_label.configure(text="")
        if hasattr(self, 'toggle_btn'):
            self.toggle_btn.pack_forget()
        self._log("⏹ Gestoppt", "info")

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        self._stop_sharing()
        self.root.destroy()


if __name__ == "__main__":
    app = SendPaiApp()
    app.run()
