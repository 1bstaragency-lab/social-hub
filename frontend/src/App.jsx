import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "react-hot-toast";
import {
  LayoutDashboard, Users, Megaphone, Calendar,
  BarChart2, Zap, Settings, ChevronRight, Menu, X
} from "lucide-react";

import DashboardOverview from "./components/dashboard/DashboardOverview";
import AccountList from "./components/accounts/AccountList";
import PostScheduler from "./components/posts/PostScheduler";
import BulkEngagementModal from "./components/accounts/BulkEngagementModal";

const qc = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
});

const NAV_ITEMS = [
  { key: "dashboard",   label: "Dashboard",   icon: LayoutDashboard },
  { key: "accounts",    label: "Accounts",     icon: Users },
  { key: "campaigns",   label: "Campaigns",    icon: Megaphone },
  { key: "posts",       label: "Posts",        icon: Calendar },
  { key: "analytics",  label: "Analytics",    icon: BarChart2 },
];

function Sidebar({ page, setPage, collapsed, setCollapsed }) {
  return (
    <aside className={`
      bg-gray-900 text-white flex flex-col transition-all duration-200
      ${collapsed ? "w-16" : "w-56"}
    `}>
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 py-5 border-b border-gray-800">
        <span className="text-xl">🎵</span>
        {!collapsed && (
          <span className="font-bold text-lg tracking-tight">SocialHub</span>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="ml-auto p-1 hover:bg-gray-800 rounded transition"
        >
          {collapsed ? <ChevronRight size={14} /> : <Menu size={14} />}
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-4 space-y-1 px-2">
        {NAV_ITEMS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setPage(key)}
            className={`
              w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition
              ${page === key
                ? "bg-indigo-600 text-white"
                : "text-gray-400 hover:bg-gray-800 hover:text-white"
              }
            `}
          >
            <Icon size={16} className="shrink-0" />
            {!collapsed && <span>{label}</span>}
          </button>
        ))}
      </nav>

      {/* Bottom */}
      <div className="px-2 pb-4">
        <button className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-gray-400 hover:bg-gray-800 hover:text-white transition">
          <Settings size={16} className="shrink-0" />
          {!collapsed && <span>Settings</span>}
        </button>
      </div>
    </aside>
  );
}

function PageContent({ page, showBulk, setShowBulk }) {
  switch (page) {
    case "dashboard":
      return (
        <div>
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-xl font-bold text-gray-900">Dashboard</h1>
              <p className="text-sm text-gray-400">Live overview across all accounts</p>
            </div>
            <button
              onClick={() => setShowBulk(true)}
              className="flex items-center gap-1.5 text-sm px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition"
            >
              <Zap size={14} /> Bulk Action
            </button>
          </div>
          <DashboardOverview />
        </div>
      );
    case "accounts":
      return (
        <div>
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-xl font-bold text-gray-900">Accounts</h1>
              <p className="text-sm text-gray-400">Manage and monitor all social accounts</p>
            </div>
            <button
              onClick={() => setShowBulk(true)}
              className="flex items-center gap-1.5 text-sm px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition"
            >
              <Zap size={14} /> Bulk Engagement
            </button>
          </div>
          <AccountList />
        </div>
      );
    case "posts":
      return (
        <div>
          <div className="mb-6">
            <h1 className="text-xl font-bold text-gray-900">Posts & Scheduling</h1>
            <p className="text-sm text-gray-400">Create, schedule, and cross-post content</p>
          </div>
          <PostScheduler />
        </div>
      );
    case "campaigns":
      return (
        <div>
          <h1 className="text-xl font-bold text-gray-900 mb-2">Campaigns</h1>
          <p className="text-sm text-gray-400">Campaign management coming soon.</p>
        </div>
      );
    case "analytics":
      return (
        <div>
          <h1 className="text-xl font-bold text-gray-900 mb-2">Analytics</h1>
          <p className="text-sm text-gray-400">Growth charts and engagement metrics coming soon.</p>
        </div>
      );
    default:
      return null;
  }
}

export default function App() {
  const [page, setPage] = useState("dashboard");
  const [collapsed, setCollapsed] = useState(false);
  const [showBulk, setShowBulk] = useState(false);

  return (
    <QueryClientProvider client={qc}>
      <div className="flex h-screen bg-gray-50 overflow-hidden">
        <Sidebar page={page} setPage={setPage} collapsed={collapsed} setCollapsed={setCollapsed} />

        <main className="flex-1 overflow-y-auto">
          <div className="max-w-7xl mx-auto px-6 py-6">
            <PageContent page={page} showBulk={showBulk} setShowBulk={setShowBulk} />
          </div>
        </main>
      </div>

      {showBulk && <BulkEngagementModal onClose={() => setShowBulk(false)} />}
      <Toaster position="top-right" />
    </QueryClientProvider>
  );
}
