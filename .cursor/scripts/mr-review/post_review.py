#!/usr/bin/env python3
"""
Post review findings from a REVIEW_MR<IID>.md file as GitLab MR discussions.

Each R-NN section in the review doc becomes one MR discussion note.
The script shows a preview table and waits for confirmation before posting.

GITLAB_HOST is auto-detected from the git remote of the current directory if
not set in the environment; only GITLAB_TOKEN needs to be provided explicitly.

Usage:
    python3 post_review.py --review-file path/to/REVIEW_MR4.md \\
                           --mr-url http://host/namespace/project/-/merge_requests/4

    # Or supply project + iid directly (host auto-detected from git remote):
    python3 post_review.py --review-file path/to/REVIEW_MR4.md \\
                           --project jojijose/workspace-settings --iid 4

Environment:
    GITLAB_TOKEN  Personal access token with api scope (required for posting)
    GITLAB_HOST   GitLab hostname — auto-detected from git remote if not set

Optional line annotations in the review file:
    Add <!-- file: path/to/file.md, line: 12 --> immediately after an R-NN
    heading to post that finding as a diff-level comment on that file/line.
    Example:
        ## R-01 · Some finding [minor]
        <!-- file: .cursor/commands/mr.md, line: 3 -->
"""

import argparse
import json
import os
import subprocess
import re
import sys
import urllib.parse
import urllib.request


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(
    r'^##\s+(R-\d+)\s+[·•]\s+(.+?)\s+\[(major|minor|info)\]\s*$',
    re.MULTILINE,
)
_ANNOTATION_RE = re.compile(
    r'<!--\s*file:\s*(.+?),\s*line:\s*(\d+)\s*-->',
)
_REVIEW_LABEL_RE = re.compile(r'\*\*Review:\*\*', re.MULTILINE)
_SEPARATOR_RE = re.compile(r'^---\s*$', re.MULTILINE)


def parse_findings(text: str) -> list[dict]:
    """
    Parse R-NN sections from the review markdown into a list of dicts:
        id, title, severity, description, review_action, diff_file, diff_line
    """
    matches = list(_HEADING_RE.finditer(text))
    findings = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section = text[start:end]

        # Check for diff annotation on the line immediately after the heading
        lines_after = section[m.end() - start:].lstrip('\n').split('\n')
        diff_file = diff_line = None
        ann_match = _ANNOTATION_RE.search(lines_after[0] if lines_after else '')
        if ann_match:
            diff_file = ann_match.group(1).strip()
            diff_line = int(ann_match.group(2))

        # Split into description (before **Review:**) and action (after)
        rv_match = _REVIEW_LABEL_RE.search(section)
        if rv_match:
            description = section[m.end() - start: rv_match.start()].strip()
            # strip trailing separator
            action_raw = section[rv_match.end():].strip()
            action = _SEPARATOR_RE.split(action_raw)[0].strip()
        else:
            description = section[m.end() - start:].strip()
            description = _SEPARATOR_RE.split(description)[0].strip()
            action = ''

        findings.append({
            'id': m.group(1),
            'title': m.group(2).strip(),
            'severity': m.group(3),
            'description': description,
            'review_action': action,
            'diff_file': diff_file,
            'diff_line': diff_line,
        })
    return findings


# ---------------------------------------------------------------------------
# GitLab API helpers
# ---------------------------------------------------------------------------

SEVERITY_EMOJI = {'major': '🔴', 'minor': '🟡', 'info': '🔵'}


def _api(host: str, token: str, method: str, path: str, body: dict | None = None,
         scheme: str = 'https'):
    url = f'{scheme}://{host}/api/v4{path}'
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            'PRIVATE-TOKEN': token,
            'Content-Type': 'application/json',
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors='replace')
        raise RuntimeError(f'HTTP {e.code} {e.reason}: {body_text}') from e


def get_project_id(host: str, token: str, project_path: str, scheme: str = 'https') -> int:
    encoded = urllib.parse.quote(project_path, safe='')
    result = _api(host, token, 'GET', f'/projects/{encoded}', scheme=scheme)
    return result['id']


