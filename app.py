from flask import Flask, render_template, request, redirect, session, jsonify
from instagrapi import Client
import threading, time

app = Flask(__name__)
app.secret_key = "supersecretkey"

cl = Client()
running = False
message_thread = None
pending_2fa = {}
logs = []

# Function to append logs safely
def log_message(text):
    logs.append(text)
    print(text)

def spam_messages(recipient, message, delay, threads_count=3):
    global running
    def send_one():
        try:
            if recipient.startswith("thread:"):
                thread_id = recipient.replace("thread:", "")
                cl.direct_send(message, thread_ids=[thread_id])
            else:
                user_id = cl.user_id_from_username(recipient)
                cl.direct_send(message, [user_id])
            log_message(f"✅ Sent: {message}")
        except Exception as e:
            log_message(f"❌ Error: {e}")

    while running:
        thread_list = []
        for _ in range(threads_count):
            t = threading.Thread(target=send_one)
            t.start()
            thread_list.append(t)
        for t in thread_list:
            t.join()
        if delay > 0:
            time.sleep(delay)

@app.route("/", methods=["GET", "POST"])
def login():
    error = None
    username = ""

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        two_factor = request.form.get("two_factor")

        if username in pending_2fa:
            try:
                cl.two_factor_login(two_factor)
                session["logged_in"] = True
                pending_2fa.pop(username)
                return redirect("/control")
            except Exception as e:
                error = f"2FA failed: {e}"
        else:
            try:
                cl.login(username, password)
                session["logged_in"] = True
                return redirect("/control")
            except Exception as e:
                if "two_factor_required" in str(e):
                    pending_2fa[username] = True
                    error = "2FA required. Enter code below."
                else:
                    error = str(e)

    return render_template("login.html", error=error, username=username)

@app.route("/control", methods=["GET", "POST"])
def control_panel():
    if not session.get("logged_in"):
        return redirect("/")

    started = False
    stopped = False
    delay = 0.5
    threads_count = 3

    if request.method == "POST":
        recipient = request.form["recipient"]
        message = request.form["message"]
        try:
            delay = float(request.form["delay"])
        except:
            delay = 0.5
        try:
            threads_count = int(request.form.get("threads_count", 3))
        except:
            threads_count = 3

        global running, message_thread
        running = True
        logs.clear()
        message_thread = threading.Thread(
            target=spam_messages,
            args=(recipient, message, delay, threads_count)
        )
        message_thread.start()
        started = True

    return render_template(
        "control.html",
        chats=get_chats(),
        started=started,
        stopped=stopped,
        delay=delay,
        threads_count=threads_count,
        logs=logs
    )

@app.route("/stop")
def stop_sending():
    global running, message_thread
    running = False
    if message_thread and message_thread.is_alive():
        message_thread.join()
    return redirect("/control")

@app.route("/logs")
def get_logs():
    return jsonify(logs)

def get_chats():
    threads = cl.direct_threads()
    chat_list = []
    for t in threads:
        if len(t.users) > 1:
            name = "Group: " + ", ".join([u.username for u in t.users])
            chat_list.append(("thread:" + str(t.id), name))
        else:
            chat_list.append((t.users[0].username, t.users[0].username))
    return chat_list

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
