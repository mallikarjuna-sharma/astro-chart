/** Routes that render without the main app shell (login, signup, etc.). */
export const AUTH_ROUTES = ["/login", "/signup", "/forgot-password"] as const;

/**
 * Routes that require an authenticated session.
 * Guests see a "log in to continue" screen instead of page content.
 */
export const PROTECTED_ROUTES = [
  "/",
  "/charts",
  "/kp",
  "/kn-rao",
  "/parashari",
  "/education-analysis",
  "/career-timeline",
] as const;

export function isAuthRoute(pathname: string): boolean {
  return AUTH_ROUTES.some((route) => pathname === route);
}

export function isProtectedRoute(pathname: string): boolean {
  return PROTECTED_ROUTES.some(
    (route) => pathname === route || (route !== "/" && pathname.startsWith(`${route}/`)),
  );
}
