import DashboardShell from "@/components/DashboardShell";
import AuthGuard from "@/components/AuthGuard";
import ImpersonationBanner from "@/components/ImpersonationBanner";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <ImpersonationBanner />
      <DashboardShell>{children}</DashboardShell>
    </AuthGuard>
  );
}
