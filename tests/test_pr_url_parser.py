import unittest

from shipguard.pr_url_parser import InvalidPRURLError, parse_github_pr_url


class GitHubPRURLParserTests(unittest.TestCase):
    def test_parses_valid_github_pull_request_urls(self) -> None:
        cases = [
            (
                "https://github.com/OWNER/REPO/pull/123",
                "OWNER",
                "REPO",
                123,
            ),
            (
                "https://github.com/acme-corp/service-api/pull/42",
                "acme-corp",
                "service-api",
                42,
            ),
            (
                "https://github.com/acme_org/service_api/pull/7",
                "acme_org",
                "service_api",
                7,
            ),
            (
                "https://github.com/acme.tools/service.core/pull/19",
                "acme.tools",
                "service.core",
                19,
            ),
        ]

        for pr_url, owner, repo, number in cases:
            with self.subTest(pr_url=pr_url):
                parsed = parse_github_pr_url(pr_url)

                self.assertEqual(parsed.owner, owner)
                self.assertEqual(parsed.repo, repo)
                self.assertEqual(parsed.number, number)
                self.assertEqual(parsed.url, pr_url)

    def test_strips_surrounding_whitespace(self) -> None:
        parsed = parse_github_pr_url(
            "  \nhttps://github.com/OWNER/REPO/pull/123\t "
        )

        self.assertEqual(parsed.owner, "OWNER")
        self.assertEqual(parsed.repo, "REPO")
        self.assertEqual(parsed.number, 123)
        self.assertEqual(parsed.url, "https://github.com/OWNER/REPO/pull/123")

    def test_rejects_invalid_github_pull_request_urls(self) -> None:
        cases = [
            ("http://github.com/OWNER/REPO/pull/123", "https://github.com"),
            ("https://gitlab.com/OWNER/REPO/pull/123", "github.com"),
            ("https://github.com/OWNER/REPO/issues/123", "OWNER/REPO/pull/NUMBER"),
            ("https://github.com/OWNER/REPO/pull/not-a-number", "integer"),
            ("https://github.com/OWNER/REPO/pull/0", "greater than zero"),
            ("https://github.com/OWNER/REPO/pull/-1", "greater than zero"),
            ("https://github.com/OWNER/REPO", "OWNER/REPO/pull/NUMBER"),
            ("https://github.com/OWNER/REPO/pull/123/files", "OWNER/REPO/pull/NUMBER"),
            ("", "https://github.com"),
            ("random text", "https://github.com"),
        ]

        for pr_url, message_fragment in cases:
            with self.subTest(pr_url=pr_url):
                with self.assertRaises(InvalidPRURLError) as caught:
                    parse_github_pr_url(pr_url)

                self.assertIn(message_fragment, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
