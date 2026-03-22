from agentdrive.search.bm25 import bm25_score

def test_bm25_score_positive():
    score = bm25_score(tf=3, df=10, dl=100, avgdl=120, n_docs=1000)
    assert score > 0

def test_bm25_score_zero_tf():
    score = bm25_score(tf=0, df=10, dl=100, avgdl=120, n_docs=1000)
    assert score == 0.0

def test_bm25_score_rare_term_higher():
    common = bm25_score(tf=1, df=500, dl=100, avgdl=100, n_docs=1000)
    rare = bm25_score(tf=1, df=5, dl=100, avgdl=100, n_docs=1000)
    assert rare > common
