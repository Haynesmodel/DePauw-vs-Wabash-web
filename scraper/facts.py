"""
Numbers worked out from a sport's game list: the Monon Bell standings and (later) the per-sport fun facts.

Pure functions over the games in data/series.json (dicts with date, result, depauw, wabash, ...).
Results are from DePauw's side: "W" is a DePauw win, "L" a Wabash win, "T" a tie.
"""

from __future__ import annotations

# The football game became the Monon Bell game with the 1932 season.
BELL_START = 1932


def bell(games: list) -> dict | None:
    """The Monon Bell standings from the games played for it.

    The holder is whoever won the most recent Bell game that was not a tie: a tie leaves the Bell where
    it is. "since" is the year of the holder's first win in the unbroken run of wins and ties that
    ends today, and "held_games" counts the games in that run (the wins and the ties in between).
    Returns None when there are no Bell games, or when none was ever decided.
    """
    played = sorted((g for g in games if int(g["date"][:4]) >= BELL_START), key=lambda g: g["date"])
    if not played:
        return None
    out = {
        "depauw": sum(1 for g in played if g["result"] == "W"),
        "wabash": sum(1 for g in played if g["result"] == "L"),
        "ties": sum(1 for g in played if g["result"] == "T"),
        "games": len(played),
        "last": played[-1],
        "holder": None, "since": None, "held_games": 0,
    }
    decided = [g for g in played if g["result"] != "T"]
    if not decided:
        return out
    holder_result = decided[-1]["result"]               # "W": DePauw holds it, "L": Wabash does
    run_start = None
    for i in range(len(played) - 1, -1, -1):
        r = played[i]["result"]
        if r == "T":
            continue
        if r != holder_result:
            break
        run_start = i
    out["holder"] = "DePauw" if holder_result == "W" else "Wabash"
    out["since"] = int(played[run_start]["date"][:4])
    out["held_games"] = len(played) - run_start
    return out
