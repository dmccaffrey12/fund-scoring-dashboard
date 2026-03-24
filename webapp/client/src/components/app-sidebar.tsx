import {
  LayoutDashboard,
  Table2,
  Search,
  BarChart3,
  Shield,
  Upload,
} from "lucide-react";
import { Link, useLocation } from "wouter";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarHeader,
  SidebarFooter,
} from "@/components/ui/sidebar";
import { PerplexityAttribution } from "@/components/PerplexityAttribution";

const navItems = [
  { title: "Dashboard", url: "/", icon: LayoutDashboard },
  { title: "Batch Scores", url: "/scores", icon: Table2 },
  { title: "Fund Lookup", url: "/lookup", icon: Search },
  { title: "Category Analysis", url: "/categories", icon: BarChart3 },
  { title: "Monitoring", url: "/monitoring", icon: Shield },
  { title: "CSV Upload", url: "/upload", icon: Upload },
];

export function AppSidebar() {
  const [location] = useLocation();

  return (
    <Sidebar>
      <SidebarHeader className="p-4 border-b border-sidebar-border">
        <div className="flex items-center gap-3">
          <svg
            width="32"
            height="32"
            viewBox="0 0 32 32"
            fill="none"
            aria-label="FundScore Logo"
            className="flex-shrink-0"
          >
            <rect x="2" y="2" width="28" height="28" rx="6" stroke="currentColor" strokeWidth="1.5" className="text-primary" />
            <path d="M8 22 L12 14 L16 18 L20 10 L24 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-primary" />
            <circle cx="24" cy="12" r="2" fill="currentColor" className="text-primary" />
          </svg>
          <div>
            <h1 className="text-sm font-bold tracking-tight">FundScore</h1>
            <p className="text-[11px] text-muted-foreground font-mono">v2.0 · 2026</p>
          </div>
        </div>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel className="text-[10px] uppercase tracking-widest text-muted-foreground px-4">
            Navigation
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {navItems.map((item) => {
                const isActive = location === item.url || 
                  (item.url !== "/" && location.startsWith(item.url));
                return (
                  <SidebarMenuItem key={item.title}>
                    <SidebarMenuButton
                      asChild
                      isActive={isActive}
                      data-testid={`nav-${item.title.toLowerCase().replace(/\s/g, "-")}`}
                    >
                      <Link href={item.url}>
                        <item.icon className="w-4 h-4" />
                        <span className="text-sm">{item.title}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter className="p-3 border-t border-sidebar-border">
        <PerplexityAttribution />
      </SidebarFooter>
    </Sidebar>
  );
}