def get_mr_shas(host: str, token: str, project_id: int, iid: int,
                scheme: str = 'https') -> dict:
    """Return base_sha, start_sha, head_sha for diff position."""
    result = _api(host, token, 'GET',
                  f'/projects/{project_id}/merge_requests/{iid}/versions',
                  scheme=scheme)
    if not result:
        raise RuntimeError('No diff versions found for this MR.')
    latest = result[0]
    return {
        'base_sha': latest['base_commit_sha'],
        'start_sha': latest['start_commit_sha'],
        'head_sha': latest['head_commit_sha'],
    }


def post_note(host: str, token: str, project_id: int, iid: int, body: str,
              scheme: str = 'https', draft: bool = True) -> dict:
    """Post a general MR note. draft=True posts as pending (visible only to you)."""
    if draft:
        return _api(host, token, 'POST',
                    f'/projects/{project_id}/merge_requests/{iid}/draft_notes',
                    {'note': body}, scheme=scheme)
    return _api(host, token, 'POST',
                f'/projects/{project_id}/merge_requests/{iid}/discussions',
                {'body': body}, scheme=scheme)


def post_diff_note(host: str, token: str, project_id: int, iid: int,
                   body: str, shas: dict, file_path: str, new_line: int,
                   scheme: str = 'https', draft: bool = True) -> dict:
    """Post a diff-level note. draft=True posts as pending (visible only to you)."""
    if draft:
        return _api(host, token, 'POST',
                    f'/projects/{project_id}/merge_requests/{iid}/draft_notes',
                    {
                        'note': body,
                        'position': {
                            'position_type': 'text',
                            'base_sha': shas['base_sha'],
                            'start_sha': shas['start_sha'],
                            'head_sha': shas['head_sha'],
                            'new_path': file_path,
                            'new_line': new_line,
                        },
                    }, scheme=scheme)
    return _api(host, token, 'POST',
                f'/projects/{project_id}/merge_requests/{iid}/discussions',
                {
                    'body': body,
                    'position': {
                        'position_type': 'text',
                        'base_sha': shas['base_sha'],
                        'start_sha': shas['start_sha'],
                        'head_sha': shas['head_sha'],
                        'new_path': file_path,
                        'new_line': new_line,
                    },
                }, scheme=scheme)


def publish_draft_notes(host: str, token: str, project_id: int, iid: int,
                        scheme: str = 'https') -> None:
    """Publish all pending draft notes for this MR at once."""
    _api(host, token, 'POST',
         f'/projects/{project_id}/merge_requests/{iid}/draft_notes/bulk_publish',
         {}, scheme=scheme)


def get_diff_map(host: str, token: str, project_id: int, iid: int,
                 scheme: str = 'https') -> dict:
    """
    Return a map: { file_path: [ (new_line_number, line_content), ... ] }
    Only includes added/context lines that carry a new-side line number.
    """
    diffs = _api(host, token, 'GET',
                 f'/projects/{project_id}/merge_requests/{iid}/diffs',
                 scheme=scheme)
    result = {}
    for d in diffs:
        path = d['new_path']
        lines = []
        new_line = 0
        for raw in d['diff'].splitlines():
            if raw.startswith('@@'):
                m = re.search(r'\+(\d+)', raw)
                new_line = int(m.group(1)) - 1 if m else 0
            elif raw.startswith('-'):
                pass  # removed line — no new-side number
            else:
                new_line += 1
                content = raw[1:] if raw.startswith('+') else raw
                lines.append((new_line, content))
        if lines:
            result[path] = lines
    return result


