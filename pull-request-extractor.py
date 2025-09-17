#!/usr/bin/env python3
import os, sys, csv, time, json, argparse, datetime as dt
from pathlib import Path
from typing import Dict, Any, List, Optional
import requests

def log(msg: str): print(msg, flush=True)
def progress(pct: int, msg: str): print(f"PROGRESS {json.dumps({'pct': int(pct), 'msg': msg})}", flush=True)

class GitHubAPI:
    def __init__(self, token: str, base_url: str = "https://api.github.com", verbose: bool = False):
        token = token.strip().strip('"').strip("'")
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        self.verbose = verbose

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> requests.Response:
        url = f"{self.base_url}{endpoint}"
        if self.verbose:
            log(f"GET {url}  params={params or {}}")
        resp = self.session.get(url, params=params, timeout=60)
        if resp.status_code == 403 and "X-RateLimit-Remaining" in resp.headers:
            remaining = int(resp.headers.get("X-RateLimit-Remaining", "0"))
            if remaining == 0 and "X-RateLimit-Reset" in resp.headers:
                reset = int(resp.headers["X-RateLimit-Reset"])
                sleep_for = max(0, reset - int(time.time()) + 1)
                log(f"[rate limit] sleeping {sleep_for}s until reset...")
                time.sleep(sleep_for)
                return self.session.get(url, params=params, timeout=60)
        resp.raise_for_status()
        return resp

    def get_all(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        params = dict(params or {})
        params.setdefault("per_page", 100)
        page = 1
        out: List[Dict[str, Any]] = []
        while True:
            params["page"] = page
            data = self._get(endpoint, params=params).json()
            if not data: break
            out.extend(data)
            if len(data) < params["per_page"]: break
            page += 1
        return out

    # --- Endpoints ---
    def list_repo_prs(self, org: str, repo: str, state: str = "closed") -> List[Dict[str, Any]]:
        return self.get_all(f"/repos/{org}/{repo}/pulls",
                            {"state": state, "sort": "updated", "direction": "desc"})

    def list_pr_commits(self, org: str, repo: str, number: int) -> List[Dict[str, Any]]:
        return self.get_all(f"/repos/{org}/{repo}/pulls/{number}/commits")

    def list_pr_reviews(self, org: str, repo: str, number: int) -> List[Dict[str, Any]]:
        return self.get_all(f"/repos/{org}/{repo}/pulls/{number}/reviews")

    def search_merged_prs(self, org: str, repo: str, since_iso: str, until_iso: str) -> List[Dict[str, Any]]:
        # GitHub Search API for issues/PRs: filter by merged range
        # q: repo:org/repo is:pr is:merged merged:YYYY-MM-DD..YYYY-MM-DD
        q = f"repo:{org}/{repo} is:pr is:merged merged:{since_iso[:10]}..{until_iso[:10]}"
        results: List[Dict[str, Any]] = []
        page = 1
        while True:
            resp = self._get("/search/issues", {"q": q, "per_page": 100, "page": page}).json()
            items = resp.get("items") or []
            if not items: break
            results.extend(items)
            if len(items) < 100: break
            page += 1
        # Normalize to PR-like dicts (we still fetch commits/reviews below)
        for it in results:
            it["number"] = it.get("number")
            it["title"] = it.get("title")
            it["state"] = "closed"  # merged implies closed
            it["created_at"] = it.get("created_at")
            it["merged_at"] = it.get("closed_at")  # search returns closed_at for merged PRs
            it["user"] = {"login": (it.get("user") or {}).get("login", "")}
            it["merge_commit_sha"] = ""  # will be blank unless we fetch PR details; not strictly needed
            it["html_url"] = it.get("html_url")
            it["body"] = it.get("body") or ""
        return results

def normalize_iso(s: Optional[str]) -> Optional[str]:
    if not s: return None
    try:
        if len(s) == 10:
            return dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc).isoformat()
        return dt.datetime.fromisoformat(s).isoformat()
    except Exception:
        raise SystemExit(f"Invalid date format: {s}. Use YYYY-MM-DD or full ISO.")

def within_merged_window(pr: Dict[str, Any], since_iso: Optional[str], until_iso: Optional[str]) -> bool:
    merged_at = pr.get("merged_at")
    if merged_at is None: return False
    if since_iso is None and until_iso is None: return True
    if since_iso and merged_at < since_iso: return False
    if until_iso and merged_at > until_iso: return False
    return True

