import os, json, secrets
from datetime import datetime, date, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import or_

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__, instance_relative_config=True)
os.makedirs(app.instance_path, exist_ok=True)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-this-secret-before-deploying"),
    SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", "sqlite:///" + os.path.join(app.instance_path, "journal.db")),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    MAX_CONTENT_LENGTH=8 * 1024 * 1024,
)
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "برای ادامه ابتدا وارد حساب خود شوید."
login_manager.login_message_category = "info"

def now():
    return datetime.utcnow()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    journal_name = db.Column(db.String(100), nullable=False, default="ژورنال من")
    email = db.Column(db.String(180), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    theme = db.Column(db.String(20), nullable=False, default="light")
    accent = db.Column(db.String(20), nullable=False, default="#7667e8")
    font_size = db.Column(db.Integer, nullable=False, default=16)
    start_week = db.Column(db.String(20), nullable=False, default="saturday")
    dashboard_layout = db.Column(db.Text, nullable=False, default="[\"tasks\",\"habits\",\"goals\",\"notes\"]")
    created_at = db.Column(db.DateTime, default=now, nullable=False)
    tasks = db.relationship("Task", backref="owner", cascade="all, delete-orphan", lazy=True)
    notes = db.relationship("Note", backref="owner", cascade="all, delete-orphan", lazy=True)
    goals = db.relationship("Goal", backref="owner", cascade="all, delete-orphan", lazy=True)
    habits = db.relationship("Habit", backref="owner", cascade="all, delete-orphan", lazy=True)
    pages = db.relationship("JournalPage", backref="owner", cascade="all, delete-orphan", lazy=True)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    title = db.Column(db.String(220), nullable=False)
    details = db.Column(db.Text, default="")
    due_date = db.Column(db.Date, nullable=True)
    priority = db.Column(db.String(20), default="medium")
    status = db.Column(db.String(20), default="todo")
    reminder_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=now, nullable=False)

class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    title = db.Column(db.String(220), nullable=False)
    body = db.Column(db.Text, default="")
    pinned = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=now, nullable=False)
    updated_at = db.Column(db.DateTime, default=now, onupdate=now, nullable=False)

class Goal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    title = db.Column(db.String(220), nullable=False)
    details = db.Column(db.Text, default="")
    target_date = db.Column(db.Date, nullable=True)
    progress = db.Column(db.Integer, default=0)

class Habit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    color = db.Column(db.String(20), default="#7667e8")
    active = db.Column(db.Boolean, default=True)
    entries = db.relationship("HabitEntry", backref="habit", cascade="all, delete-orphan", lazy=True)

class HabitEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    habit_id = db.Column(db.Integer, db.ForeignKey("habit.id"), nullable=False, index=True)
    entry_date = db.Column(db.Date, nullable=False, default=date.today)
    done = db.Column(db.Boolean, default=True)
    __table_args__ = (db.UniqueConstraint("habit_id", "entry_date", name="uq_habit_entry_day"),)

class JournalEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    title = db.Column(db.String(220), nullable=False)
    details = db.Column(db.Text, default="")
    starts_at = db.Column(db.DateTime, nullable=False, index=True)
    reminder_minutes = db.Column(db.Integer, default=10)
    created_at = db.Column(db.DateTime, default=now, nullable=False)

class DailyEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    entry_date = db.Column(db.Date, nullable=False, index=True)
    title = db.Column(db.String(180), default="یادداشت روزانه")
    mood = db.Column(db.String(30), default="خوب")
    gratitude = db.Column(db.Text, default="")
    wins = db.Column(db.Text, default="")
    reflection = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=now, nullable=False)
    updated_at = db.Column(db.DateTime, default=now, onupdate=now, nullable=False)
    __table_args__ = (db.UniqueConstraint("user_id", "entry_date", name="uq_daily_entry_user_date"),)

class JournalTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    page_title = db.Column(db.String(180), nullable=False, default="صفحه جدید")
    icon = db.Column(db.String(20), default="📄")
    color = db.Column(db.String(20), default="#7667e8")
    body = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=now, nullable=False)

