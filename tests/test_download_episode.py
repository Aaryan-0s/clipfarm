import pytest

from clipfarm_mcp.download_episode import filename_stem


def test_episode_filename():
    assert filename_stem(8, 14, "Peter-assment") == "Family.Guy.S08E14.Peter.assment"
    assert filename_stem(21, 4, "The Munchurian Candidate") == (
        "Family.Guy.S21E04.The.Munchurian.Candidate"
    )


@pytest.mark.parametrize("season,episode", [(0, 1), (1, 0), (100, 1), (1, 1000)])
def test_invalid_episode_numbers(season, episode):
    with pytest.raises(ValueError):
        filename_stem(season, episode, "Example")
