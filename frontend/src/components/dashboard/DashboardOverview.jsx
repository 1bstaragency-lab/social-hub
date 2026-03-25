import { useQuery } from "@tanstack/react-query";
import { analyticsApi } from "../../services/api";
import {
  Users, Activity, Calendar, TrendingUp,
  AlertCircle, CheckCircle2, Music, Radio
} from "lucide-react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

const PLATFORM_COLORS = {
  soundcloud: "#ff5500",
  tiktok: "#010101",
  twitter: "#1da1f2",
  spotify: "#1db954",
};

const PLATFORM_ICONS = {
  soundcloud: "🎵",
  tiktok: "🎬",
  twitter: "🐦",
  spotify: "🎧",
};

function StatCard({ title, value, icon: Icon, color, sub }) {
  return (
    <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100 flex items-start gap-4">
      <div className={`p-3 rounded-lg ${color}`}>
        <Icon size={20} className="text-white" />
      </div>
      <div>
        <p className="text-sm text-gray-500">{title}</p>
        <p className="text-2xl font-bold text-gray-900">{value?.toLocaleString() ?? "—"}</p>
        {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
      </div>
    </div>
  );
}

function AccountRow({ account }) {
  const color = PLATFORM_COLORS[account.platform] || "#888";
  const icon = PLATFORM_ICONS[account.platform] || "📱";
  return (
    <tr className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
      <td className="py-3 px-4">
        <div className="flex items-center gap-2">
          <span>{icon}</span>
          <span className="font-medium text-gray-800 text-sm">{account.username}</span>
        </div>
      </td>
      <td className="py-3 px-4">
        <span
          className="text-xs px-2 py-1 rounded-full font-medium capitalize"
          style={{ backgroundColor: color + "20", color }}
        >
          {account.platform}
        </span>
      </td>
      <td className="py-3 px-4 text-sm text-gray-700">{account.followers?.toLocaleString()}</td>
      <td className="py-3 px-4 text-sm text-gray-700">{account.engagement_rate?.toFixed(2)}%</td>
      <td className="py-3 px-4 text-sm text-gray-700">{account.posts_last_7d}</td>
      <td className="py-3 px-4 text-sm text-gray-700">{account.plays_last_7d?.toLocaleString()}</td>
    </tr>
  );
}

export default function DashboardOverview({ organizationId }) {
  const { data, isLoading } = useQuery({
    queryKey: ["dashboard", organizationId],
    queryFn: () => analyticsApi.dashboard(organizationId ? { organization_id: organizationId } : {}),
    select: (r) => r.data,
    refetchInterval: 60_000,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400">
        Loading dashboard…
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Stat Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Total Accounts"
          value={data?.total_accounts}
          icon={Users}
          color="bg-blue-500"
          sub={`${data?.active_accounts} active`}
        />
        <StatCard
          title="Total Followers"
          value={data?.total_followers}
          icon={TrendingUp}
          color="bg-purple-500"
          sub={`Avg ${data?.avg_engagement_rate}% engagement`}
        />
        <StatCard
          title="Scheduled Posts"
          value={data?.total_posts_scheduled}
          icon={Calendar}
          color="bg-orange-500"
          sub={`${data?.total_posts_published_today} published today`}
        />
        <StatCard
          title="Needs Re-auth"
          value={data?.accounts_needing_reauth}
          icon={AlertCircle}
          color={data?.accounts_needing_reauth > 0 ? "bg-red-500" : "bg-green-500"}
          sub={data?.accounts_needing_reauth === 0 ? "All sessions healthy" : "Action required"}
        />
      </div>

      {/* Account Table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100">
        <div className="px-5 py-4 border-b border-gray-100">
          <h2 className="font-semibold text-gray-800">Account Overview</h2>
          <p className="text-xs text-gray-400 mt-0.5">Live metrics across all platforms</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-gray-100">
                {["Account", "Platform", "Followers", "Engagement", "Posts (7d)", "Plays (7d)"].map(h => (
                  <th key={h} className="py-2.5 px-4 text-xs font-semibold text-gray-400 uppercase tracking-wide">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data?.account_summaries?.map((a) => (
                <AccountRow key={a.account_id} account={a} />
              ))}
              {!data?.account_summaries?.length && (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-gray-400 text-sm">
                    No accounts yet. Add your first account to get started.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
