import { useRouterState } from "@tanstack/react-router";
import { Loader2 } from "lucide-react";
import { type ReactNode, useEffect, useRef } from "react";
import { LoginRequired } from "@/components/auth/LoginRequired";
import { isProtectedRoute } from "@/lib/auth/routes";
import { useAuthStore, useIsAuthenticated } from "@/stores/auth-store";

export function AuthGate({ children }: { children: ReactNode }) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const hydrated = useAuthStore((s) => s.hydrated);
  const isAuthenticated = useIsAuthenticated();
  const clearAllAppData = useAuthStore((s) => s.clearAllAppData);
  const clearedRef = useRef(false);

  const needsAuth = isProtectedRoute(pathname);

  useEffect(() => {
    if (!hydrated || isAuthenticated || !needsAuth) {
      clearedRef.current = false;
      return;
    }
    if (clearedRef.current) return;
    clearedRef.current = true;
    clearAllAppData();
  }, [hydrated, isAuthenticated, needsAuth, clearAllAppData]);

  if (!hydrated) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-muted-foreground">
        <Loader2 className="w-6 h-6 animate-spin" aria-label="Loading session" />
      </div>
    );
  }

  if (needsAuth && !isAuthenticated) {
    return <LoginRequired />;
  }

  return <>{children}</>;
}