def pr_row(pr: Dict[str, Any], commits_count: int, reviews_count: int) -> Dict[str, Any]:
    return {
        "number": pr.get("number",""),
        "title": pr.get("title",""),
        "state": pr.get("state",""),
        "created_at": pr.get("created_at",""),
        "merged_at": pr.get("merged_at",""),
        "author": (pr.get("user") or {}).get("login",""),
        "merge_commit_sha": pr.get("merge_commit_sha",""),
        "commits_count": commits_count,
        "reviews_count": reviews_count,
        "description": pr.get("body") or "",
        "url": pr.get("html_url",""),
    }

def write_repo_csv(rows: List[Dict[str, Any]], output_dir: Path, repo: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{repo}-pull-requests.csv"
    fields = ["number","title","state","created_at","merged_at","author","merge_commit_sha",
              "commits_count","reviews_count","description","url"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for r in rows: w.writerow(r)
    log(f"OUTPUT_CSV {path}")
    return path

def main() -> int:
    ap = argparse.ArgumentParser(description="Extract GitHub Pull Requests for specified repositories.")
    ap.add_argument("--token")
    ap.add_argument("--org", default="name-of-organisation")
    ap.add_argument("--repos", nargs="+", help="Repo names (space-separated). Defaults to built-in list.")
    ap.add_argument("--output-dir", default="output")
    ap.add_argument("--since"); ap.add_argument("--until")
    ap.add_argument("--state", choices=["open","closed","all"], default="closed")
    ap.add_argument("--merged-only", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--emit-progress", action="store_true")
    ap.add_argument("--audit-log")
    args = ap.parse_args()

    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Error: GitHub token is required (pass --token or set GITHUB_TOKEN).", file=sys.stderr, flush=True)
        return 1

    since_iso = normalize_iso(args.since)
    until_iso = normalize_iso(args.until)
    apply_window = (since_iso is not None) or (until_iso is not None)

    log("\n=== Filters ===")
    log("  type:       is:pr")
    log(f"  state:      {args.state}")
    log(f"  is:merged:  {'true' if args.merged_only else 'false'}")
    if apply_window: log(f"  merged_at:  {since_iso or '-inf'}  ->  {until_iso or '+inf'}")
    else: log("  merged_at:  ALL TIME (no date window)")
    log("==============\n")

    gh = GitHubAPI(token=token, verbose=args.verbose)
    out_dir = Path(args.output_dir)
    repos = args.repos

    t0 = time.time()
    total_rows = 0

    for repo in repos:
        log(f"[{repo}] fetching PRs...")
        # Fast path: if you gave a date window AND merged_only, use Search API to pre-filter
        pr_list: List[Dict[str, Any]]
        if apply_window and args.merged_only:
            pr_list = gh.search_merged_prs(args.org, repo, since_iso or "1970-01-01T00:00:00+00:00",
                                           until_iso or dt.datetime.now(dt.timezone.utc).isoformat())
        else:
            raw = gh.list_repo_prs(args.org, repo, state=args.state)
            pr_list = [p for p in raw if (not args.merged_only or p.get("merged_at"))]
            if apply_window:
                pr_list = [p for p in pr_list if within_merged_window(p, since_iso, until_iso)]

        if args.emit_progress:
            progress(5, f"{repo}: {len(pr_list)} PRs to process")

        rows: List[Dict[str, Any]] = []
        N = max(1, len(pr_list))
        for i, pr in enumerate(pr_list, start=1):
            num = pr.get("number")
            commits = gh.list_pr_commits(args.org, repo, num)
            reviews = gh.list_pr_reviews(args.org, repo, num)
            rows.append(pr_row(pr, len(commits), len(reviews)))

            if args.emit_progress:
                pct = 5 + int(90 * (i / N))
                progress(pct, f"{repo}: processing {i}/{N}")

        write_repo_csv(rows, out_dir, repo)
        total_rows += len(rows)

    if args.emit_progress: progress(100, "Completed")

    if args.audit_log:
        try:
            with open(args.audit_log, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ts": time.time(), "tool": "pull-request-extractor",
                    "params": {"org": args.org, "repos": repos, "since": args.since, "until": args.until,
                               "state": args.state, "merged_only": bool(args.merged_only)},
                    "rows_written": total_rows, "duration_sec": time.time() - t0,
                }) + "\n")
        except Exception:
            pass

    log("\nDone.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