def auto_locate(finding: dict, diff_map: dict) -> tuple[str, int] | None:
    """
    Try to find the best (file_path, new_line) in the diff for this finding.

    Strategy (in order):
    1. Explicit <!-- file: ..., line: N --> annotation already on the finding.
    2. Search all changed lines for a verbatim snippet from the finding description.
    3. Fall back to the first changed line of the only file in the diff (when there
       is exactly one changed file and the finding description mentions its basename).
    Returns None when no confident match is found.
    """
    # 1. Explicit annotation wins
    if finding['diff_file'] and finding['diff_line']:
        return finding['diff_file'], finding['diff_line']

    desc = (finding['title'] + ' ' + finding['description']).lower()

    # 2. Search for quoted/backtick snippets from the description in the diff
    snippets = re.findall(r'[`>]\s*(.+?)\s*[`\n]', finding['description'])
    for path, lines in diff_map.items():
        for new_line, content in lines:
            stripped = content.strip()
            if not stripped:
                continue
            # Check if any snippet from the finding matches this diff line
            for snip in snippets:
                snip_clean = snip.strip().lower()
                if len(snip_clean) > 8 and snip_clean in content.lower():
                    return path, new_line
            # Also check if diff line content appears quoted in the description
            if len(stripped) > 8 and stripped.lower() in desc:
                return path, new_line

    # 3. Single-file diff and finding mentions the file's basename
    if len(diff_map) == 1:
        path = next(iter(diff_map))
        basename = path.split('/')[-1].lower().replace('.', r'\.')
        if re.search(basename, desc):
            # Pin to the first added line (+) in that file
            for new_line, content in diff_map[path]:
                return path, new_line

    return None


def format_note(f: dict, abstract_only: bool = True) -> str:
    """Format a finding as a GitLab comment.

    abstract_only=True (default):
      - heading + review action when review action is present
      - heading + description body when review action is absent (fallback)
    abstract_only=False: heading + full description + review action.
    """
    emoji = SEVERITY_EMOJI.get(f['severity'], '⚪')
    header = f"{emoji} ## {f['id']} · {f['title']}"
    if abstract_only:
        body = f['review_action'] or f['description']
        lines = [header]
        if body:
            lines += ['', body]
        return '\n'.join(lines)
    lines = [header, '', f['description']]
    if f['review_action']:
        lines += ['', f['review_action']]
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

GITLAB_USER = 'jojijose'


def detect_host_from_remote(repo_dir: str = '.') -> str:
    """
    Auto-detect the GitLab hostname from the git remote URL of repo_dir.
    Works for both SSH (git@host:...) and HTTPS (https://host/...) remotes.
    """
    try:
        url = subprocess.check_output(
            ['git', 'remote', 'get-url', 'origin'],
            cwd=repo_dir, stderr=subprocess.DEVNULL,
        ).decode().strip()
    except subprocess.CalledProcessError:
        return ''
    # SSH form: git@host:namespace/project.git
    m = re.match(r'git@([^:]+):', url)
    if m:
        return m.group(1)
    # HTTPS form: https://host/namespace/project.git
    m = re.match(r'https?://([^/]+)/', url)
    if m:
        return m.group(1)
    return ''


