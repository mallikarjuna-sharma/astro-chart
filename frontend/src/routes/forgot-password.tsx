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
  validateNewPassword,
  validateOtp,
} from "@/lib/auth/validation";

type ForgotPasswordStep = "email" | "otp" | "reset" | "done";

export const Route = createFileRoute("/forgot-password")({
  head: () => ({ meta: [{ title: "Forgot password — JyotishAI" }] }),
  component: ForgotPasswordPage,
});

function ForgotPasswordPage() {
  const navigate = useNavigate();

  const [step, setStep] = useState<ForgotPasswordStep>("email");
  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [resetToken, setResetToken] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmNewPassword, setConfirmNewPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const sendCode = async () => {
    const normalizedEmail = email.trim().toLowerCase();
    if (!normalizedEmail) {
      toast.error("Enter your email address");
      return;
    }
    setEmail(normalizedEmail);
    setLoading(true);
    try {
      const res = await authApi.forgotPassword(normalizedEmail);
      if (res.dev_otp) toast.message(`Dev OTP: ${res.dev_otp}`);
      toast.success(res.message);
      setStep("otp");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not send reset code");
    } finally {
      setLoading(false);
    }
  };

  const verifyCode = async () => {
    const otpCheck = validateOtp(otp);
    if (!otpCheck.ok) {
      toast.error(otpCheck.message);
      return;
    }
    setLoading(true);
    try {
      const res = await authApi.verifyResetOtp(email, otp);
      setResetToken(res.reset_token);
      toast.success("Code verified");
      setStep("reset");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Invalid code");
    } finally {
      setLoading(false);
    }
  };

  const submitNewPassword = async () => {
    const check = validateNewPassword(newPassword, confirmNewPassword);
    if (!check.ok) {
      toast.error(check.message);
      return;
    }
    setLoading(true);
    try {
      await authApi.resetPassword({
        email,
        reset_token: resetToken,
        new_password: newPassword,
        confirm_new_password: confirmNewPassword,
      });
      toast.success("Password updated. You can log in now.");
      setStep("done");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not reset password");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      title="Reset your password"
      subtitle="We will send a one-time code to your email to verify it's you."
    >
      <Card>
        <CardHeader>
          <CardTitle>
            {step === "email" && "Step 1 — Email"}
            {step === "otp" && "Step 2 — Verify code"}
            {step === "reset" && "Step 3 — New password"}
            {step === "done" && "Password updated"}
          </CardTitle>
          <CardDescription>
            {step === "email" && "Enter the email address on your account."}
            {step === "otp" && `Enter the code sent to ${email} (dev: 0000)`}
            {step === "reset" && "Choose a new password (more than 6 characters)."}
            {step === "done" && "Your password has been changed successfully."}
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
                  onKeyDown={(e) => e.key === "Enter" && sendCode()}
                />
              </div>
              <Button
                className="w-full gradient-gold text-primary-foreground"
                onClick={sendCode}
                disabled={loading}
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Send reset code"}
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
                  onClick={verifyCode}
                  disabled={loading}
                >
                  {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Verify code"}
                </Button>
              </div>
              <Button variant="link" className="px-0" onClick={sendCode} disabled={loading}>
                Resend code
              </Button>
            </>
          )}

          {step === "reset" && (
            <>
              <div className="space-y-2">
                <Label htmlFor="newPassword">New password</Label>
                <Input
                  id="newPassword"
                  type="password"
                  autoComplete="new-password"
                  minLength={AUTH_PASSWORD_MIN_LENGTH}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  More than 6 characters.
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="confirmNewPassword">Confirm new password</Label>
                <Input
                  id="confirmNewPassword"
                  type="password"
                  autoComplete="new-password"
                  minLength={AUTH_PASSWORD_MIN_LENGTH}
                  value={confirmNewPassword}
                  onChange={(e) => setConfirmNewPassword(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && submitNewPassword()}
                />
              </div>
              <Button
                className="w-full gradient-gold text-primary-foreground"
                onClick={submitNewPassword}
                disabled={loading}
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Update password"}
              </Button>
            </>
          )}

          {step === "done" && (
            <Button
              className="w-full gradient-gold text-primary-foreground"
              onClick={() => navigate({ to: "/login" })}
            >
              Go to login
            </Button>
          )}

          {step !== "done" && (
            <p className="text-sm text-center text-muted-foreground">
              Remembered your password?{" "}
              <Link to="/login" className="text-gold hover:underline font-medium">
                Log in
              </Link>
            </p>
          )}
        </CardContent>
      </Card>
    </AuthLayout>
  );
}
