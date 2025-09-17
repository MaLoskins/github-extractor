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
            if not data:
                break
            out.extend(data)
            if len(data) < params["per_page"]:
                break
            page += 1
        return out

    def list_commits_for_path(self, org: str, repo: str, path: str,
                              since_iso: Optional[str] = None, until_iso: Optional[str] = None,
                              sha: Optional[str] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"path": path}
        if since_iso: params["since"] = since_iso
        if until_iso: params["until"] = until_iso
        if sha: params["sha"] = sha
        return self.get_all(f"/repos/{org}/{repo}/commits", params=params)

    def get_commit(self, org: str, repo: str, sha: str) -> Dict[str, Any]:
        return self._get(f"/repos/{org}/{repo}/commits/{sha}").json()

def normalize_iso(s: Optional[str]) -> Optional[str]:
    if not s: return None
    try:
        if len(s) == 10:
            return dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc).isoformat()
        return dt.datetime.fromisoformat(s).isoformat()
    except Exception:
        raise SystemExit(f"Invalid date format: {s}. Use YYYY-MM-DD or full ISO.")

def csv_row_from_commit(org: str, repo: str, file_path: str,
                        commit_summary: Dict[str, Any], commit_detail: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    sha = commit_summary.get("sha", "")
    html_url = commit_summary.get("html_url", "")
    commit_url = f"https://github.com/{org}/{repo}/commit/{sha}"

    commit_info = commit_summary.get("commit", {}) or {}
    author_info = commit_info.get("author", {}) or {}
    message = (commit_info.get("message") or "").replace("\r\n", " ").replace("\n", " ")

    author_login = (commit_summary.get("author") or {}).get("login", "")
    author_name = author_info.get("name", "")
    author_email = author_info.get("email", "")
    commit_date = author_info.get("date", "")

    committer_login = (commit_summary.get("committer") or {}).get("login", "")

    files = commit_detail.get("files") or []
    file_rec = None
    for f in files:
        if f.get("filename") == file_path or f.get("previous_filename") == file_path:
            file_rec = f
            break
    if not file_rec:
        return None

    return {
        "repo": repo, "file_path": file_path, "commit_sha": sha,
        "html_url": html_url, "commit_url": commit_url, "commit_date": commit_date,
        "author_login": author_login, "author_name": author_name, "author_email": author_email,
        "committer_login": committer_login, "message": message,
        "status": file_rec.get("status",""), "previous_filename": file_rec.get("previous_filename",""),
        "additions": file_rec.get("additions",0), "deletions": file_rec.get("deletions",0),
        "changes": file_rec.get("changes",0),
    }

def write_repo_csv(rows: List[Dict[str, Any]], output_dir: Path, repo: str, file_path: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_suffix = file_path.strip("/").replace("/", "-")
    outpath = output_dir / f"{repo}-{safe_suffix}-file-history.csv"
    fields = ["repo","file_path","commit_sha","html_url","commit_url","commit_date","author_login","author_name",
              "author_email","committer_login","message","status","previous_filename","additions","deletions","changes"]
    with outpath.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        def _key(r): return r.get("commit_date") or ""
        for r in sorted(rows, key=_key, reverse=True): w.writerow(r)
    log(f"OUTPUT_CSV {outpath}")
    return outpath

def main() -> int:
    ap = argparse.ArgumentParser(description="Extract per-file commit history for specified repositories.")
    ap.add_argument("--token")
    ap.add_argument("--org", default="name-of-organisation")
    ap.add_argument("--repos", nargs="+", required=True)
    ap.add_argument("--file-path", required=True)
    ap.add_argument("--output-dir", default="output")
    ap.add_argument("--since"); ap.add_argument("--until"); ap.add_argument("--sha")
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
    log("  type:        commits (per-file)")
    log(f"  org:         {args.org}")
    log(f"  repos:       {', '.join(args.repos)}")
    log(f"  file_path:   {args.file_path}")
    if args.sha: log(f"  sha:         {args.sha}")
    if apply_window: log(f"  date:        {since_iso or '-inf'}  ->  {until_iso or '+inf'}")
    else: log("  date:        ALL TIME (no date window)")
    log("===============\n")

    gh = GitHubAPI(token=token, verbose=args.verbose)
    out_dir = Path(args.output_dir)
    total_rows = 0
    t0 = time.time()

    if args.emit_progress: progress(1, "Listing commits...")

    for repo in args.repos:
        log(f"[{repo}] listing commits touching {args.file_path}...")
        commits = gh.list_commits_for_path(org=args.org, repo=repo, path=args.file_path,
                                           since_iso=since_iso, until_iso=until_iso, sha=args.sha)
        if args.emit_progress: progress(10, f"{repo}: {len(commits)} commits found")

        rows: List[Dict[str, Any]] = []
        N = max(1, len(commits))
        for i, c in enumerate(commits, start=1):
            sha = c.get("sha")
            if not sha: continue
            detail = gh.get_commit(args.org, repo, sha)
            row = csv_row_from_commit(args.org, repo, args.file_path, c, detail)
            if row: rows.append(row)
            if args.emit_progress:
                pct = 10 + int(80 * (i / N))
                progress(pct, f"{repo}: processing {i}/{N}")

        write_repo_csv(rows, out_dir, repo, args.file_path)
        total_rows += len(rows)

    if args.emit_progress: progress(100, "Completed")

    if args.audit_log:
        try:
            with open(args.audit_log, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ts": time.time(), "tool": "file-commit-history",
                    "params": {"org": args.org, "repos": args.repos, "file_path": args.file_path,
                               "since": args.since, "until": args.until, "sha": args.sha},
                    "rows_written": total_rows, "duration_sec": time.time() - t0,
                }) + "\n")
        except Exception:
            pass

    log(f"\nDone. Rows written: {total_rows}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
