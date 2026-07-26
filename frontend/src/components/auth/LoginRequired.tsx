import { Link, useRouterState } from "@tanstack/react-router";
import { LogIn, UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/AppShell";

interface LoginRequiredProps {
  title?: string;
  description?: string;
}

export function LoginRequired({
  title = "Log in to continue",
  description = "Sign in to access your birth profiles, charts, and analysis. Your session data is cleared when you are signed out.",
}: LoginRequiredProps) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const loginSearch = pathname && pathname !== "/login" ? { redirect: pathname } : undefined;

  return (
    <div>
      <PageHeader title={title} subtitle={description} />
      <Card className="max-w-lg">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <LogIn className="w-5 h-5 text-gold" />
            Authentication required
          </CardTitle>
          <CardDescription>
            Create an account or sign in to save profiles and run KP, Jaimini, Parashari, education, and career analysis.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Link to="/login" search={loginSearch}>
            <Button className="gradient-gold text-primary-foreground">
              <LogIn className="w-4 h-4 mr-2" />
              Log in
            </Button>
          </Link>
          <Link to="/signup">
            <Button variant="outline">
              <UserPlus className="w-4 h-4 mr-2" />
              Sign up
            </Button>
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
