import unittest
from cosmolab import faculties, db, sparring, curriculum, harvest
from _markers import needs_corpus


class TestCosmoLabUniversity(unittest.TestCase):

    def test_faculties_definitions(self):
        """Test that foundational and multidisciplinary faculties are defined with required attributes."""
        all_facs = faculties.list_faculties()
        self.assertGreaterEqual(len(all_facs), 6)
        
        expected_ids = {"ilahiyyat", "epistemologi", "kausalitas", "teodisi", "falsafah_jiwa", "nubuwwat"}
        actual_ids = {f.id for f in all_facs}
        self.assertTrue(expected_ids.issubset(actual_ids))

        for f in all_facs:
            self.assertTrue(len(f.default_queries) >= 3)
            if not f.is_custom:
                self.assertTrue(len(f.classic_references) >= 2)
                self.assertTrue(len(f.modern_references) >= 2)

    def test_custom_faculty_lifecycle(self):
        """Test dynamic creation, retrieval, and deletion of custom research faculties."""
        test_id = "test_manajemen_rs"
        fac = faculties.save_custom_faculty(
            name="Manajemen Rumah Sakit",
            faculty_id=test_id,
            icon="🏥",
            short_desc="Riset mutu pelayanan faskes dan akreditasi",
            default_queries=["hospital administration quality", "bpjs patient satisfaction"],
        )
        self.assertEqual(fac.id, test_id)
        
        # Verify retrieved
        retrieved = faculties.get_faculty(test_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "Manajemen Rumah Sakit")
        self.assertTrue(retrieved.is_custom)

        # Cleanup
        deleted = faculties.delete_custom_faculty(test_id)
        self.assertTrue(deleted)
        self.assertNotIn(test_id, [f.id for f in faculties.list_faculties()])

    def test_faculty_heuristic_detection(self):
        """Test auto-classification of academic titles into appropriate faculties."""
        # Kausalitas
        fac_causal = faculties.detect_faculty_from_text(
            "Al-Ghazali and Hume on Causality and Occasionalism"
        )
        self.assertEqual(fac_causal, "kausalitas")

        # Teodisi
        fac_evil = faculties.detect_faculty_from_text(
            "The Evidential Problem of Evil and Gratuitous Suffering"
        )
        self.assertEqual(fac_evil, "teodisi")

        # Falsafah Jiwa
        fac_mind = faculties.detect_faculty_from_text(
            "Avicenna's Flying Man Argument and the Hard Problem of Consciousness"
        )
        self.assertEqual(fac_mind, "falsafah_jiwa")

        # Nubuwwat
        fac_prophecy = faculties.detect_faculty_from_text(
            "Hume on Miracles and the Epistemology of Religious Prophecy"
        )
        self.assertEqual(fac_prophecy, "nubuwwat")

        # Multidisiplin: Hukum
        fac_hukum = faculties.detect_faculty_from_text(
            "Analisis Yuridis Perbandingan Hukum Pidana dan Maqasid Syariah"
        )
        self.assertEqual(fac_hukum, "hukum")

        # Multidisiplin: Ekonomi
        fac_ekonomi = faculties.detect_faculty_from_text(
            "Financial Performance and Risk Management in Islamic Banking"
        )
        self.assertEqual(fac_ekonomi, "ekonomi")

        # Multidisiplin: Pendidikan
        fac_pendidikan = faculties.detect_faculty_from_text(
            "Pengembangan Kurikulum dan Pedagogis Model Pembelajaran Berbasis AI"
        )
        self.assertEqual(fac_pendidikan, "pendidikan")

    @needs_corpus
    def test_database_faculty_filtering(self):
        """Test retrieving papers filtered by faculty from SQLite."""
        papers = db.get_papers_by_faculty("ilahiyyat")
        self.assertIsInstance(papers, list)
        for p in papers:
            self.assertEqual(p.get("faculty"), "ilahiyyat")

        dist = db.get_faculty_distribution()
        self.assertIsInstance(dist, dict)
        self.assertTrue(len(dist) > 0)

    def test_sparring_personas_and_dilemmas(self):
        """Test that philosophical personas and multi-faculty dilemmas are registered."""
        personas = sparring.list_personas()
        self.assertGreaterEqual(len(personas), 6)

        persona_ids = {p["id"] for p in personas}
        self.assertIn("david_hume", persona_ids)
        self.assertIn("al_ghazali", persona_ids)
        self.assertIn("ibn_sina", persona_ids)
        self.assertIn("jl_mackie", persona_ids)
        self.assertIn("daniel_dennett", persona_ids)
        self.assertIn("ruthless_critic", persona_ids)

        # Dilemmas
        dilemmas = sparring.SOCRATIC_DILEMMAS
        self.assertGreaterEqual(len(dilemmas), 10)
        
        # Test faculty dilemma filtering
        ilahiyyat_dilemmas = sparring.get_dilemmas_by_faculty("ilahiyyat")
        self.assertTrue(len(ilahiyyat_dilemmas) >= 2)

    def test_curriculum_roadmaps(self):
        """Test that progressive roadmaps are generated for each faculty."""
        for fac_id in ("ilahiyyat", "epistemologi", "kausalitas", "teodisi", "falsafah_jiwa", "nubuwwat"):
            roadmap = curriculum.get_learning_roadmap(fac_id)
            self.assertEqual(len(roadmap), 4)
            for lvl in roadmap:
                self.assertIn("level", lvl)
                self.assertIn("title", lvl)
                self.assertIn("papers", lvl)


if __name__ == "__main__":
    unittest.main()