class JournalPage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    icon = db.Column(db.String(20), default="📄")
    body = db.Column(db.Text, default="")
    color = db.Column(db.String(20), default="#7667e8")
    created_at = db.Column(db.DateTime, default=now, nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

@app.before_request
def csrf_protect():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    if request.method == "POST":
        token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not token or not secrets.compare_digest(token, session["csrf_token"]):
            abort(400, description="درخواست معتبر نیست. صفحه را تازه‌سازی کنید و دوباره تلاش کنید.")

@app.context_processor
def inject_globals():
    return {"csrf_token": session.get("csrf_token", ""), "today": date.today()}

def parse_datetime(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except ValueError:
        return None

def parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None

@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return render_template("welcome.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        first = request.form.get("first_name", "").strip()
        last = request.form.get("last_name", "").strip()
        journal = request.form.get("journal_name", "").strip() or "ژورنال من"
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not first or not last or not email or len(password) < 8:
            flash("نام، نام خانوادگی، ایمیل و رمز عبور حداقل ۸ کاراکتری لازم است.", "error")
        elif User.query.filter_by(email=email).first():
            flash("این ایمیل قبلاً ثبت شده است.", "error")
        else:
            user = User(first_name=first[:80], last_name=last[:100], journal_name=journal[:100],
                        email=email, password_hash=generate_password_hash(password))
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("ژورنال شخصی‌ات ساخته شد. خوش آمدی!", "success")
            return redirect(url_for("dashboard"))
    return render_template("auth.html", mode="register")

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("ایمیل یا رمز عبور صحیح نیست.", "error")
    return render_template("auth.html", mode="login")

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("از حساب خارج شدی.", "success")
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    today = date.today()
    tasks = Task.query.filter_by(user_id=current_user.id).order_by(Task.status.asc(), Task.due_date.asc()).limit(8).all()
    notes = Note.query.filter_by(user_id=current_user.id).order_by(Note.pinned.desc(), Note.updated_at.desc()).limit(4).all()
    goals = Goal.query.filter_by(user_id=current_user.id).order_by(Goal.target_date.asc()).limit(4).all()
    habits = Habit.query.filter_by(user_id=current_user.id, active=True).all()
    habit_done = {e.habit_id for h in habits for e in h.entries if e.entry_date == today and e.done}
    total = Task.query.filter_by(user_id=current_user.id).count()
    completed = Task.query.filter_by(user_id=current_user.id, status="done").count()
    try:
        layout = json.loads(current_user.dashboard_layout or '["tasks","habits","goals","notes"]')
    except (ValueError, TypeError):
        layout = ["tasks", "habits", "goals", "notes"]
    upcoming = JournalEvent.query.filter_by(user_id=current_user.id).filter(JournalEvent.starts_at >= datetime.now()).order_by(JournalEvent.starts_at.asc()).limit(4).all()
    return render_template("dashboard.html", tasks=tasks, notes=notes, goals=goals, habits=habits,
                           habit_done=habit_done, total=total, completed=completed, today=today, layout=layout, upcoming=upcoming)

@app.route("/tasks", methods=["GET", "POST"])
@login_required
def tasks():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if title:
            db.session.add(Task(user_id=current_user.id, title=title[:220],
                details=request.form.get("details", "").strip()[:5000],
                due_date=parse_date(request.form.get("due_date")),
                priority=request.form.get("priority", "medium") if request.form.get("priority") in ("low","medium","high","urgent") else "medium",
                reminder_at=parse_datetime(request.form.get("reminder_at"))))
            db.session.commit()
            flash("وظیفه اضافه شد.", "success")
        return redirect(url_for("tasks"))
    status = request.args.get("status", "all")
    q = Task.query.filter_by(user_id=current_user.id)
    if status in ("todo", "done", "doing"):
        q = q.filter_by(status=status)
    search = request.args.get("q", "").strip()
    if search:
        q = q.filter(or_(Task.title.ilike(f"%{search}%"), Task.details.ilike(f"%{search}%")))
    items = q.order_by(Task.due_date.is_(None), Task.due_date.asc(), Task.created_at.desc()).all()
    return render_template("tasks.html", tasks=items, status=status, search=search)

@app.route("/tasks/<int:task_id>/toggle", methods=["POST"])
@login_required
def toggle_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    task.status = "todo" if task.status == "done" else "done"
    db.session.commit()
    return redirect(request.referrer or url_for("tasks"))

@app.route("/tasks/<int:task_id>/delete", methods=["POST"])
@login_required
def delete_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    db.session.delete(task); db.session.commit()
    flash("وظیفه حذف شد.", "success")
    return redirect(request.referrer or url_for("tasks"))

@app.route("/notes", methods=["GET", "POST"])
@login_required
def notes():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if title:
            db.session.add(Note(user_id=current_user.id, title=title[:220], body=request.form.get("body", "").strip()[:20000]))
            db.session.commit(); flash("یادداشت ذخیره شد.", "success")
        return redirect(url_for("notes"))
    items = Note.query.filter_by(user_id=current_user.id).order_by(Note.pinned.desc(), Note.updated_at.desc()).all()
    return render_template("notes.html", notes=items)

@app.route("/notes/<int:note_id>/edit", methods=["POST"])
@login_required
def edit_note(note_id):
    note = Note.query.filter_by(id=note_id, user_id=current_user.id).first_or_404()
    title = request.form.get("title", "").strip()
    if title:
        note.title = title[:220]
        note.body = request.form.get("body", "").strip()[:20000]
        db.session.commit(); flash("یادداشت به‌روزرسانی شد.", "success")
    return redirect(url_for("notes"))

@app.route("/notes/<int:note_id>/pin", methods=["POST"])
@login_required
def pin_note(note_id):
    note = Note.query.filter_by(id=note_id, user_id=current_user.id).first_or_404()
    note.pinned = not note.pinned
    db.session.commit()
    return redirect(url_for("notes"))

@app.route("/notes/<int:note_id>/delete", methods=["POST"])
@login_required
def delete_note(note_id):
    note = Note.query.filter_by(id=note_id, user_id=current_user.id).first_or_404()
    db.session.delete(note); db.session.commit()
    flash("یادداشت حذف شد.", "success")
    return redirect(url_for("notes"))

@app.route("/goals", methods=["GET", "POST"])
@login_required
def goals():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if title:
            try: progress = max(0, min(100, int(request.form.get("progress", "0"))))
            except ValueError: progress = 0
            db.session.add(Goal(user_id=current_user.id, title=title[:220],
                details=request.form.get("details", "").strip()[:5000],
                target_date=parse_date(request.form.get("target_date")), progress=progress))
            db.session.commit(); flash("هدف ثبت شد.", "success")
        return redirect(url_for("goals"))
    items = Goal.query.filter_by(user_id=current_user.id).order_by(Goal.target_date.asc()).all()
    return render_template("goals.html", goals=items)

@app.route("/goals/<int:goal_id>/update", methods=["POST"])
@login_required
def update_goal(goal_id):
    goal = Goal.query.filter_by(id=goal_id, user_id=current_user.id).first_or_404()
    try: goal.progress = max(0, min(100, int(request.form.get("progress", "0"))))
    except ValueError: pass
    db.session.commit()
    flash("پیشرفت هدف ذخیره شد.", "success")
    return redirect(url_for("goals"))

@app.route("/goals/<int:goal_id>/delete", methods=["POST"])
@login_required
def delete_goal(goal_id):
    goal = Goal.query.filter_by(id=goal_id, user_id=current_user.id).first_or_404()
    db.session.delete(goal); db.session.commit()
    return redirect(url_for("goals"))

@app.route("/habits", methods=["GET", "POST"])
@login_required
def habits():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if title:
            db.session.add(Habit(user_id=current_user.id, title=title[:180],
                                 color=request.form.get("color", "#7667e8")[:20]))
            db.session.commit(); flash("عادت جدید ساخته شد.", "success")
        return redirect(url_for("habits"))
    items = Habit.query.filter_by(user_id=current_user.id, active=True).all()
    today = date.today()
    done = {e.habit_id for h in items for e in h.entries if e.entry_date == today and e.done}
    history = {h.id: {e.entry_date.isoformat() for e in h.entries if e.done} for h in items}
    return render_template("habits.html", habits=items, done=done, today=today, history=history)

@app.route("/habits/<int:habit_id>/toggle", methods=["POST"])
@login_required
def toggle_habit(habit_id):
    habit = Habit.query.filter_by(id=habit_id, user_id=current_user.id).first_or_404()
    today = date.today()
    entry = HabitEntry.query.filter_by(habit_id=habit.id, entry_date=today).first()
    if entry:
        db.session.delete(entry)
    else:
        db.session.add(HabitEntry(habit_id=habit.id, entry_date=today, done=True))
    db.session.commit()
    return redirect(request.referrer or url_for("habits"))

@app.route("/habits/<int:habit_id>/delete", methods=["POST"])
@login_required
def delete_habit(habit_id):
    habit = Habit.query.filter_by(id=habit_id, user_id=current_user.id).first_or_404()
    db.session.delete(habit); db.session.commit()
    return redirect(url_for("habits"))

@app.route("/pages", methods=["GET", "POST"])
@login_required
def pages():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if title:
            db.session.add(JournalPage(user_id=current_user.id, title=title[:180],
                icon=request.form.get("icon", "📄")[:20], body=request.form.get("body", "").strip()[:30000],
                color=request.form.get("color", "#7667e8")[:20]))
            db.session.commit(); flash("صفحه ساخته شد.", "success")
        return redirect(url_for("pages"))
    items = JournalPage.query.filter_by(user_id=current_user.id).order_by(JournalPage.created_at.desc()).all()
    return render_template("pages.html", pages=items)

@app.route("/pages/<int:page_id>/edit", methods=["POST"])
@login_required
def edit_page(page_id):
    page = JournalPage.query.filter_by(id=page_id, user_id=current_user.id).first_or_404()
    title = request.form.get("title", "").strip()
    if title:
        page.title = title[:180]
        page.body = request.form.get("body", "").strip()[:30000]
        page.icon = request.form.get("icon", page.icon)[:20]
        page.color = request.form.get("color", page.color)[:20]
        db.session.commit(); flash("صفحه به‌روزرسانی شد.", "success")
    return redirect(url_for("pages"))

@app.route("/pages/<int:page_id>/delete", methods=["POST"])
@login_required
def delete_page(page_id):
    page = JournalPage.query.filter_by(id=page_id, user_id=current_user.id).first_or_404()
    db.session.delete(page); db.session.commit()
    return redirect(url_for("pages"))

@app.route("/journal", methods=["GET", "POST"])
@login_required
def daily_journal():
    if request.method == "POST":
        entry_date = parse_date(request.form.get("entry_date")) or date.today()
        entry = DailyEntry.query.filter_by(user_id=current_user.id, entry_date=entry_date).first()
        if not entry:
            entry = DailyEntry(user_id=current_user.id, entry_date=entry_date)
            db.session.add(entry)
        entry.title = request.form.get("title", "یادداشت روزانه").strip()[:180] or "یادداشت روزانه"
        entry.mood = request.form.get("mood", "خوب") if request.form.get("mood") in ("عالی", "خوب", "معمولی", "خسته", "نگران") else "خوب"
        entry.gratitude = request.form.get("gratitude", "").strip()[:10000]
        entry.wins = request.form.get("wins", "").strip()[:10000]
        entry.reflection = request.form.get("reflection", "").strip()[:20000]
        db.session.commit(); flash("یادداشت روزانه ذخیره شد.", "success")
        return redirect(url_for("daily_journal", day=entry_date.isoformat()))
    selected = parse_date(request.args.get("day")) or date.today()
    entry = DailyEntry.query.filter_by(user_id=current_user.id, entry_date=selected).first()
    recent = DailyEntry.query.filter_by(user_id=current_user.id).order_by(DailyEntry.entry_date.desc()).limit(14).all()
    return render_template("journal.html", entry=entry, selected=selected, recent=recent)

@app.route("/reports")
@login_required
def reports():
    total_tasks = Task.query.filter_by(user_id=current_user.id).count()
    completed_tasks = Task.query.filter_by(user_id=current_user.id, status="done").count()
    active_goals = Goal.query.filter_by(user_id=current_user.id).count()
    avg_goal = round(sum(g.progress for g in Goal.query.filter_by(user_id=current_user.id).all()) / active_goals) if active_goals else 0
    habits = Habit.query.filter_by(user_id=current_user.id, active=True).all()
    since = date.today() - timedelta(days=6)
    habit_checks = HabitEntry.query.join(Habit, HabitEntry.habit_id == Habit.id).filter(Habit.user_id == current_user.id, HabitEntry.entry_date >= since, HabitEntry.done.is_(True)).count()
    entries_count = DailyEntry.query.filter_by(user_id=current_user.id).count()
    week_tasks = Task.query.filter_by(user_id=current_user.id, status="done").filter(Task.created_at >= datetime.now() - timedelta(days=7)).count()
    return render_template("reports.html", total_tasks=total_tasks, completed_tasks=completed_tasks, active_goals=active_goals, avg_goal=avg_goal, habits=habits, habit_checks=habit_checks, entries_count=entries_count, week_tasks=week_tasks)

@app.route("/calendar", methods=["GET", "POST"])
@login_required
def calendar():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        starts_at = parse_datetime(request.form.get("starts_at"))
        if title and starts_at:
            try: reminder = max(0, min(10080, int(request.form.get("reminder_minutes", "10"))))
            except ValueError: reminder = 10
            db.session.add(JournalEvent(user_id=current_user.id, title=title[:220], details=request.form.get("details", "").strip()[:5000], starts_at=starts_at, reminder_minutes=reminder))
            db.session.commit(); flash("رویداد به تقویم اضافه شد.", "success")
        else:
            flash("عنوان و تاریخ و ساعت رویداد را وارد کن.", "error")
        return redirect(url_for("calendar"))
    use_jalali = False
    try:
        import jdatetime
        today_j = jdatetime.date.fromgregorian(date=date.today())
        raw_month = request.args.get("month", f"{today_j.year}-{today_j.month:02d}")
        try: year, mon = [int(x) for x in raw_month.split("-")]
        except (ValueError, TypeError): year, mon = today_j.year, today_j.month
        if mon < 1 or mon > 12: year, mon = today_j.year, today_j.month
        first_j = jdatetime.date(year, mon, 1)
        next_j = jdatetime.date(year + (mon == 12), 1 if mon == 12 else mon + 1, 1)
        first, next_date = first_j.togregorian(), next_j.togregorian()
        last_day = (next_date - first).days
        jalali_label = f"{year} / {jdatetime.date.j_months_fa[mon-1]}"
        jalali_day = lambda day: day
        today_calendar = (today_j.year, today_j.month, today_j.day)
        prev_month = f"{year - (mon == 1)}-{12 if mon == 1 else mon-1:02d}"
        next_month = f"{year + (mon == 12)}-{1 if mon == 12 else mon+1:02d}"
        use_jalali = True
    except Exception:
        raw_month = request.args.get("month", date.today().strftime("%Y-%m"))
        try: year, mon = [int(x) for x in raw_month.split("-")]; first = date(year, mon, 1)
        except (ValueError, TypeError): first = date.today().replace(day=1); year, mon = first.year, first.month
        next_date = date(year + (mon == 12), 1 if mon == 12 else mon + 1, 1)
        last_day = (next_date - first).days
        jalali_label = f"{year}/{mon:02d}"; jalali_day = lambda day: day
        today_calendar = (date.today().year, date.today().month, date.today().day)
        prev_month = f"{year - (mon == 1)}-{12 if mon == 1 else mon-1:02d}"
        next_month = f"{year + (mon == 12)}-{1 if mon == 12 else mon+1:02d}"
    offset = (first.weekday() + (2 if current_user.start_week == "saturday" else 0)) % 7
    days = [None] * offset + list(range(1, last_day + 1))
    while len(days) % 7: days.append(None)
    events = JournalEvent.query.filter_by(user_id=current_user.id).filter(JournalEvent.starts_at >= datetime.combine(first, datetime.min.time()), JournalEvent.starts_at < datetime.combine(next_date, datetime.min.time())).order_by(JournalEvent.starts_at.asc()).all()
    tasks_due = Task.query.filter_by(user_id=current_user.id).filter(Task.due_date >= first, Task.due_date < next_date).all()
    event_map = {}
    for event in events:
        day_key = event.starts_at.day
        if use_jalali:
            try:
                import jdatetime
                day_key = jdatetime.date.fromgregorian(date=event.starts_at.date()).day
            except Exception: pass
        event_map.setdefault(day_key, []).append({"kind":"event", "title":event.title, "time":event.starts_at.strftime("%H:%M"), "id":event.id})
    for task in tasks_due:
        day_key = task.due_date.day
        if use_jalali:
            try:
                import jdatetime
                day_key = jdatetime.date.fromgregorian(date=task.due_date).day
            except Exception: pass
        event_map.setdefault(day_key, []).append({"kind":"task", "title":task.title, "time":"وظیفه", "id":task.id})
    return render_template("calendar.html", days=days, year=year, mon=mon, month=raw_month, prev_month=prev_month, next_month=next_month, event_map=event_map, events=events, jalali_label=jalali_label, jalali_day=jalali_day, today_calendar=today_calendar)

@app.route("/api/reminders")
@login_required
def reminder_feed():
    now_at = datetime.now()
    lower = now_at - timedelta(minutes=2)
    task_items = Task.query.filter_by(user_id=current_user.id).filter(Task.status != "done", Task.reminder_at > lower, Task.reminder_at <= now_at).all()
    event_items = JournalEvent.query.filter_by(user_id=current_user.id).filter(JournalEvent.starts_at >= now_at, JournalEvent.starts_at <= now_at + timedelta(days=1)).all()
    results = [{"id": f"task-{x.id}", "title": x.title, "message": "زمان یادآوری وظیفه رسیده است."} for x in task_items]
    for event in event_items:
        remind_at = event.starts_at - timedelta(minutes=event.reminder_minutes or 0)
        if event.reminder_minutes and lower < remind_at <= now_at:
            results.append({"id": f"event-{event.id}", "title": event.title, "message": "زمان یادآوری رویداد رسیده است."})
    return jsonify(results)

@app.route("/events/<int:event_id>/delete", methods=["POST"])
@login_required
def delete_event(event_id):
    event = JournalEvent.query.filter_by(id=event_id, user_id=current_user.id).first_or_404()
    db.session.delete(event); db.session.commit(); flash("رویداد حذف شد.", "success")
    return redirect(url_for("calendar"))

@app.route("/dashboard/layout", methods=["POST"])
@login_required
def save_dashboard_layout():
    allowed = {"tasks", "habits", "goals", "notes", "upcoming"}
    raw = request.form.getlist("widget")
    layout = [x for x in raw if x in allowed]
    for item in allowed:
        if item not in layout: layout.append(item)
    current_user.dashboard_layout = json.dumps(layout)
    db.session.commit(); flash("چیدمان داشبورد ذخیره شد.", "success")
    return redirect(url_for("dashboard"))

@app.route("/templates", methods=["GET", "POST"])
@login_required
def templates_page():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if name:
            db.session.add(JournalTemplate(user_id=current_user.id, name=name[:120], page_title=request.form.get("page_title", "صفحه جدید").strip()[:180] or "صفحه جدید", icon=request.form.get("icon", "📄")[:20], color=request.form.get("color", "#7667e8")[:20], body=request.form.get("body", "").strip()[:30000]))
            db.session.commit(); flash("قالب ذخیره شد و از این پس می‌توانی دوباره از آن استفاده کنی.", "success")
        return redirect(url_for("templates_page"))
    templates = JournalTemplate.query.filter_by(user_id=current_user.id).order_by(JournalTemplate.created_at.desc()).all()
    return render_template("templates.html", templates=templates)

@app.route("/templates/<int:template_id>/use", methods=["POST"])
@login_required
def use_template(template_id):
    template = JournalTemplate.query.filter_by(id=template_id, user_id=current_user.id).first_or_404()
    page = JournalPage(user_id=current_user.id, title=template.page_title, icon=template.icon, body=template.body, color=template.color)
    db.session.add(page); db.session.commit(); flash("یک صفحه بر اساس قالب ساخته شد.", "success")
    return redirect(url_for("pages"))

@app.route("/templates/<int:template_id>/delete", methods=["POST"])
@login_required
def delete_template(template_id):
    template = JournalTemplate.query.filter_by(id=template_id, user_id=current_user.id).first_or_404()
    db.session.delete(template); db.session.commit(); return redirect(url_for("templates_page"))

@app.route("/search")
@login_required
def global_search():
    q = request.args.get("q", "").strip()[:100]
    tasks = Task.query.filter_by(user_id=current_user.id).filter(or_(Task.title.ilike(f"%{q}%"), Task.details.ilike(f"%{q}%"))).all() if q else []
    notes = Note.query.filter_by(user_id=current_user.id).filter(or_(Note.title.ilike(f"%{q}%"), Note.body.ilike(f"%{q}%"))).all() if q else []
    pages = JournalPage.query.filter_by(user_id=current_user.id).filter(or_(JournalPage.title.ilike(f"%{q}%"), JournalPage.body.ilike(f"%{q}%"))).all() if q else []
    goals = Goal.query.filter_by(user_id=current_user.id).filter(or_(Goal.title.ilike(f"%{q}%"), Goal.details.ilike(f"%{q}%"))).all() if q else []
    return render_template("search.html", q=q, tasks=tasks, notes=notes, pages=pages, goals=goals)

@app.route("/import", methods=["GET", "POST"])
@login_required
def import_data():
    if request.method == "POST":
        upload = request.files.get("backup")
        if not upload or not upload.filename.lower().endswith(".json"):
            flash("یک فایل پشتیبان JSON انتخاب کن.", "error"); return redirect(url_for("settings"))
        try:
            data = json.loads(upload.read(5_000_001).decode("utf-8"))
            if not isinstance(data, dict): raise ValueError()
            for item in data.get("tasks", []):
                db.session.add(Task(user_id=current_user.id, title=str(item.get("title", "وظیفه"))[:220], details=str(item.get("details", ""))[:5000], due_date=parse_date(item.get("due_date")), priority=item.get("priority") if item.get("priority") in ("low","medium","high","urgent") else "medium", status=item.get("status") if item.get("status") in ("todo","done","doing") else "todo", reminder_at=parse_datetime(item.get("reminder_at", "")[:16].replace(" ", "T") if item.get("reminder_at") else "")))
            for item in data.get("notes", []): db.session.add(Note(user_id=current_user.id, title=str(item.get("title", "یادداشت"))[:220], body=str(item.get("body", ""))[:20000], pinned=bool(item.get("pinned", False))))
            for item in data.get("goals", []): db.session.add(Goal(user_id=current_user.id, title=str(item.get("title", "هدف"))[:220], details=str(item.get("details", ""))[:5000], target_date=parse_date(item.get("target_date")), progress=max(0,min(100,int(item.get("progress",0))))))
            for item in data.get("pages", []): db.session.add(JournalPage(user_id=current_user.id, title=str(item.get("title", "صفحه"))[:180], icon=str(item.get("icon", "📄"))[:20], body=str(item.get("body", ""))[:30000], color=str(item.get("color", "#7667e8"))[:20]))
            for item in data.get("habits", []):
                habit = Habit(user_id=current_user.id, title=str(item.get("title", "عادت"))[:180], color=str(item.get("color", "#7667e8"))[:20])
                db.session.add(habit); db.session.flush()
                for entry in item.get("entries", []):
                    entry_date = parse_date(entry.get("date"))
                    if entry_date: db.session.add(HabitEntry(habit_id=habit.id, entry_date=entry_date, done=bool(entry.get("done", True))))
            for item in data.get("events", []):
                starts_at = parse_datetime(str(item.get("starts_at", ""))[:16])
                if starts_at: db.session.add(JournalEvent(user_id=current_user.id, title=str(item.get("title", "رویداد"))[:220], details=str(item.get("details", ""))[:5000], starts_at=starts_at, reminder_minutes=max(0,min(10080,int(item.get("reminder_minutes",10))))))
            for item in data.get("templates", []): db.session.add(JournalTemplate(user_id=current_user.id, name=str(item.get("name", "قالب"))[:120], page_title=str(item.get("page_title", "صفحه جدید"))[:180], icon=str(item.get("icon", "📄"))[:20], color=str(item.get("color", "#7667e8"))[:20], body=str(item.get("body", ""))[:30000]))
            for item in data.get("daily_journal", []):
                entry_date = parse_date(item.get("date"))
                if entry_date and not DailyEntry.query.filter_by(user_id=current_user.id, entry_date=entry_date).first():
                    mood = item.get("mood", "خوب")
                    if mood not in ("عالی", "خوب", "معمولی", "خسته", "نگران"): mood = "خوب"
                    db.session.add(DailyEntry(user_id=current_user.id, entry_date=entry_date, title=str(item.get("title", "یادداشت روزانه"))[:180], mood=mood, gratitude=str(item.get("gratitude", ""))[:10000], wins=str(item.get("wins", ""))[:10000], reflection=str(item.get("reflection", ""))[:20000]))
            db.session.commit(); flash("اطلاعات فایل پشتیبان به ژورنالت اضافه شد.", "success")
        except Exception:
            db.session.rollback(); flash("فایل پشتیبان نامعتبر یا خراب است.", "error")
        return redirect(url_for("settings"))
    return redirect(url_for("settings"))

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        current_user.first_name = request.form.get("first_name", "").strip()[:80] or current_user.first_name
        current_user.last_name = request.form.get("last_name", "").strip()[:100] or current_user.last_name
        current_user.journal_name = request.form.get("journal_name", "").strip()[:100] or current_user.journal_name
        current_user.theme = request.form.get("theme", "light") if request.form.get("theme") in ("light", "dark", "paper", "green", "purple") else "light"
        accent = request.form.get("accent", "#7667e8")
        if len(accent) == 7 and accent.startswith("#"):
            current_user.accent = accent
        try: current_user.font_size = max(13, min(22, int(request.form.get("font_size", "16"))))
        except ValueError: pass
        current_user.start_week = request.form.get("start_week", "saturday") if request.form.get("start_week") in ("saturday","monday") else "saturday"
        db.session.commit()
        flash("تنظیمات ذخیره شد.", "success")
        return redirect(url_for("settings"))
    return render_template("settings.html")

@app.route("/export")
@login_required
def export_data():
    data = {
        "profile": {"first_name": current_user.first_name, "last_name": current_user.last_name,
                    "journal_name": current_user.journal_name, "exported_at": datetime.utcnow().isoformat()},
        "tasks": [{"title":x.title,"details":x.details,"due_date":x.due_date.isoformat() if x.due_date else None,
                   "priority":x.priority,"status":x.status,"reminder_at":x.reminder_at.isoformat() if x.reminder_at else None} for x in current_user.tasks],
        "notes": [{"title":x.title,"body":x.body,"pinned":x.pinned} for x in current_user.notes],
        "goals": [{"title":x.title,"details":x.details,"target_date":x.target_date.isoformat() if x.target_date else None,"progress":x.progress} for x in current_user.goals],
        "habits": [{"title":x.title,"color":x.color,"entries":[{"date":e.entry_date.isoformat(),"done":e.done} for e in x.entries]} for x in current_user.habits],
        "pages": [{"title":x.title,"icon":x.icon,"body":x.body,"color":x.color} for x in current_user.pages],
        "events": [{"title":x.title,"details":x.details,"starts_at":x.starts_at.isoformat(),"reminder_minutes":x.reminder_minutes} for x in JournalEvent.query.filter_by(user_id=current_user.id).all()],
        "templates": [{"name":x.name,"page_title":x.page_title,"icon":x.icon,"color":x.color,"body":x.body} for x in JournalTemplate.query.filter_by(user_id=current_user.id).all()],
        "daily_journal": [{"date":x.entry_date.isoformat(),"title":x.title,"mood":x.mood,"gratitude":x.gratitude,"wins":x.wins,"reflection":x.reflection} for x in DailyEntry.query.filter_by(user_id=current_user.id).all()],
    }
    from flask import Response
    return Response(json.dumps(data, ensure_ascii=False, indent=2), mimetype="application/json",
                    headers={"Content-Disposition":"attachment; filename=my-journal-backup.json"})

@app.errorhandler(400)
def bad_request(error):
    return render_template("error.html", code=400, message=getattr(error, "description", "درخواست نامعتبر است.")), 400

@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", code=404, message="صفحه یا مورد درخواستی پیدا نشد."), 404

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1")
