"use client";
import { AppShell, NavItem } from "@/components/AppShell";
import { LayoutDashboard, KeyRound, Wallet, ScrollText, Settings } from "lucide-react";

const nav: NavItem[] = [
  { href: "/dashboard", label: "概览", icon: LayoutDashboard },
  { href: "/dashboard/tokens", label: "令牌管理", icon: KeyRound },
  { href: "/dashboard/recharge", label: "充值", icon: Wallet },
  { href: "/dashboard/logs", label: "账单日志", icon: ScrollText },
  { href: "/dashboard/settings", label: "账户设置", icon: Settings },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return <AppShell nav={nav}>{children}</AppShell>;
}
