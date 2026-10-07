import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402
from app import create_app  # noqa: E402


@pytest.fixture
def app(tmp_path):
    return create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.db"),
                       "SECRET_KEY": "test"})


@pytest.fixture
def client(app):
    return app.test_client()


def conn_for(app):
    return db.connect(app.config["DATABASE"])


def register(client, username="Player", password="Pass$123"):
    return client.post("/register", data={"username": username, "password": password},
                       follow_redirects=True)


def login(client, username="Player", password="Pass$123"):
    return client.post("/login", data={"username": username, "password": password},
                       follow_redirects=True)


def start_game(client):
    resp = client.post("/play")
    assert resp.status_code == 302
    return int(resp.headers["Location"].rstrip("/").split("/")[-1])


def secret_of(app, game_id):
    with conn_for(app) as c:
        return db.get_game(c, game_id)["word"]


def wrong_word(secret):
    return "ZZZZZ" if secret != "ZZZZZ" else "YYYYY"


@pytest.fixture
def player(client):
    register(client)
    login(client)
    return client


# ---------- database seed ----------
def test_twenty_five_letter_words_seeded(app):
    with conn_for(app) as c:
        words = [r["word"] for r in c.execute("SELECT word FROM words")]
    assert len(words) == 20
    assert all(len(w) == 5 and w.isalpha() and w == w.upper() for w in words)


def test_init_db_is_idempotent(app):
    with conn_for(app) as c:
        db.init_db(c)
        assert c.execute("SELECT COUNT(*) FROM words").fetchone()[0] == 20
        assert c.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0] == 1


# ---------- registration & login ----------
def test_register_success_and_password_is_hashed(client, app):
    resp = register(client)
    assert b"Registration successful" in resp.data
    with conn_for(app) as c:
        user = db.get_user_by_name(c, "Player")
    assert user["role"] == "player"
    assert user["password_hash"] != "Pass$123"


@pytest.mark.parametrize("username,password,msg", [
    ("abcd", "Pass$123", b"at least 5 letters"),
    ("Player", "ab1", b"at least 5 characters"),
    ("Player", "abcdefgh", b"number"),
    ("Player", "abcde123", b"special character"),
])
def test_register_validation_errors(client, username, password, msg):
    resp = register(client, username, password)
    assert msg in resp.data


def test_register_duplicate_username_case_insensitive(client):
    register(client, "Player")
    resp = register(client, "PLAYER")
    assert b"already taken" in resp.data


def test_login_wrong_password(client):
    register(client)
    assert b"Invalid username or password" in login(client, password="Wrong$999").data


def test_login_and_logout(client):
    register(client)
    assert b"Welcome, Player" in login(client).data
    assert b"logged out" in client.get("/logout", follow_redirects=True).data


def test_anonymous_redirected_to_login(client):
    assert client.get("/dashboard").status_code == 302
    assert client.get("/admin/report").status_code == 302


def test_player_cannot_open_admin_report(player):
    assert player.get("/admin/report").status_code == 403


def test_admin_cannot_play(client):
    login(client, "Admin", "Admin$123")
    assert client.post("/play").status_code == 403


# ---------- gameplay ----------
def test_start_game_gives_word_from_database(player, app):
    gid = start_game(player)
    assert secret_of(app, gid) in db.SEED_WORDS


def test_winning_game(player, app):
    gid = start_game(player)
    secret = secret_of(app, gid)
    resp = player.post(f"/game/{gid}/guess", data={"guess": secret}, follow_redirects=True)
    assert b"Congratulations" in resp.data
    with conn_for(app) as c:
        assert db.get_game(c, gid)["status"] == "won"


def test_losing_after_five_guesses(player, app):
    gid = start_game(player)
    bad = wrong_word(secret_of(app, gid))
    for i in range(4):
        resp = player.post(f"/game/{gid}/guess", data={"guess": bad}, follow_redirects=True)
        assert b"Better luck next time" not in resp.data
    resp = player.post(f"/game/{gid}/guess", data={"guess": bad}, follow_redirects=True)
    assert b"Better luck next time" in resp.data
    with conn_for(app) as c:
        assert db.get_game(c, gid)["status"] == "lost"
        assert len(db.get_guesses(c, gid)) == 5


def test_no_guess_after_game_over(player, app):
    gid = start_game(player)
    secret = secret_of(app, gid)
    player.post(f"/game/{gid}/guess", data={"guess": secret})
    resp = player.post(f"/game/{gid}/guess", data={"guess": secret}, follow_redirects=True)
    assert b"already over" in resp.data
    with conn_for(app) as c:
        assert len(db.get_guesses(c, gid)) == 1


