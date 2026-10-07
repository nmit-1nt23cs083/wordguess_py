# Guess the Word

A Wordle-style web game written in **Python (Flask + SQLite)**.
Players register, log in and try to guess a hidden 5-letter word in at most 5 guesses.
Admins log in to see a daily report.

## Features (mapped to the specification)

| Requirement | Where it is implemented |
|---|---|
| Two user types: **Admin** and **Player** | `users.role` column; `role_required()` in `app.py` |
| Register / log in with username + password | `/register`, `/login` in `app.py` (passwords stored hashed) |
| Username: at least 5 letters, upper/lower case | `validate_username()` in `game.py` |
| Password: at least 5 chars, letters + numbers + one of `$ % *` | `validate_password()` in `game.py` |
| 20 five-letter upper-case words saved in the database | `SEED_WORDS` in `db.py`, seeded by `init_db()` |
| Random word per game | `pick_random_word()` in `db.py` |
| Max **3 words per user per day** | `MAX_GAMES_PER_DAY` in `game.py`, checked in `/play` |
| Max **5 guesses**, 5-letter upper-case words only | `validate_guess()`, `MAX_GUESSES` |
| Green / orange / grey highlighting | `score_guess()` in `game.py` (handles repeated letters correctly) |
| Win -> congratulations; 5 wrong -> "Better luck next time"; **OK** ends the game | modal in `templates/game.html` |
| Earlier guesses shown in the same order | board rendered from the saved guesses |
| Words given and words guessed saved with date | tables `games` and `guesses` |
| Admin report for a day (users, correct guesses, ...) | `/admin/report?date=YYYY-MM-DD` |

## Project structure

```
guess_the_word/
├── app.py            # Flask routes (auth, game, admin report)
├── db.py             # SQLite schema, seed data, queries
├── game.py           # Validation rules and guess scoring (pure functions)
├── templates/        # HTML pages (login, register, dashboard, game, report)
├── static/style.css
├── tests/            # pytest tests (66 tests)
├── requirements.txt
└── README.md
```

## Run it

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5000>.

The database file `guess_the_word.db` is created automatically on first run, with
the 20 words and a default admin account:

| Role | Username | Password |
|---|---|---|
| Admin | `Admin` | `Admin$123` |

Players create their own accounts on the **Register** page. Admin accounts are not
self-registered; change the default admin password in `db.py` before real use.

## Run the tests

```bash
python -m pytest -v
```

The tests cover username/password validation, guess validation, colour scoring
(including the TOWER example from the project picture and repeated letters),
registration and login, access control, winning/losing, the 5-guess limit,
the 3-games-per-day limit (and its reset the next day), data saved in the
database, and the admin report numbers.

## Notes

- Guesses must be **upper-case A-Z, exactly 5 letters**. The browser input converts
  typing to upper case automatically; the server also rejects anything else.
- An unfinished game is resumed when the player comes back, and it counts toward the
  3-per-day limit as soon as it is started.
- "Correct guesses" in the admin report is the number of games won that day.
- Only `$ % *` count as special characters for passwords, as in the specification.

## Git / GitHub

```bash
git init
git add .
git commit -m "Guess the Word: Flask + SQLite implementation"
git branch -M main
git remote add origin https://github.com/<your-username>/guess-the-word.git
git push -u origin main
```
