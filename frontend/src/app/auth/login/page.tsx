import { type FormEvent, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../../../providers/auth-provider";

export default function LoginPage() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const isExpired = searchParams.get("reason") === "expired";

  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [fullName, setFullName] = useState("");

  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const cleanEmail = email.trim().toLowerCase();
  const isEmailValid = cleanEmail.includes("@") && cleanEmail.indexOf("@") > 0 && cleanEmail.indexOf("@") < cleanEmail.length - 1;
  const isPasswordMatch = mode === "register" && confirmPassword.length > 0 && password === confirmPassword;
  const isPasswordMismatch = mode === "register" && confirmPassword.length > 0 && password !== confirmPassword;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (!isEmailValid) {
      setError("Please enter a valid email address.");
      return;
    }

    if (mode === "register") {
      if (!fullName.trim()) {
        setError("Please enter your full name.");
        return;
      }
      if (password !== confirmPassword) {
        setError("Password and confirm password do not match.");
        return;
      }
    }

    setBusy(true);

    try {
      if (mode === "login") {
        await login(cleanEmail, password);
      } else {
        await register(cleanEmail, password, fullName.trim(), confirmPassword);
      }
      navigate("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-md mx-auto my-6">
      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-5">
        {/* Header Title */}
        <div className="text-center space-y-1">
          <h1 className="text-xl font-bold text-slate-800">
            {mode === "login" ? "Sign In" : "Create Account"}
          </h1>
          <p className="text-xs text-slate-500">
            Enter your credentials to continue
          </p>
        </div>

        {/* Mode Toggle Tabs */}
        <div className="grid grid-cols-2 p-1 bg-slate-100 rounded-lg text-xs font-medium">
          <button
            type="button"
            onClick={() => {
              setMode("login");
              setError(null);
            }}
            className={`py-1.5 rounded-md transition-colors ${
              mode === "login"
                ? "bg-white text-slate-900 shadow-2xs font-semibold"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            Sign In
          </button>
          <button
            type="button"
            onClick={() => {
              setMode("register");
              setError(null);
            }}
            className={`py-1.5 rounded-md transition-colors ${
              mode === "register"
                ? "bg-white text-slate-900 shadow-2xs font-semibold"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            Sign Up
          </button>
        </div>

        {isExpired && !error && (
          <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-xs text-blue-800 font-medium">
            Your login session expired. Please sign in again to continue.
          </div>
        )}

        {error && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
            {error}
          </div>
        )}

        <form onSubmit={onSubmit} className="space-y-4">
          {mode === "register" && (
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-700">Full Name</label>
              <input
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-xs text-slate-800 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                placeholder="Full Name"
                type="text"
                required
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
              />
            </div>
          )}

          <div className="space-y-1">
            <label className="text-xs font-medium text-slate-700">Email</label>
            <input
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-xs text-slate-800 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
              placeholder="name@example.com"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium text-slate-700">Password</label>
            <div className="relative">
              <input
                className="w-full rounded-lg border border-slate-300 pl-3 pr-9 py-2 text-xs text-slate-800 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                placeholder="Password"
                type={showPassword ? "text" : "password"}
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 text-xs"
              >
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
          </div>

          {mode === "register" && (
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-700">Confirm Password</label>
              <div className="relative">
                <input
                  className={`w-full rounded-lg border pl-3 pr-9 py-2 text-xs text-slate-800 outline-none transition-colors ${
                    isPasswordMismatch
                      ? "border-red-300 bg-red-50/50"
                      : isPasswordMatch
                      ? "border-emerald-300 bg-emerald-50/30"
                      : "border-slate-300 focus:border-blue-500"
                  }`}
                  placeholder="Confirm Password"
                  type={showConfirmPassword ? "text" : "password"}
                  required
                  minLength={8}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 text-xs"
                >
                  {showConfirmPassword ? "Hide" : "Show"}
                </button>
              </div>
              {isPasswordMismatch && (
                <p className="text-[13px] text-red-600 font-medium mt-1">Passwords do not match</p>
              )}
              {isPasswordMatch && (
                <p className="text-[13px] text-emerald-700 font-medium mt-1">✓ Passwords match</p>
              )}
            </div>
          )}

          <button
            type="submit"
            disabled={busy || !isEmailValid || (mode === "register" && isPasswordMismatch)}
            className="w-full mt-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white py-2 text-xs font-semibold transition-colors disabled:opacity-50"
          >
            {busy ? "Authenticating…" : mode === "login" ? "Sign In" : "Register"}
          </button>
        </form>

        <div className="pt-2 text-center text-xs text-slate-500 border-t border-slate-100">
          {mode === "login" ? (
            <p>
              Need an account?{" "}
              <button
                type="button"
                onClick={() => {
                  setMode("register");
                  setError(null);
                }}
                className="text-blue-600 font-semibold hover:underline"
              >
                Sign Up
              </button>
            </p>
          ) : (
            <p>
              Already registered?{" "}
              <button
                type="button"
                onClick={() => {
                  setMode("login");
                  setError(null);
                }}
                className="text-blue-600 font-semibold hover:underline"
              >
                Sign In
              </button>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