def parse_mr_url(url: str) -> tuple[str, str, str, int]:
    """Return (scheme, host, project_path, iid) from a GitLab MR URL."""
    m = re.match(
        r'(https?)://([^/]+)/(.+?)/-/merge_requests/(\d+)',
        url.rstrip('/'),
    )
    if not m:
        raise ValueError(f'Cannot parse MR URL: {url!r}')
    return m.group(1), m.group(2), m.group(3), int(m.group(4))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--review-file', required=True,
                        help='Path to the REVIEW_MR<IID>.md file')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--mr-url', help='Full GitLab MR URL')
    group.add_argument('--project', help='GitLab project path (namespace/name)')
    parser.add_argument('--iid', type=int, help='MR IID (required with --project)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview without posting')
    parser.add_argument('--publish', action='store_true',
                        help='Post as visible comments immediately (default: pending/draft)')
    parser.add_argument('--full', action='store_true',
                        help='Include full description and review action in each comment '
                             '(default: abstract/title only)')
    parser.add_argument('--severities', default='major,minor,info',
                        help='Comma-separated severities to post (default: all)')
    parser.add_argument('--repo-dir', default='.',
                        help='Repo directory for git remote auto-detection (default: cwd)')
    args = parser.parse_args()

    # Host: prefer env var, then MR URL, then git remote auto-detect
    host = os.environ.get('GITLAB_HOST', '')
    token = os.environ.get('GITLAB_TOKEN', '')
    scheme = 'https'  # default; overridden by MR URL scheme

    if args.mr_url:
        scheme, host_from_url, project_path, iid = parse_mr_url(args.mr_url)
        if not host:
            host = host_from_url
    else:
        project_path = args.project
        if not args.iid:
            sys.exit('ERROR: --iid required when using --project')
        iid = args.iid

    # Fall back to git remote detection
    if not host:
        host = detect_host_from_remote(args.repo_dir)
    if not host:
        sys.exit('ERROR: Cannot detect GitLab host. Pass --mr-url or set GITLAB_HOST.')

    if not args.dry_run and not token:
        sys.exit('ERROR: GITLAB_TOKEN not set. Set it in the environment or source gitlab_env.sh.')

    draft = not args.publish
    abstract_only = not args.full
    allowed_severities = {s.strip() for s in args.severities.split(',')}

    review_text = open(args.review_file).read()
    all_findings = parse_findings(review_text)
    findings = [f for f in all_findings if f['severity'] in allowed_severities]

    if not findings:
        print('No findings match the specified severities. Nothing to post.')
        return

    # Resolve project ID early (needed for diff-map even in dry-run preview)
    project_id = None
    diff_map = {}
    locations: dict[str, tuple[str, int] | None] = {}

    if not args.dry_run or True:  # always build preview locations
        if not args.dry_run and not token:
            sys.exit('ERROR: GITLAB_TOKEN not set.')
        if token:
            project_id = get_project_id(host, token, project_path, scheme=scheme)
            diff_map = get_diff_map(host, token, project_id, iid, scheme=scheme)

    # Auto-locate each finding in the diff
    for f in findings:
        locations[f['id']] = auto_locate(f, diff_map)

    def _post_as_label(fid: str) -> str:
        loc = locations[fid]
        if loc:
            return f'{loc[0]}:{loc[1]}'
        return 'general note'

    # Preview table
    print(f'\nReview file : {args.review_file}')
    print(f'MR          : {scheme}://{host}/{project_path}/-/merge_requests/{iid}')
    print(f'GitLab user : {GITLAB_USER}')
    print(f'Mode        : {"pending (draft — visible only to you)" if draft else "immediate (visible to all)"}')
    print(f'Findings    : {len(findings)} (filtered from {len(all_findings)} total)\n')
    col_w = [6, 45, 10, 28]
    header = f"{'ID':<{col_w[0]}} {'Title':<{col_w[1]}} {'Sev':<{col_w[2]}} {'Post as':<{col_w[3]}}"
    print(header)
    print('-' * sum(col_w))
    for f in findings:
        emoji = SEVERITY_EMOJI.get(f['severity'], '⚪')
        sev_label = f"{emoji} {f['severity']}"
        post_as = _post_as_label(f['id'])
        print(f"{f['id']:<{col_w[0]}} {f['title'][:col_w[1]]:<{col_w[1]}} {sev_label:<{col_w[2]}} {post_as:<{col_w[3]}}")
    print()

    if args.dry_run:
        print('[dry-run] No comments posted.')
        return

    mode_label = 'pending draft' if draft else 'visible'
    answer = input(f'Post {len(findings)} finding(s) as {mode_label} comment(s) to MR !{iid}? [y/N] ').strip().lower()
    if answer != 'y':
        print('Aborted.')
        return

    shas = get_mr_shas(host, token, project_id, iid, scheme=scheme)

    posted = 0
    for f in findings:
        note_body = format_note(f, abstract_only=abstract_only)
        loc = locations[f['id']]
        try:
            if loc:
                file_path, new_line = loc
                post_diff_note(host, token, project_id, iid,
                               note_body, shas, file_path, new_line,
                               scheme=scheme, draft=draft)
                label = 'pending diff note' if draft else 'diff note'
                print(f"  ✓ {f['id']} posted as {label} on {file_path}:{new_line}")
            else:
                post_note(host, token, project_id, iid, note_body, scheme=scheme, draft=draft)
                label = 'pending note' if draft else 'general note'
                print(f"  ✓ {f['id']} posted as {label}")
            posted += 1
        except RuntimeError as e:
            print(f"  ✗ {f['id']} FAILED: {e}", file=sys.stderr)

    if draft and posted:
        print(f'\nPosted {posted}/{len(findings)} findings as pending drafts to MR !{iid}.')
        print('To publish: open the MR in GitLab → "Pending comments" → Submit review.')
    else:
        print(f'\nPosted {posted}/{len(findings)} findings to MR !{iid}.')


if __name__ == '__main__':
    main()
