import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSlot,
} from "@/components/ui/input-otp";
import { authApi } from "@/lib/auth/client";
import {
  AUTH_PASSWORD_MIN_LENGTH,
  validateLoginInput,
  validateOtp,
  validateSignupCredentials,
} from "@/lib/auth/validation";
import { useAuthStore } from "@/stores/auth-store";

type SignupStep = "email" | "otp" | "credentials";

export const Route = createFileRoute("/signup")({
  head: () => ({ meta: [{ title: "Sign up — JyotishAI" }] }),
  component: SignupPage,
});

function SignupPage() {
  const navigate = useNavigate();
  const setSession = useAuthStore((s) => s.setSession);

  const [step, setStep] = useState<SignupStep>("email");
  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [verificationToken, setVerificationToken] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const sendOtp = async () => {
    const normalizedEmail = email.trim().toLowerCase();
    if (!normalizedEmail) {
      toast.error("Enter your email address");
      return;
    }
    setEmail(normalizedEmail);
    setLoading(true);
    try {
      const res = await authApi.sendOtp(normalizedEmail);
      if (res.dev_otp) toast.message(`Dev OTP: ${res.dev_otp}`);
      toast.success(res.message);
      setStep("otp");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not send OTP");
    } finally {
      setLoading(false);
    }
  };

  const verifyOtp = async () => {
    const otpCheck = validateOtp(otp);
    if (!otpCheck.ok) {
      toast.error(otpCheck.message);
      return;
    }
    setLoading(true);
    try {
      const res = await authApi.verifyOtp(email.trim().toLowerCase(), otp);
      setVerificationToken(res.verification_token);
      toast.success("Email verified");
      setStep("credentials");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Invalid OTP");
    } finally {
      setLoading(false);
    }
  };

  const completeSignup = async () => {
    const check = validateSignupCredentials(username, password, confirmPassword);
    if (!check.ok) {
      toast.error(check.message);
      return;
    }
    setLoading(true);
    try {
      const res = await authApi.signup({
        email: email.trim(),
        verification_token: verificationToken,
        username: username.trim(),
        password,
        confirm_password: confirmPassword,
      });
      setSession(res.access_token, res.user);
      toast.success("Account created");
      navigate({ to: "/" });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Signup failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Verify your email, then choose a username and password."
    >
      <Card>
        <CardHeader>
          <CardTitle>
            {step === "email" && "Step 1 — Email"}
            {step === "otp" && "Step 2 — Verify OTP"}
            {step === "credentials" && "Step 3 — Account details"}
          </CardTitle>
          <CardDescription>
            {step === "email" && "We will send a one-time code to your inbox."}
            {step === "otp" && `Enter the code sent to ${email} (dev: 0000)`}
            {step === "credentials" && "Pick a unique username and password (more than 6 characters each)."}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {step === "email" && (
            <>
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <Button
                className="w-full gradient-gold text-primary-foreground"
                onClick={sendOtp}
                disabled={loading}
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Send verification code"}
              </Button>
            </>
          )}

          {step === "otp" && (
            <>
              <div className="space-y-2">
                <Label>Verification code</Label>
                <InputOTP maxLength={4} value={otp} onChange={setOtp}>
                  <InputOTPGroup>
                    <InputOTPSlot index={0} />
                    <InputOTPSlot index={1} />
                    <InputOTPSlot index={2} />
                    <InputOTPSlot index={3} />
                  </InputOTPGroup>
                </InputOTP>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" className="flex-1" onClick={() => setStep("email")} disabled={loading}>
                  Back
                </Button>
                <Button
                  className="flex-1 gradient-gold text-primary-foreground"
                  onClick={verifyOtp}
                  disabled={loading}
                >
                  {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Verify code"}
                </Button>
              </div>
              <Button variant="link" className="px-0" onClick={sendOtp} disabled={loading}>
                Resend code
              </Button>
            </>
          )}

          {step === "credentials" && (
            <>
              <div className="space-y-2">
                <Label htmlFor="username">Username</Label>
                <Input
                  id="username"
                  autoComplete="username"
                  placeholder="Shiva ramakrishanan"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  More than 6 characters. Spaces are allowed.
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  autoComplete="new-password"
                  minLength={AUTH_PASSWORD_MIN_LENGTH}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  More than 6 characters.
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="confirmPassword">Confirm password</Label>
                <Input
                  id="confirmPassword"
                  type="password"
                  autoComplete="new-password"
                  minLength={AUTH_PASSWORD_MIN_LENGTH}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                />
              </div>
              <Button
                className="w-full gradient-gold text-primary-foreground"
                onClick={completeSignup}
                disabled={loading}
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Create account"}
              </Button>
            </>
          )}

          <p className="text-sm text-center text-muted-foreground">
            Already have an account?{" "}
            <Link to="/login" className="text-gold hover:underline font-medium">
              Log in
            </Link>
          </p>
        </CardContent>
      </Card>
    </AuthLayout>
  );
}
