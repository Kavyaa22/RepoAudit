import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../providers/auth-provider";
import { env } from "../../config/env";
import {
  loadUserSettings,
  saveUserSettings,
  type StructureStyle,
  type UserLlmSettings,
} from "../../lib/user-settings";

export default function SettingsPage() {
  const navigate = useNavigate();
  const { user, refreshUser, updateProfile, deleteAccount, logout } = useAuth();

  const [fullName, setFullName] = useState(
    () => user?.full_name || localStorage.getItem("repoaudit_user_name") || ""
  );
  const [email, setEmail] = useState(
    () => user?.email || localStorage.getItem("repoaudit_user_email") || "user@example.com"
  );
  const [accountMessage, setAccountMessage] = useState<string | null>(null);
  const [accountError, setAccountError] = useState<string | null>(null);
  const [savingAccount, setSavingAccount] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deletePassword, setDeletePassword] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [llmSettings, setLlmSettings] = useState<UserLlmSettings>(() => loadUserSettings());
  const [auditMessage, setAuditMessage] = useState<string | null>(null);

  useEffect(() => {
    void refreshUser().catch(() => undefined);
  }, [refreshUser]);

  useEffect(() => {
    if (user?.full_name) setFullName(user.full_name);
    if (user?.email) setEmail(user.email);
  }, [user?.user_id, user?.full_name, user?.email]);

  const handleSaveProfile = useCallback(async () => {
    setSavingAccount(true);
    setAccountError(null);
    setAccountMessage(null);
    try {
      localStorage.setItem("repoaudit_user_name", fullName.trim());
      if (!env.authDisabled) {
        await updateProfile(fullName.trim());
      }
      setAccountMessage("Profile updated successfully.");
    } catch (err) {
      setAccountError(err instanceof Error ? err.message : "Failed to update profile");
    } finally {
      setSavingAccount(false);
    }
  }, [fullName, updateProfile]);

  const handleSaveAuditPrefs = useCallback(() => {
    saveUserSettings(llmSettings);
    setAuditMessage("Folder structure preference saved. New audits will use it.");
  }, [llmSettings]);

  const handleLogout = useCallback(async () => {
    await logout();
    navigate("/auth/login", { replace: true });
  }, [logout, navigate]);

  const handleDeleteAccount = useCallback(async () => {
    if (!deletePassword.trim()) {
      setAccountError("Enter your password to confirm account deletion.");
      return;
    }
    setDeleting(true);
    setAccountError(null);
    try {
      await deleteAccount(deletePassword);
      setShowDeleteModal(false);
      navigate("/auth/login", { replace: true });
    } catch (err) {
      setAccountError(err instanceof Error ? err.message : "Failed to delete account");
    } finally {
      setDeleting(false);
    }
  }, [deleteAccount, deletePassword, navigate]);

  return (
    <div className="mx-auto max-w-3xl space-y-6 pb-8">
      <div>
        <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">Settings</h1>
        <p className="mt-0.5 text-xs text-slate-500 font-medium">Manage your personal profile and active session.</p>
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-2xs space-y-5">
        <h2 className="text-base font-bold text-slate-900">Account Profile</h2>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <label className="block text-xs font-semibold text-slate-700">Full Name</label>
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Your full name"
              className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 bg-slate-50/50 text-xs text-slate-800 outline-none focus:bg-white focus:border-[#3B82F6] transition-all"
            />
          </div>

          <div className="space-y-1.5">
            <label className="block text-xs font-semibold text-slate-700">Email Address</label>
            <input
              type="email"
              value={email}
              readOnly
              disabled
              placeholder="name@example.com"
              className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 bg-slate-100 text-xs text-slate-500 cursor-not-allowed outline-none select-none"
            />
          </div>

          {accountMessage && (
            <p className="text-xs text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-xl px-3.5 py-2.5 font-bold">
              ✓ {accountMessage}
            </p>
          )}
          {accountError && (
            <p className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-xl px-3.5 py-2.5 font-bold">
              ⚠ {accountError}
            </p>
          )}

          <div className="flex flex-wrap gap-2.5 pt-2">
            <button
              type="button"
              onClick={() => void handleSaveProfile()}
              disabled={savingAccount || !fullName.trim()}
              className="px-5 py-2.5 bg-[#3B82F6] hover:bg-[#2563EB] text-white text-xs font-bold rounded-xl shadow-xs transition-all disabled:opacity-50 cursor-pointer"
            >
              {savingAccount ? "Saving…" : "Save profile"}
            </button>
            <button
              type="button"
              onClick={() => void handleLogout()}
              className="px-4 py-2.5 border border-slate-200 text-slate-700 text-xs font-bold rounded-xl hover:bg-slate-50 transition-all cursor-pointer"
            >
              Logout
            </button>
            {!env.authDisabled && (
              <button
                type="button"
                onClick={() => setShowDeleteModal(true)}
                className="px-4 py-2.5 border border-red-200 text-red-700 text-xs font-bold rounded-xl hover:bg-red-50 transition-all cursor-pointer"
              >
                Delete account
              </button>
            )}
          </div>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-2xs space-y-5">
        <h2 className="text-base font-bold text-slate-900">Folder structure style</h2>
        <p className="text-xs text-slate-500">
          Chooses how RepoAudit suggests rearranging folders in new audits.
        </p>
        <div className="space-y-1.5">
          <label className="block text-xs font-semibold text-slate-700">Preferred layout</label>
          <select
            value={llmSettings.structureStyle}
            onChange={(e) =>
              setLlmSettings((prev) => ({
                ...prev,
                structureStyle: e.target.value as StructureStyle,
              }))
            }
            className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 bg-slate-50/50 text-xs text-slate-800 outline-none focus:bg-white focus:border-[#3B82F6]"
          >
            <option value="action_api">Feature → action → files</option>
            <option value="conservative">Conservative (keep current roots, fewer moves)</option>
          </select>
        </div>
        {auditMessage && (
          <p className="text-xs text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-xl px-3.5 py-2.5 font-bold">
            ✓ {auditMessage}
          </p>
        )}
        <button
          type="button"
          onClick={handleSaveAuditPrefs}
          className="px-5 py-2.5 bg-[#3B82F6] hover:bg-[#2563EB] text-white text-xs font-bold rounded-xl shadow-xs transition-all cursor-pointer"
        >
          Save folder preference
        </button>
      </section>

      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40">
          <div className="bg-white rounded-2xl shadow-xl max-w-md w-full p-6 border border-slate-200 space-y-4">
            <div>
              <h3 className="text-base font-bold text-slate-900">Delete Account</h3>
              <p className="text-xs text-slate-500 mt-1">
                Enter your password to confirm permanent account deletion.
              </p>
            </div>
            <input
              type="password"
              value={deletePassword}
              onChange={(e) => setDeletePassword(e.target.value)}
              placeholder="Enter password"
              className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-xs outline-none focus:border-red-500"
            />
            <div className="flex justify-end gap-2.5 pt-2">
              <button
                type="button"
                onClick={() => {
                  setShowDeleteModal(false);
                  setDeletePassword("");
                }}
                className="px-4 py-2 text-xs text-slate-600 hover:bg-slate-100 rounded-xl font-bold"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void handleDeleteAccount()}
                disabled={deleting}
                className="px-4 py-2 text-xs font-bold bg-red-600 hover:bg-red-700 text-white rounded-xl disabled:opacity-50 cursor-pointer"
              >
                {deleting ? "Deleting…" : "Delete Permanently"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
