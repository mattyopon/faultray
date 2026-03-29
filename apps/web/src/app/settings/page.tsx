"use client";

import { useAuth } from "@/components/auth-provider";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  User,
  CreditCard,
  Key,
  Bell,
  ExternalLink,
} from "lucide-react";

export default function SettingsPage() {
  const { user } = useAuth();

  return (
    <div className="max-w-[800px] mx-auto px-6 py-10">
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1">Settings</h1>
        <p className="text-[#94a3b8] text-sm">Manage your account and subscription</p>
      </div>

      {/* Profile */}
      <Card className="mb-6">
        <div className="flex items-center gap-3 mb-6">
          <User size={20} className="text-[#FFD700]" />
          <h2 className="text-lg font-bold">Profile</h2>
        </div>
        <div className="space-y-4">
          <div className="grid grid-cols-[120px_1fr] items-center gap-4">
            <span className="text-sm text-[#64748b]">Email</span>
            <span className="text-sm">{user?.email || "Not signed in"}</span>
          </div>
          <div className="grid grid-cols-[120px_1fr] items-center gap-4">
            <span className="text-sm text-[#64748b]">Name</span>
            <span className="text-sm">{user?.user_metadata?.full_name || "Not set"}</span>
          </div>
          <div className="grid grid-cols-[120px_1fr] items-center gap-4">
            <span className="text-sm text-[#64748b]">Provider</span>
            <span className="text-sm capitalize">{user?.app_metadata?.provider || "N/A"}</span>
          </div>
          <div className="grid grid-cols-[120px_1fr] items-center gap-4">
            <span className="text-sm text-[#64748b]">Member since</span>
            <span className="text-sm">
              {user?.created_at ? new Date(user.created_at).toLocaleDateString() : "N/A"}
            </span>
          </div>
        </div>
      </Card>

      {/* Subscription */}
      <Card className="mb-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <CreditCard size={20} className="text-[#FFD700]" />
            <h2 className="text-lg font-bold">Subscription</h2>
          </div>
          <Badge variant="gold">Free Plan</Badge>
        </div>
        <div className="space-y-4 mb-6">
          <div className="grid grid-cols-[120px_1fr] items-center gap-4">
            <span className="text-sm text-[#64748b]">Plan</span>
            <span className="text-sm">Free</span>
          </div>
          <div className="grid grid-cols-[120px_1fr] items-center gap-4">
            <span className="text-sm text-[#64748b]">Simulations</span>
            <div>
              <div className="flex items-center gap-2">
                <div className="h-2 w-32 bg-white/5 rounded-full overflow-hidden">
                  <div className="h-full w-2/5 bg-[#FFD700] rounded-full" />
                </div>
                <span className="text-xs text-[#64748b]">2 / 5 this month</span>
              </div>
            </div>
          </div>
          <div className="grid grid-cols-[120px_1fr] items-center gap-4">
            <span className="text-sm text-[#64748b]">Components</span>
            <span className="text-sm">5 max</span>
          </div>
        </div>
        <Button size="sm">
          <CreditCard size={14} /> Upgrade to Pro
        </Button>
      </Card>

      {/* API Keys */}
      <Card className="mb-6">
        <div className="flex items-center gap-3 mb-6">
          <Key size={20} className="text-[#FFD700]" />
          <h2 className="text-lg font-bold">API Keys</h2>
        </div>
        <p className="text-sm text-[#94a3b8] mb-4">
          Use API keys to authenticate requests to the FaultRay API from your CI/CD pipeline.
        </p>
        <Button variant="secondary" size="sm">
          Generate API Key
        </Button>
      </Card>

      {/* Notifications */}
      <Card className="mb-6">
        <div className="flex items-center gap-3 mb-6">
          <Bell size={20} className="text-[#FFD700]" />
          <h2 className="text-lg font-bold">Notifications</h2>
        </div>
        <div className="space-y-4">
          {[
            { label: "Simulation completed", desc: "Get notified when a simulation finishes", enabled: true },
            { label: "Score degradation", desc: "Alert when resilience score drops below threshold", enabled: true },
            { label: "Weekly summary", desc: "Receive a weekly resilience report", enabled: false },
          ].map((n) => (
            <div key={n.label} className="flex items-center justify-between py-2">
              <div>
                <p className="text-sm font-medium">{n.label}</p>
                <p className="text-xs text-[#64748b]">{n.desc}</p>
              </div>
              <button
                className={`relative w-11 h-6 rounded-full transition-colors ${
                  n.enabled ? "bg-[#FFD700]" : "bg-[#1e293b]"
                }`}
              >
                <span
                  className={`absolute top-0.5 w-5 h-5 rounded-full bg-white transition-transform ${
                    n.enabled ? "left-[22px]" : "left-0.5"
                  }`}
                />
              </button>
            </div>
          ))}
        </div>
      </Card>

      {/* Danger Zone */}
      <Card className="border-red-500/20">
        <h2 className="text-lg font-bold text-red-400 mb-4">Danger Zone</h2>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">Delete Account</p>
            <p className="text-xs text-[#64748b]">Permanently delete your account and all data</p>
          </div>
          <Button variant="danger" size="sm">Delete Account</Button>
        </div>
      </Card>
    </div>
  );
}
