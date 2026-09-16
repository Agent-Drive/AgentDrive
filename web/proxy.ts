import { NextRequest } from "next/server";
import { authkit, handleAuthkitHeaders } from "@workos-inc/authkit-nextjs";

export default async function proxy(request: NextRequest) {
  const { session, headers } = await authkit(request);
  const { pathname } = request.nextUrl;

  if (pathname.startsWith("/app") && !session.user) {
    return handleAuthkitHeaders(request, headers, { redirect: "/sign-in" });
  }

  return handleAuthkitHeaders(request, headers);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|icon.svg|icon.png).*)"],
};
