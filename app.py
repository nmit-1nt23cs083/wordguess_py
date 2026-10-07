"""Guess the Word - Flask web application.

Run:  python app.py      then open http://127.0.0.1:5000
"""
import os
import sqlite3
from datetime import datetime
from functools import wraps

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash

import db
import game as rules

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-change-me"),
        DATABASE=os.path.join(BASE_DIR, "guess_the_word.db"),
    )
    if test_config:
        app.config.update(test_config)

    with db.connect(app.config["DATABASE"]) as conn:
        db.init_db(conn)

    # ---------- per-request DB connection ----------
    def get_db():
        if "db" not in g:
            g.db = db.connect(app.config["DATABASE"])
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    @app.before_request
    def load_user():
        user_id = session.get("user_id")
        g.user = db.get_user(get_db(), user_id) if user_id else None

    # ---------- access control ----------
    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.user is None:
                flash("Please log in first.", "error")
                return redirect(url_for("login"))
            return view(*args, **kwargs)
        return wrapped

    def role_required(role):
        def decorator(view):
            @wraps(view)
            def wrapped(*args, **kwargs):
                if g.user is None:
                    flash("Please log in first.", "error")
                    return redirect(url_for("login"))
                if g.user["role"] != role:
                    abort(403)
                return view(*args, **kwargs)
            return wrapped
        return decorator

    # ---------- pages: auth ----------
    @app.route("/")
    def index():
        if g.user is None:
            return redirect(url_for("login"))
        if g.user["role"] == "admin":
            return redirect(url_for("admin_report"))
        return redirect(url_for("dashboard"))

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            error = (rules.validate_username(username)
                     or rules.validate_password(password))
            if error is None and db.get_user_by_name(get_db(), username):
                error = "That username is already taken."
            if error is None:
                try:
                    db.create_player(get_db(), username, password)
                except sqlite3.IntegrityError:
                    error = "That username is already taken."
            if error is None:
                flash("Registration successful. Please log in.", "success")
                return redirect(url_for("login"))
            flash(error, "error")
        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            user = db.get_user_by_name(get_db(), username)
            if user is None or not check_password_hash(user["password_hash"], password):
                flash("Invalid username or password.", "error")
            else:
                session.clear()
                session["user_id"] = user["id"]
                return redirect(url_for("index"))
        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        flash("You have been logged out.", "success")
        return redirect(url_for("login"))

    # ---------- pages: player ----------
    @app.route("/dashboard")
    @role_required("player")
    def dashboard():
        conn = get_db()
        played = db.games_played_today(conn, g.user["id"], db.today())
        active = db.get_active_game(conn, g.user["id"])
        return render_template(
            "dashboard.html",
            played=played,
            remaining=max(0, rules.MAX_GAMES_PER_DAY - played),
            max_games=rules.MAX_GAMES_PER_DAY,
            active=active,
        )

    @app.route("/play", methods=["POST"])
    @role_required("player")
    def play():
        """Start a new game (or resume the unfinished one)."""
        conn = get_db()
        active = db.get_active_game(conn, g.user["id"])
        if active:
            return redirect(url_for("game_page", game_id=active["id"]))
        day = db.today()
        if db.games_played_today(conn, g.user["id"], day) >= rules.MAX_GAMES_PER_DAY:
            flash("You can play only %d words per day. Come back tomorrow!"
                  % rules.MAX_GAMES_PER_DAY, "error")
            return redirect(url_for("dashboard"))
        game_id = db.start_game(conn, g.user["id"], day)
        return redirect(url_for("game_page", game_id=game_id))

    def own_game_or_404(game_id):
        row = db.get_game(get_db(), game_id)
        if row is None or row["user_id"] != g.user["id"]:
            abort(404)
        return row

    def build_board(secret, guesses):
        rows = []
        for item in guesses:
            colours = rules.score_guess(secret, item["guess"])
            rows.append(list(zip(item["guess"], colours)))
        return rows

    @app.route("/game/<int:game_id>")
    @role_required("player")
    def game_page(game_id):
        row = own_game_or_404(game_id)
        guesses = db.get_guesses(get_db(), game_id)
        board = build_board(row["word"], guesses)
        return render_template(
            "game.html",
            game=row,
            board=board,
            blank_rows=rules.MAX_GUESSES - len(board),
            max_guesses=rules.MAX_GUESSES,
            word_length=rules.WORD_LENGTH,
        )

    @app.route("/game/<int:game_id>/guess", methods=["POST"])
    @role_required("player")
    def submit_guess(game_id):
        conn = get_db()
        row = own_game_or_404(game_id)
        if row["status"] != "active":
            flash("This game is already over.", "error")
            return redirect(url_for("game_page", game_id=game_id))

        guess = request.form.get("guess", "").strip()
        error = rules.validate_guess(guess)
        if error:
            flash(error, "error")
            return redirect(url_for("game_page", game_id=game_id))

        guess_no = len(db.get_guesses(conn, game_id)) + 1
        db.add_guess(conn, game_id, guess_no, guess, db.today())

        if guess == row["word"]:
            db.set_game_status(conn, game_id, "won")
        elif guess_no >= rules.MAX_GUESSES:
            db.set_game_status(conn, game_id, "lost")
        return redirect(url_for("game_page", game_id=game_id))

    # ---------- pages: admin ----------
    @app.route("/admin/report")
    @role_required("admin")
    def admin_report():
        day = request.args.get("date") or db.today()
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError:
            flash("Invalid date. Use YYYY-MM-DD.", "error")
            day = db.today()
        summary, total_guesses, details = db.daily_report(get_db(), day)
        return render_template("report.html", day=day, summary=summary,
                               total_guesses=total_guesses, details=details)

    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("error.html", code=403,
                               message="You do not have access to this page."), 403

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("error.html", code=404,
                               message="Page not found."), 404

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
