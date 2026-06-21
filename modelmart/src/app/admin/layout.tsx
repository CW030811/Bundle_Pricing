"use client";
import { AppShell, NavItem } from "@/components/AppShell";
import { BarChart3, Users, Server, Boxes, Receipt, Ticket, Megaphone } from "lucide-react";

const nav: NavItem[] = [
  { href: "/admin", label: "数据看板", icon: BarChart3 },
  { href: "/admin/users", label: "用户管理", icon: Users },
  { href: "/admin/channels", label: "渠道 (进货/调度)", icon: Server },
  { href: "/admin/models", label: "商品 (模型)", icon: Boxes },
  { href: "/admin/orders", label: "订单 (财务)", icon: Receipt },
  { href: "/admin/redeem", label: "兑换码", icon: Ticket },
  { href: "/admin/announcements", label: "公告", icon: Megaphone },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <AppShell nav={nav}>{children}</AppShell>;
}
