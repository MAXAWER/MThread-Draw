#!/usr/bin/env bash
#
# One narrow door to this repository's GitHub API.
#
#     tools/github.sh GET  /pulls
#     tools/github.sh PUT  /pulls/7/merge '{"merge_method":"squash"}'
#     tools/github.sh POST /releases '{"tag_name":"v1.1.0"}'
#
# It exists so that an assistant can be given one permission rule instead of
# "may run curl", which is the same thing as "may talk to anything". Everything
# here is fixed except the method, the path under this one repository, and the
# body: no other host, no other repository, no other credential.
#
# The token comes from the git credential helper - the same one `git push`
# already uses - and is never printed.
#
# To allow it, add to .claude/settings.json:
#
#     { "permissions": { "allow": ["Bash(bash tools/github.sh:*)"] } }

set -euo pipefail

REPOSITORY="MAXAWER/MThread-Draw"
API="https://api.github.com/repos/${REPOSITORY}"

if [ $# -lt 2 ]; then
    echo "usage: $0 <GET|POST|PATCH|PUT|DELETE> <path> [json body]" >&2
    exit 2
fi

METHOD="$1"
PATH_UNDER_REPO="$2"
BODY="${3:-}"

case "$METHOD" in
    GET|POST|PATCH|PUT|DELETE) ;;
    *) echo "refusing method $METHOD" >&2; exit 2 ;;
esac

# A path only, so no amount of creativity redirects this at another repository
# or another host.
case "$PATH_UNDER_REPO" in
    /*) ;;
    *) echo "path must start with /" >&2; exit 2 ;;
esac
case "$PATH_UNDER_REPO" in
    *//*|*..*|*:*) echo "refusing path $PATH_UNDER_REPO" >&2; exit 2 ;;
esac

TOKEN="$(printf 'protocol=https\nhost=github.com\n\n' | git credential fill 2>/dev/null \
         | sed -n 's/^password=//p')"
if [ -z "$TOKEN" ]; then
    echo "no GitHub credential stored; run a git push once to save one" >&2
    exit 1
fi

if [ -n "$BODY" ]; then
    curl -sS -X "$METHOD" \
        -H "Authorization: Bearer ${TOKEN}" \
        -H "Accept: application/vnd.github+json" \
        -d "$BODY" \
        "${API}${PATH_UNDER_REPO}"
else
    curl -sS -X "$METHOD" \
        -H "Authorization: Bearer ${TOKEN}" \
        -H "Accept: application/vnd.github+json" \
        "${API}${PATH_UNDER_REPO}"
fi
echo
