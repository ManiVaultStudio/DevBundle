import requests
import os
import json


def get_vcpkg_baseline_shas(
    chronological: bool = True,
    max_pages: int = 20,
) -> list[dict]:
    """
    Fetch vcpkg tag SHAs directly via the Git refs API.
    Faster than the releases API and returns all tags including
    those not formally published as releases.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        print("WARNING: No GITHUB_TOKEN — rate limited to 60 requests/hr.")

    tags = []
    page = 1

    while page <= max_pages:
        response = requests.get(
            "https://api.github.com/repos/microsoft/vcpkg/git/refs/tags",
            headers=headers,
            params={"per_page": 100, "page": page},
        )
        response.raise_for_status()
        data = response.json()

        if not data:
            break

        for ref in data:
            tag_name = ref["ref"].removeprefix("refs/tags/")

            # Resolve annotated tags — they point to a tag object,
            # not directly to a commit. We need the commit SHA.
            obj = ref["object"]
            if obj["type"] == "tag":
                tag_response = requests.get(obj["url"], headers=headers)
                tag_response.raise_for_status()
                sha = tag_response.json()["object"]["sha"]
            else:
                sha = obj["sha"]

            tags.append({
                "tag": tag_name,
                "sha": sha,
            })

        if "next" not in response.links:
            break
        page += 1

    # The refs API returns tags in lexicographic order by ref name.
    # vcpkg uses date-prefixed tags (e.g. 2024.01.12) so lexicographic
    # order IS chronological order for vcpkg specifically.
    # Reverse if you want newest first.
    if not chronological:
        tags.reverse()

    return tags


def main():
    print("Fetching vcpkg tag SHAs...")
    tags = get_vcpkg_baseline_shas(chronological=True)

    # print(f"\nFound {len(tags)} tags:\n")
    # print(f"{'Tag':<24} SHA")
    # print("-" * 70)
    print(f"{json.dumps(tags, indent=2)}")
    #for t in tags:
    #    print(f"{t['tag']:<24} {t['sha']}")

    latest = tags[-1] if tags else None
    if latest:
        print(f"\nLatest baseline for vcpkg-configuration.json:")
        print(f'  "builtin-baseline": "{latest["sha"]}"')


if __name__ == "__main__":
    main()