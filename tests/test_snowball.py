import unittest
from unittest import mock

from cosmolab import snowball


def cand(title, doi="", arxiv="", citations=0, pdf=""):
    return snowball._candidate(title, 2020, doi, arxiv, [], citations, pdf, "", "semanticscholar")


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class S2KeyTests(unittest.TestCase):
    def test_journal_doi_wins(self):
        self.assertEqual(snowball.s2_key({"doi": "https://doi.org/10.1/ABC"}), "DOI:10.1/ABC")

    def test_arxiv_doi_uses_arxiv_id(self):
        self.assertEqual(snowball.s2_key({"doi": "10.48550/arXiv.2101.00001"}), "ARXIV:2101.00001")

    def test_arxiv_id_field(self):
        self.assertEqual(snowball.s2_key({"arxiv_id": "hep-th/9901001"}), "ARXIV:hep-th/9901001")

    def test_nothing(self):
        self.assertEqual(snowball.s2_key({"title": "x"}), "")


class MergeTests(unittest.TestCase):
    def test_drops_collected_and_ranks_by_links_then_citations(self):
        corpus = [
            {"title": "Seed One", "doi": "10.1/seed1"},
            {"title": "Seed Two", "doi": "10.1/seed2"},
            {"title": "Already Here", "doi": "10.1/here"},
        ]
        shared = cand("Shared Paper", doi="10.1/shared", citations=5)
        popular = cand("Popular Paper", doi="10.1/pop", citations=900)
        collected_doi = cand("Other title", doi="10.1/HERE")
        collected_title = cand("already here!")
        merged = snowball.merge([
            (corpus[0], snowball.BACKWARD, [shared, popular, collected_doi]),
            (corpus[1], snowball.FORWARD, [cand("Shared Paper", doi="10.1/SHARED", citations=7,
                                                pdf="http://x/a.pdf"), collected_title]),
        ], corpus)
        self.assertEqual([m["title"] for m in merged], ["Shared Paper", "Popular Paper"])
        top = merged[0]
        self.assertEqual(top["link_count"], 2)
        self.assertEqual(top["citations"], 7)
        self.assertEqual(top["pdf_url"], "http://x/a.pdf")
        self.assertEqual(top["directions"], [snowball.BACKWARD, snowball.FORWARD])

    def test_arxiv_candidate_gets_pdf_and_dedupes_against_arxiv_doi(self):
        corpus = [{"title": "Seed", "doi": "10.48550/arXiv.2101.00001"}]
        merged = snowball.merge([(corpus[0], snowball.BACKWARD, [
            cand("Same seed other title", arxiv="2101.00001"),
            cand("New arXiv paper", arxiv="2202.00002"),
        ])], corpus)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["pdf_url"], "https://arxiv.org/pdf/2202.00002")


class LinksForTests(unittest.TestCase):
    def test_semantic_scholar_used_when_it_answers(self):
        data = {"data": [{"citedPaper": {"title": "Ref A", "year": 2001, "externalIds": {"DOI": "10.1/a"},
                                         "citationCount": 3, "authors": [{"name": "Jane Doe"}]}}]}
        with mock.patch.object(snowball, "_http_get", return_value=FakeResponse(data)) as get:
            found, src = snowball.links_for({"doi": "10.1/seed"}, snowball.BACKWARD)
        self.assertEqual(src, "semanticscholar")
        self.assertEqual(found[0]["doi"], "10.1/a")
        self.assertIn("/DOI:10.1/seed/references", get.call_args[0][0])

    def test_falls_back_to_openalex(self):
        def fake_get(url, **kwargs):
            if "semanticscholar" in url:
                return None
            if "/doi:" in url:
                return FakeResponse({"id": "https://openalex.org/W1", "referenced_works": []})
            self.assertEqual(kwargs["params"]["filter"], "cites:W1")
            return FakeResponse({"results": [{"title": "Citing B", "publication_year": 2024,
                                              "doi": "https://doi.org/10.1/b", "cited_by_count": 2}]})

        with mock.patch.object(snowball, "_http_get", side_effect=fake_get):
            found, src = snowball.links_for({"doi": "10.1/seed"}, snowball.FORWARD)
        self.assertEqual(src, "openalex")
        self.assertEqual(found[0]["doi"], "10.1/b")

    def test_snowball_counts_sources_without_sleeping(self):
        with mock.patch.object(snowball, "links_for", return_value=([cand("X", doi="10.1/x")], "openalex")):
            res = snowball.snowball([{"title": "S", "doi": "10.1/s"}], [], pause=0)
        self.assertEqual(res["sources"], {"openalex": 2})
        self.assertEqual(res["candidates"][0]["directions"], [snowball.BACKWARD, snowball.FORWARD])


if __name__ == "__main__":
    unittest.main()
