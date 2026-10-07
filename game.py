"""Pure game rules: input validation and guess scoring (no Flask / DB here)."""
import re

WORD_LENGTH = 5
MAX_GUESSES = 5
MAX_GAMES_PER_DAY = 3
SPECIAL_CHARS = "$%*"

GREEN = "green"    # right letter, right position
ORANGE = "orange"  # right letter, wrong position
GREY = "grey"      # letter not in the word

_USERNAME_RE = re.compile(r"^[A-Za-z]{5,}$")
_GUESS_RE = re.compile(r"^[A-Z]{%d}$" % WORD_LENGTH)


def validate_username(username):
    """Return an error message, or None if the username is valid."""
    if not _USERNAME_RE.match(username or ""):
        return ("Username must have at least 5 letters "
                "(upper or lower case letters only).")
    return None


def validate_password(password):
    """Return an error message, or None if the password is valid."""
    password = password or ""
    if len(password) < 5:
        return "Password must be at least 5 characters long."
    if not any(c.isalpha() for c in password):
        return "Password must contain at least one letter."
    if not any(c.isdigit() for c in password):
        return "Password must contain at least one number."
    if not any(c in SPECIAL_CHARS for c in password):
        return "Password must contain at least one special character: $ % *"
    return None


def validate_guess(guess):
    """Return an error message, or None if the guess is a valid 5-letter UPPER-CASE word."""
    if not _GUESS_RE.match(guess or ""):
        return "Enter a %d-letter word using upper-case letters only (A-Z)." % WORD_LENGTH
    return None


def score_guess(secret, guess):
    """Score a guess against the secret word.

    Returns a list of 5 colours. Duplicate letters are handled the standard
    way: a letter is only marked orange as many times as it still remains
    unmatched in the secret word.
    """
    result = [GREY] * WORD_LENGTH
    remaining = {}
    for i in range(WORD_LENGTH):
        if guess[i] == secret[i]:
            result[i] = GREEN
        else:
            remaining[secret[i]] = remaining.get(secret[i], 0) + 1
    for i in range(WORD_LENGTH):
        if result[i] == GREEN:
            continue
        if remaining.get(guess[i], 0) > 0:
            result[i] = ORANGE
            remaining[guess[i]] -= 1
    return result