@pytest.mark.parametrize("bad_input", ["tower", "TOWE", "TOWERS", "TOW3R", ""])
def test_invalid_guess_rejected_and_not_counted(player, app, bad_input):
    gid = start_game(player)
    resp = player.post(f"/game/{gid}/guess", data={"guess": bad_input}, follow_redirects=True)
    assert b"upper-case letters only" in resp.data
    with conn_for(app) as c:
        assert db.get_guesses(c, gid) == []


def test_colours_and_order_of_earlier_guesses(player, app):
    gid = start_game(player)
    secret = secret_of(app, gid)
    first = wrong_word(secret)
    player.post(f"/game/{gid}/guess", data={"guess": first})
    # a second guess that is partly right: first 4 letters of secret + a different last letter
    second = secret[:4] + ("A" if secret[4] != "A" else "B")
    player.post(f"/game/{gid}/guess", data={"guess": second})
    html = player.get(f"/game/{gid}").get_data(as_text=True)
    assert html.index(first[0]) >= 0
    assert html.count('class="tile green"') >= 4
    assert html.count('class="tile grey"') >= 5      # the first (all wrong) guess
    assert html.count('class="tile empty"') == 3 * 5  # 3 unused rows remain


def test_unfinished_game_is_resumed(player):
    first = start_game(player)
    assert start_game(player) == first


def test_game_belongs_to_its_owner(client, player):
    gid = start_game(player)
    player.get("/logout")
    register(client, "Other", "Pass$123")
    login(client, "Other", "Pass$123")
    assert client.get(f"/game/{gid}").status_code == 404
    assert client.post(f"/game/{gid}/guess", data={"guess": "TOWER"}).status_code == 404


def finish_game(client, app):
    gid = start_game(client)
    client.post(f"/game/{gid}/guess", data={"guess": secret_of(app, gid)})
    return gid


def test_max_three_words_per_day(player, app):
    for _ in range(3):
        finish_game(player, app)
    resp = player.post("/play", follow_redirects=True)
    assert b"only 3 words per day" in resp.data
    with conn_for(app) as c:
        assert c.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 3


def test_daily_limit_resets_next_day(player, app, monkeypatch):
    for _ in range(3):
        finish_game(player, app)
    monkeypatch.setattr(db, "today", lambda: "2099-01-01")
    assert player.post("/play").status_code == 302
    with conn_for(app) as c:
        assert c.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 4


def test_words_and_guesses_saved_with_date(player, app):
    gid = start_game(player)
    secret = secret_of(app, gid)
    bad = wrong_word(secret)
    player.post(f"/game/{gid}/guess", data={"guess": bad})
    player.post(f"/game/{gid}/guess", data={"guess": secret})
    with conn_for(app) as c:
        game = db.get_game(c, gid)
        rows = c.execute("SELECT guess_no, guess, guess_date FROM guesses "
                         "WHERE game_id = ? ORDER BY guess_no", (gid,)).fetchall()
    assert game["game_date"] == db.today()
    assert [(r["guess_no"], r["guess"]) for r in rows] == [(1, bad), (2, secret)]
    assert all(r["guess_date"] == db.today() for r in rows)


# ---------- admin report ----------
def test_admin_report_counts(app):
    # two players: A wins a game and loses one; B starts a game and does nothing
    a = app.test_client()
    register(a, "Alpha", "Pass$123")
    login(a, "Alpha", "Pass$123")
    finish_game(a, app)
    gid = start_game(a)
    bad = wrong_word(secret_of(app, gid))
    for _ in range(5):
        a.post(f"/game/{gid}/guess", data={"guess": bad})

    b = app.test_client()
    register(b, "Bravo", "Pass$123")
    login(b, "Bravo", "Pass$123")
    start_game(b)

    admin = app.test_client()
    resp = login(admin, "Admin", "Admin$123")
    assert b"Daily report" in resp.data
    with conn_for(app) as c:
        summary, total_guesses, details = db.daily_report(c, db.today())
    assert summary["users"] == 2
    assert summary["games"] == 3
    assert summary["correct"] == 1
    assert summary["lost"] == 1
    assert summary["in_progress"] == 1
    assert total_guesses == 6
    assert len(details) == 3

    html = admin.get("/admin/report?date=" + db.today()).get_data(as_text=True)
    assert "Alpha" in html and "Bravo" in html


def test_admin_report_other_day_is_empty(client):
    login(client, "Admin", "Admin$123")
    html = client.get("/admin/report?date=2000-01-01").get_data(as_text=True)
    assert "No games were played" in html


def test_admin_report_bad_date_falls_back_to_today(client):
    login(client, "Admin", "Admin$123")
    resp = client.get("/admin/report?date=not-a-date")
    assert b"Invalid date" in resp.data
