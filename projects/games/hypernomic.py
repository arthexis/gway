"""Simple Nomic-style game for proposals, rules and scores."""

import html
from gway import gw
from bottle import request, redirect

RULES_TABLE = gw.resource("work", "games", "hypernomic_rules.cdv", touch=True)
PROPOSALS_TABLE = gw.resource("work", "games", "hypernomic_proposals.cdv", touch=True)
SCORES_TABLE = gw.resource("work", "games", "hypernomic_scores.cdv", touch=True)


def _next_id(records):
    ids = [int(i) for i in records if str(i).isdigit()]
    return str(max(ids or [0]) + 1)


def _load_rules():
    return gw.cdv.load_all(RULES_TABLE) or {}


def _load_proposals():
    return gw.cdv.load_all(PROPOSALS_TABLE) or {}


def _load_scores():
    return gw.cdv.load_all(SCORES_TABLE) or {}


def view_hypernomic(*, action=None, prop_text=None, author=None, vote=None, pid=None):
    """Main Hypernomic view for submitting and voting on proposals."""
    if request.method == "POST":
        if action == "new" and prop_text and author:
            recs = _load_proposals()
            new_id = _next_id(recs)
            gw.cdv.update(
                PROPOSALS_TABLE,
                new_id,
                text=prop_text,
                author=author,
                votes_for="0",
                votes_against="0",
                status="open",
            )
            return redirect("/games/hypernomic")
        elif action == "vote" and pid and vote in {"for", "against"}:
            recs = _load_proposals()
            record = recs.get(pid)
            if record:
                field = "votes_for" if vote == "for" else "votes_against"
                current = int(record.get(field, "0"))
                gw.cdv.update(PROPOSALS_TABLE, pid, **{field: str(current + 1)})
            return redirect("/games/hypernomic")

    rules = _load_rules()
    props = _load_proposals()
    scores = _load_scores()

    rule_rows = "".join(
        f"<tr><td>{rid}</td><td>{html.escape(r.get('text', ''))}</td></tr>"
        for rid, r in sorted(rules.items(), key=lambda x: int(x[0]))
    )
    score_rows = "".join(
        f"<tr><td>{html.escape(name)}</td><td>{html.escape(rec.get('score', '0'))}</td></tr>"
        for name, rec in sorted(scores.items())
    )
    prop_rows = []
    for pid_, info in sorted(props.items(), key=lambda x: int(x[0])):
        text = html.escape(info.get("text", ""))
        votes_for = info.get("votes_for", "0")
        votes_against = info.get("votes_against", "0")
        if info.get("status") != "open":
            status = html.escape(info.get("status", ""))
            prop_rows.append(
                f"<tr><td>{pid_}</td><td>{text}</td><td>{votes_for}</td><td>{votes_against}</td><td>{status}</td></tr>"
            )
        else:
            voting = (
                "<form method='post'>"
                "<input type='hidden' name='action' value='vote'>"
                f"<input type='hidden' name='pid' value='{pid_}'>"
                "<button name='vote' value='for'>For</button>"
                " <button name='vote' value='against'>Against</button>"
                "</form>"
            )
            prop_rows.append(
                f"<tr><td>{pid_}</td><td>{text}</td><td>{votes_for}</td><td>{votes_against}</td><td>{voting}</td></tr>"
            )
    prop_table = "".join(prop_rows)

    html_parts = [
        "<h1>Hypernomic</h1>",
        "<h2>Rules</h2>",
        "<table class='hn-rules'><tr><th>ID</th><th>Rule</th></tr>",
        rule_rows or "<tr><td colspan='2'>No rules yet.</td></tr>",
        "</table>",
        "<h2>Scores</h2>",
        "<table class='hn-scores'><tr><th>Player</th><th>Score</th></tr>",
        score_rows or "<tr><td colspan='2'>No scores yet.</td></tr>",
        "</table>",
        "<h2>Proposals</h2>",
        "<form method='post'><input type='hidden' name='action' value='new'>",
        "<input name='author' placeholder='Your name' required> ",
        "<textarea name='prop_text' placeholder='Proposal text' required class='main'></textarea>",
        "<button type='submit'>Submit</button></form>",
        "<table class='hn-proposals'><tr><th>ID</th><th>Text</th><th>For</th><th>Against</th><th>Vote</th></tr>",
        prop_table or "<tr><td colspan='5'>No proposals yet.</td></tr>",
        "</table>",
    ]
    return "\n".join(html_parts)


view_hypernomic._title = "Hypernomic"
