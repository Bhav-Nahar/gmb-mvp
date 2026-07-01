import DashboardShell from "@/components/DashboardShell";
import AuthGuard from "@/components/AuthGuard";
import ImpersonationBanner from "@/components/ImpersonationBanner";
import { WhatsAppWidget } from "@/components/WhatsAppWidget";
import { FeatureRouteGuard } from "@/components/FeatureRouteGuard";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <ImpersonationBanner />
      <DashboardShell>
        <FeatureRouteGuard>{children}</FeatureRouteGuard>
      </DashboardShell>
      <WhatsAppWidget />
    </AuthGuard>
  );
}
