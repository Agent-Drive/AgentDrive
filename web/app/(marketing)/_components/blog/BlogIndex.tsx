import { getFeaturedPost, getListingPosts } from "../../_data/posts";
import { BlogFooter } from "./BlogFooter";
import { BlogIndexHeader } from "./BlogIndexHeader";
import { BlogNav } from "./BlogNav";
import { FeaturedPost } from "./FeaturedPost";
import { PostList } from "./PostList";

export function BlogIndex() {
  return (
    <>
      <BlogNav />
      <main className="mx-auto max-w-[1200px] px-8 pt-32 pb-20">
        <BlogIndexHeader />
        <FeaturedPost post={getFeaturedPost()} />
        <PostList posts={getListingPosts()} />
      </main>
      <BlogFooter />
    </>
  );
}
