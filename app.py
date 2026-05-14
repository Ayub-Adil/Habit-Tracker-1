from flask import Flask, render_template, request, redirect, session, jsonify
import sqlite3
from datetime import datetime, timedelta
import secrets
from werkzeug.security import generate_password_hash, check_password_hash
import calendar

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)
DB = "habit.db"

# ---------------- DATABASE ----------------
def connect():
    return sqlite3.connect(DB)

def create_tables():
    con = connect()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE,
        password TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS habits(
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        name TEXT,
        goal INTEGER,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS habit_logs(
        id INTEGER PRIMARY KEY,
        habit_id INTEGER,
        date TEXT,
        FOREIGN KEY(habit_id) REFERENCES habits(id)
    )
    """)

    con.commit()
    con.close()

create_tables()

# ---------------- STREAK HELPERS ----------------

# Current streak: consecutive days ending today
def get_current_streak(habit_id):
    con = connect()
    cur = con.cursor()
    cur.execute("SELECT date FROM habit_logs WHERE habit_id=? ORDER BY date DESC", (habit_id,))
    rows = cur.fetchall()
    con.close()

    dates = {r[0] for r in rows}
    streak = 0
    today = datetime.now()

    while True:
        expected = (today - timedelta(days=streak)).strftime("%Y-%m-%d")
        if expected in dates:
            streak += 1
        else:
            break
    return streak

# Longest streak: best run ever
def get_longest_streak(habit_id):
    con = connect()
    cur = con.cursor()
    cur.execute("SELECT date FROM habit_logs WHERE habit_id=? ORDER BY date ASC", (habit_id,))
    rows = cur.fetchall()
    con.close()

    if not rows:
        return 0

    dates = [datetime.strptime(r[0], "%Y-%m-%d") for r in rows]
    longest = 1
    current = 1

    for i in range(1, len(dates)):
        if (dates[i] - dates[i-1]).days == 1:
            current += 1
            longest = max(longest, current)
        else:
            current = 1

    return longest

# Alias: keep old get_streak calls working
def get_streak(habit_id):
    return get_current_streak(habit_id)   # or get_longest_streak(habit_id)

# ---------------- PROGRESS ----------------
def get_progress(habit_id, goal):
    goal = int(goal) if goal else 0
    con = connect()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM habit_logs WHERE habit_id=?", (habit_id,))
    completed = cur.fetchone()[0]
    con.close()

    percent = int((completed / goal) * 100) if goal > 0 else 0
    return min(percent, 100)

# ---------------- TOTAL COMPLETE ----------------
def get_total_completed(habit_id):
    con = connect()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM habit_logs WHERE habit_id=?", (habit_id,))
    total = cur.fetchone()[0]
    con.close()
    return total

# ---------------- ACHIEVEMENTS ----------------
def get_achievement(streak):
    if streak >= 30:
        return "👑 Master"
    elif streak >= 14:
        return "🥇 Dedicated"
    elif streak >= 7:
        return "🥈 Consistent"
    elif streak >= 3:
        return "🥉 Beginner"
    else:
        return "No Badge Yet"

# ---------------- REGISTER ----------------
@app.route("/", methods=["GET","POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        hashed_pw = generate_password_hash(password)

        con = connect()
        cur = con.cursor()
        try:
            cur.execute("INSERT INTO users(username,password) VALUES(?,?)", (username, hashed_pw))
            con.commit()
        except sqlite3.IntegrityError:
            return render_template("index.html", error="Username already taken")
        finally:
            con.close()

        return redirect("/login")

    return render_template("index.html")

# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        con = connect()
        cur = con.cursor()
        cur.execute("SELECT * FROM users WHERE username=?", (username,))
        user = cur.fetchone()
        con.close()

        if user and check_password_hash(user[2], password):
            session["user"] = user[0]
            return redirect("/dashboard")

        return render_template("index.html", error="Invalid credentials")

    return render_template("index.html")

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/login")

    con = connect()
    cur = con.cursor()
    cur.execute("SELECT * FROM habits WHERE user_id=?", (session["user"],))
    habits = cur.fetchall()
    con.close()

    return render_template("dashboard.html",
                           habits=habits,
                           get_streak=get_streak,
                           get_current_streak=get_current_streak,
                           get_longest_streak=get_longest_streak,
                           get_total_completed=get_total_completed,
                           get_progress=get_progress,
                           get_achievement=get_achievement)

# ---------------- ADD HABIT ----------------
@app.route("/add", methods=["POST"])
def add():
    name = request.form["name"]
    goal = request.form["goal"]

    con = connect()
    cur = con.cursor()
    cur.execute("INSERT INTO habits(user_id,name,goal) VALUES(?,?,?)", (session["user"], name, goal))
    con.commit()
    con.close()

    return redirect("/dashboard")

# ---------------- DELETE HABIT ----------------
@app.route("/delete/<int:habit_id>", methods=["POST"])
def delete_habit(habit_id):
    con = connect()
    cur = con.cursor()
    # Delete logs first (to avoid foreign key issues)
    cur.execute("DELETE FROM habit_logs WHERE habit_id=?", (habit_id,))
    # Delete the habit itself
    cur.execute("DELETE FROM habits WHERE id=?", (habit_id,))
    con.commit()
    con.close()
    return redirect("/dashboard")

# ---------------- CALENDAR ----------------
@app.route("/calendar/<int:habit_id>")
def habit_calendar(habit_id):
    now = datetime.now()
    cal = calendar.monthcalendar(now.year, now.month)

    con = connect()
    cur = con.cursor()
    cur.execute("SELECT date FROM habit_logs WHERE habit_id=?", (habit_id,))
    records = [int(r[0].split("-")[2]) for r in cur.fetchall() if r[0].startswith(now.strftime("%Y-%m"))]
    con.close()

    return render_template("calendar.html",
                           cal=cal,
                           habit_id=habit_id,
                           records=records,
                           get_streak=get_streak,
                           get_current_streak=get_current_streak,
                           get_longest_streak=get_longest_streak,
                           get_total_completed=get_total_completed)

# ---------------- MARK DAY ----------------
@app.route("/mark/<int:habit_id>/<int:day>")
def mark_day(habit_id, day):
    date = datetime.now().strftime("%Y-%m-") + str(day)

    con = connect()
    cur = con.cursor()
    cur.execute("SELECT * FROM habit_logs WHERE habit_id=? AND date=?", (habit_id, date))
    exists = cur.fetchone()

    if not exists:
        cur.execute("INSERT INTO habit_logs(habit_id,date) VALUES(?,?)", (habit_id, date))
        con.commit()

    con.close()
    return redirect("/calendar/" + str(habit_id))

# ---------------- WEEKLY DATA ----------------
@app.route("/weekly")
def weekly():
    con = connect()
    cur = con.cursor()
    today = datetime.now()
    data = {}
    for i in range(7):
        day = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        cur.execute("SELECT COUNT(*) FROM habit_logs WHERE date=?", (day,))
        data[day] = cur.fetchone()[0]
    con.close()
    return jsonify(data)

# ---------------- MONTHLY DATA ----------------
@app.route("/monthly")
def monthly():
    con = connect()
    cur = con.cursor()
    today = datetime.now()
    data = {}
    for i in range(30):
        day = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        cur.execute("SELECT COUNT(*) FROM habit_logs WHERE date=?", (day,))
        data[day] = cur.fetchone()[0]
    con.close()
    return jsonify(data)

# ---------------- CHARTS ----------------
@app.route("/charts")
def charts():
    return render_template("charts.html")

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
