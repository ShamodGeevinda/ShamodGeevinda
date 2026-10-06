"""Render the profile stats card from the GitHub GraphQL API.

Usage: python3 stats_card.py OUTPUT_SVG

Reads STATS_TOKEN (a personal access token, so private activity is counted)
and falls back to GITHUB_TOKEN, which only sees public activity.
GITHUB_USER is the account to report on.
"""

import datetime as dt
import json
import os
import sys
import urllib.request

API = "https://api.github.com/graphql"

PROFILE_QUERY = """
query($login: String!, $after: String) {
  user(login: $login) {
    createdAt
    pullRequests { totalCount }
    issues { totalCount }
    repositories(ownerAffiliations: OWNER, first: 100, after: $after) {
      nodes { stargazerCount }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

COMMITS_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) { totalCommitContributions }
  }
}
"""

# Octicons, 16px.
ICONS = {
    "star": "M8 .25a.75.75 0 01.673.418l1.882 3.815 4.21.612a.75.75 0 01.416 1.279l-3.046 2.97.719 4.192a.75.75 0 01-1.088.791L8 12.347l-3.766 1.98a.75.75 0 01-1.088-.79l.72-4.194L.818 6.374a.75.75 0 01.416-1.28l4.21-.611L7.327.668A.75.75 0 018 .25zm0 2.445L6.615 5.5a.75.75 0 01-.564.41l-3.097.45 2.24 2.184a.75.75 0 01.216.664l-.528 3.084 2.769-1.456a.75.75 0 01.698 0l2.77 1.456-.53-3.084a.75.75 0 01.216-.664l2.24-2.183-3.096-.45a.75.75 0 01-.564-.41L8 2.694v.001z",
    "commits": "M1.643 3.143L.427 1.927A.25.25 0 000 2.104V5.75c0 .138.112.25.25.25h3.646a.25.25 0 00.177-.427L2.715 4.215a6.5 6.5 0 11-1.18 4.458.75.75 0 10-1.493.154 8.001 8.001 0 101.6-5.684zM7.75 4a.75.75 0 01.75.75v2.992l2.028.812a.75.75 0 01-.557 1.392l-2.5-1A.75.75 0 017 8.25v-3.5A.75.75 0 017.75 4z",
    "prs": "M7.177 3.073L9.573.677A.25.25 0 0110 .854v4.792a.25.25 0 01-.427.177L7.177 3.427a.25.25 0 010-.354zM3.75 2.5a.75.75 0 100 1.5.75.75 0 000-1.5zm-2.25.75a2.25 2.25 0 113 2.122v5.256a2.251 2.251 0 11-1.5 0V5.372A2.25 2.25 0 011.5 3.25zM11 2.5h-1V4h1a1 1 0 011 1v5.628a2.251 2.251 0 101.5 0V5A2.5 2.5 0 0011 2.5zm1 10.25a.75.75 0 111.5 0 .75.75 0 01-1.5 0zM3.75 12a.75.75 0 100 1.5.75.75 0 000-1.5z",
    "issues": "M8 9.5a1.5 1.5 0 100-3 1.5 1.5 0 000 3zM8 0a8 8 0 100 16A8 8 0 008 0zM1.5 8a6.5 6.5 0 1113 0 6.5 6.5 0 01-13 0z",
}


def graphql(token, query, **variables):
    request = urllib.request.Request(
        API,
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.load(response)
    if body.get("errors"):
        raise RuntimeError(f"GraphQL error: {body['errors']}")
    return body["data"]


def fetch_stats(token, login):
    stars, after = 0, None
    while True:
        user = graphql(token, PROFILE_QUERY, login=login, after=after)["user"]
        repos = user["repositories"]
        stars += sum(repo["stargazerCount"] for repo in repos["nodes"])
        if not repos["pageInfo"]["hasNextPage"]:
            break
        after = repos["pageInfo"]["endCursor"]

    # contributionsCollection spans at most one year, so add up each year
    # since the account was created. These are the commits shown on the
    # profile contribution graph.
    now = dt.datetime.now(dt.timezone.utc)
    created = dt.datetime.fromisoformat(user["createdAt"].replace("Z", "+00:00"))
    commits = 0
    for year in range(created.year, now.year + 1):
        start = max(created, dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc))
        end = min(now, dt.datetime(year, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc))
        data = graphql(token, COMMITS_QUERY, login=login, **{"from": start.isoformat(), "to": end.isoformat()})
        commits += data["user"]["contributionsCollection"]["totalCommitContributions"]

    return {
        "stars": stars,
        "commits": commits,
        "prs": user["pullRequests"]["totalCount"],
        "issues": user["issues"]["totalCount"],
    }


def render(stats, updated, private):
    rows = [
        ("star", "Total Stars:", stats["stars"]),
        ("commits", "Total Commits:", stats["commits"]),
        ("prs", "Total PRs:", stats["prs"]),
        ("issues", "Total Issues:", stats["issues"]),
    ]
    row_svg = "".join(
        f'<g transform="translate(25, {55 + i * 25})">'
        f'<svg class="icon" viewBox="0 0 16 16" width="16" height="16"><path fill-rule="evenodd" d="{ICONS[icon]}"/></svg>'
        f'<text class="label" x="25" y="12.5">{label}</text>'
        f'<text class="label" x="170" y="12.5">{value:,}</text>'
        "</g>"
        for i, (icon, label, value) in enumerate(rows)
    )
    scope = "includes private activity" if private else "public activity only"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="380" height="180" viewBox="0 0 380 180" role="img" aria-labelledby="title">
<title id="title">My GitHub Statistics</title>
<style>
.header {{ font: 600 18px 'Segoe UI', Ubuntu, Sans-Serif; fill: #00AEFF; }}
.label {{ font: 600 14px 'Segoe UI', Ubuntu, 'Helvetica Neue', Sans-Serif; fill: #FFFFFF; }}
.icon {{ fill: #2DDE98; }}
.note {{ font: 400 11px 'Segoe UI', Ubuntu, Sans-Serif; fill: #8B949E; }}
</style>
<rect x="0.5" y="0.5" rx="4.5" width="379" height="179" fill="#050F2C" stroke="#E4E2E2"/>
<text class="header" x="25" y="35">My GitHub Statistics</text>
{row_svg}
<text class="note" x="25" y="166">Updated {updated:%b %-d, %Y} · {scope}</text>
</svg>
"""


def main():
    output = sys.argv[1]
    login = os.environ["GITHUB_USER"]
    token = os.environ.get("STATS_TOKEN")
    private = bool(token)
    if not private:
        print("::warning::STATS_TOKEN is not set; the card will count public activity only.")
        token = os.environ["GITHUB_TOKEN"]

    stats = fetch_stats(token, login)
    print(f"Stats for {login}: {stats}")
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        f.write(render(stats, dt.datetime.now(dt.timezone.utc), private))


if __name__ == "__main__":
    main()
