import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Loader2, Eye, EyeOff } from "lucide-react";
import { toast } from "sonner";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authApi } from "@/lib/auth/client";
import { validateLoginInput } from "@/lib/auth/validation";
import { useAuthStore, useIsAuthenticated } from "@/stores/auth-store";

type LoginSearch = {
  redirect?: string;
};

export const Route = createFileRoute("/login")({
  head: () => ({ meta: [{ title: "Log in — JyotishAI" }] }),
  validateSearch: (search: Record<string, unknown>): LoginSearch => ({
    redirect: typeof search.redirect === "string" ? search.redirect : undefined,
  }),
  component: LoginPage,
});

function LoginPage() {
  const navigate = useNavigate();
  const { redirect } = Route.useSearch();
  const setSession = useAuthStore((s) => s.setSession);
  const hydrated = useAuthStore((s) => s.hydrated);
  const isAuthenticated = useIsAuthenticated();

  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (hydrated && isAuthenticated) {
      navigate({ to: redirect || "/" });
    }
  }, [hydrated, isAuthenticated, redirect, navigate]);

  const submit = async () => {
    const check = validateLoginInput(identifier, password);
    if (!check.ok) {
      toast.error(check.message);
      return;
    }
    setLoading(true);
    try {
      const res = await authApi.login(identifier.trim(), password);
      setSession(res.access_token, res.user);
      toast.success(`Welcome back, ${res.user.username}`);
      navigate({ to: redirect || "/" });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout title="Welcome back" subtitle="Sign in to your JyotishAI account.">
      <Card className="relative z-10 border-border/40 bg-card/60 backdrop-blur-2xl shadow-xl overflow-hidden pb-2">
        <div className="absolute inset-0 bg-gradient-to-br from-gold/10 via-transparent to-transparent opacity-50 z-0 pointer-events-none" />
        <CardHeader className="relative z-10 text-center pb-2">
          <CardTitle className="text-xl font-semibold">Log in</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5 relative z-10">
          <div className="space-y-2">
            <Label htmlFor="identifier">Email or username</Label>
            <Input
              id="identifier"
              autoComplete="username"
              placeholder="you@example.com or Shiva ramakrishanan"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              className="bg-background/50 border-border/60 focus-visible:ring-gold/50 focus-visible:border-gold h-11 transition-all"
            />
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="password" className="text-foreground/80 font-medium">Password</Label>
              <Link to="/forgot-password" className="text-[13px] text-gold hover:text-gold/80 hover:underline transition-colors font-medium">
                Forgot password?
              </Link>
            </div>
            <div className="relative">
              <Input
                id="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submit()}
                className="pr-10 bg-background/50 border-border/60 focus-visible:ring-gold/50 focus-visible:border-gold h-11 transition-all"
              />
              <button
                type="button"
                className="absolute inset-y-0 right-0 flex items-center pr-3 text-muted-foreground hover:text-foreground focus:outline-none"
                onClick={() => setShowPassword(!showPassword)}
                tabIndex={-1}
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>
          <Button
            className="w-full h-11 mt-2 gradient-gold text-primary-foreground shadow-md hover:shadow-lg hover:-translate-y-0.5 transition-all text-[0.95rem] font-semibold"
            onClick={submit}
            disabled={loading}
          >
            {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : "Sign in"}
          </Button>
          <p className="text-[0.9rem] text-center text-muted-foreground pt-2">
            New here?{" "}
            <Link to="/signup" className="text-gold hover:underline font-medium">
              Create an account
            </Link>
          </p>
        </CardContent>
      </Card>
    </AuthLayout>
  );
}
