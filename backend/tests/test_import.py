import pytest

from app.routers.projects import parse_github_url


@pytest.mark.parametrize(
    "url,owner,repo,branch",
    [
        ("https://github.com/octocat/Hello-World", "octocat", "Hello-World", None),
        ("https://github.com/octocat/Hello-World/", "octocat", "Hello-World", None),
        ("https://github.com/octocat/Hello-World.git", "octocat", "Hello-World", None),
        ("https://github.com/octocat/Hello-World.git/", "octocat", "Hello-World", None),
        ("https://github.com/octocat/Hello-World/tree/main", "octocat", "Hello-World", "main"),
        (
            "https://github.com/octocat/Hello-World/tree/main/",
            "octocat",
            "Hello-World",
            "main",
        ),
        (
            "https://github.com/octocat/Hello-World/tree/feature/foo",
            "octocat",
            "Hello-World",
            "feature/foo",
        ),
        ("  https://github.com/octocat/Hello-World  ", "octocat", "Hello-World", None),
    ],
)
def test_parse_valid_github_urls(url, owner, repo, branch):
    assert parse_github_url(url) == (owner, repo, branch)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not a url",
        "github.com/octocat/Hello-World",
        "https://gitlab.com/octocat/Hello-World",
        "https://github.com/octocat",
        "https://github.com/",
        "ftp://github.com/octocat/Hello-World",
        "https://github.com/octocat/Hello-World/pulls/1",
        "https://github.com/octocat/Hello-World/tree",
    ],
)
def test_parse_invalid_github_urls_reject(url):
    with pytest.raises(ValueError):
        parse_github_url(url)
