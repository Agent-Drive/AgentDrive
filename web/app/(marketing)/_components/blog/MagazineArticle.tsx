import { ArticleHero } from "./ArticleHero";
import { ArticleToc } from "./ArticleToc";
import { BlogFooter } from "./BlogFooter";
import { BlogNav } from "./BlogNav";
import { FeaturedArticle } from "./FeaturedArticle";

export function MagazineArticle() {
  return (
    <>
      <BlogNav />
      <main>
        <ArticleHero />
        <div className="article-layout">
          <ArticleToc />
          <FeaturedArticle />
          <aside className="right-sidebar" />
        </div>
        <BlogFooter />
      </main>
    </>
  );
}
