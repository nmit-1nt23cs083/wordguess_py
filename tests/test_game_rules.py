import pytest

import game


# ---------- username ----------
@pytest.mark.parametrize("name", ["Hamsh", "abcde", "ABCDEFG", "MixedCase"])
def test_valid_usernames(name):
    assert game.validate_username(name) is None


@pytest.mark.parametrize("name", ["abcd", "", "ab cde", "abc12", "user_name", None])
def test_invalid_usernames(name):
    assert game.validate_username(name) is not None


# ---------- password ----------
@pytest.mark.parametrize("pw", ["ab1$x", "Hello1%", "pass*9word", "A1*bc"])
def test_valid_passwords(pw):
    assert game.validate_password(pw) is None


@pytest.mark.parametrize("pw", [
    "a1$",          # too short
    "abcde$$$",     # no number
    "12345$%*",     # no letter
    "abcde12345",   # no special character
    "abc12#",       # '#' is not an allowed special character
    "",
    None,
])
def test_invalid_passwords(pw):
    assert game.validate_password(pw) is not None


# ---------- guess format ----------
def test_valid_guess():
    assert game.validate_guess("TOWER") is None


@pytest.mark.parametrize("g", ["tower", "TOWE", "TOWERS", "TOW3R", "TOW R", "", None])
def test_invalid_guess(g):
    assert game.validate_guess(g) is not None


# ---------- scoring ----------
G, O, X = game.GREEN, game.ORANGE, game.GREY


def test_all_green():
    assert game.score_guess("TOWER", "TOWER") == [G] * 5


def test_all_grey():
    assert game.score_guess("TOWER", "AUDIO")[:4] == [X, X, X, X]


def test_screenshot_example_sequence():
    # The sequence shown in the project's reference picture (secret = TOWER).
    assert game.score_guess("TOWER", "AUDIO") == [X, X, X, X, O]
    assert game.score_guess("TOWER", "HOMER") == [X, G, X, G, G]
    assert game.score_guess("TOWER", "JOKER") == [X, G, X, G, G]
    assert game.score_guess("TOWER", "TONER") == [G, G, X, G, G]


def test_orange_for_wrong_position():
    assert game.score_guess("APPLE", "PAPER")[0] == O  # P is in word, wrong spot


def test_duplicate_letters_not_over_marked():
    # secret has one E; guess has two Es -> only one may be coloured
    colours = game.score_guess("TOWER", "EERIE")
    assert colours.count(G) + colours.count(O) == 2  # one E and the R


def test_duplicate_letter_green_takes_priority():
    # secret APPLE: guess PPPPP -> only the two real P positions are green, rest grey
    assert game.score_guess("APPLE", "PPPPP") == [X, G, G, X, X]
