from agentdrive.models.types import ArticleStatus, ArticleType, KBStatus, LinkType


class TestKBStatus:
    def test_values(self) -> None:
        assert KBStatus.ACTIVE == "active"
        assert KBStatus.COMPILING == "compiling"
        assert KBStatus.ERROR == "error"

    def test_members(self) -> None:
        assert set(KBStatus) == {KBStatus.ACTIVE, KBStatus.COMPILING, KBStatus.ERROR}


class TestArticleType:
    def test_values(self) -> None:
        assert ArticleType.CONCEPT == "concept"
        assert ArticleType.SUMMARY == "summary"
        assert ArticleType.CONNECTION == "connection"
        assert ArticleType.QUESTION == "question"
        assert ArticleType.DERIVED == "derived"
        assert ArticleType.MANUAL == "manual"

    def test_members(self) -> None:
        assert len(ArticleType) == 6


class TestArticleStatus:
    def test_values(self) -> None:
        assert ArticleStatus.DRAFT == "draft"
        assert ArticleStatus.PUBLISHED == "published"
        assert ArticleStatus.STALE == "stale"

    def test_members(self) -> None:
        assert set(ArticleStatus) == {
            ArticleStatus.DRAFT,
            ArticleStatus.PUBLISHED,
            ArticleStatus.STALE,
        }


class TestLinkType:
    def test_values(self) -> None:
        assert LinkType.RELATED == "related"
        assert LinkType.CONTRADICTS == "contradicts"
        assert LinkType.EXTENDS == "extends"
        assert LinkType.PREREQUISITE == "prerequisite"

    def test_members(self) -> None:
        assert len(LinkType) == 4
