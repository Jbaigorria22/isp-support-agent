"""Hybrid retrieval: tree filter first, similarity ranking second."""

from fiberlab.agent.retrieval import Retriever, load_guides


def test_every_guide_has_steps_and_a_place_in_the_tree():
    guides = load_guides()
    assert len(guides) >= 9
    for g in guides:
        assert len(g.steps) >= 2 and g.path.endswith(f"/{g.problem}/green")


def test_filter_keeps_only_the_problem_branch():
    found = Retriever().search("slow_internet", "green", "no veo la red wifi", k=5)
    assert found and all(g.problem == "slow_internet" for g in found)  # similar words, wrong branch: excluded


def test_ranking_picks_the_guide_that_matches_the_customer_words():
    r = Retriever()
    assert r.search("wifi", "green", "mi celular no ve la red en la lista")[0].id == "wf-01"
    assert r.search("wifi", "green", "dice contraseña incorrecta y no conecta")[0].id == "wf-02"
    assert r.search("wifi", "green", "no llega a la habitación del fondo, se corta")[0].id == "wf-03"


def test_exclude_gives_a_different_guide_for_the_second_attempt():
    r = Retriever()
    first = r.search("intermittent", "green", "se corta a cada rato")[0]
    second = r.search("intermittent", "green", "se corta a cada rato", exclude=[first.id])[0]
    assert first.id != second.id


def test_green_only_guides_are_not_offered_on_a_red_line():
    assert Retriever().search("slow_internet", "red", "anda lento") == []
