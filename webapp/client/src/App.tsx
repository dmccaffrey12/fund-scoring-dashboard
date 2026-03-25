import { Switch, Route, Router } from "wouter";
import { useHashLocation } from "wouter/use-hash-location";
import { queryClient } from "./lib/queryClient";
import { QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/app-sidebar";
import Dashboard from "@/pages/dashboard";
import BatchScores from "@/pages/batch-scores";
import FundLookup from "@/pages/fund-lookup";
import CategoryAnalysis from "@/pages/category-analysis";
import History from "@/pages/history";
import Monitoring from "@/pages/monitoring";
import CsvUpload from "@/pages/csv-upload";
import NotFound from "@/pages/not-found";
import { useEffect, useState } from "react";

function ThemeToggle() {
  const [dark, setDark] = useState(true);

  useEffect(() => {
    document.documentElement.classList.add("dark");
  }, []);

  const toggle = () => {
    setDark(!dark);
    document.documentElement.classList.toggle("dark");
  };

  return (
    <button
      onClick={toggle}
      className="p-2 rounded-md hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
      aria-label={`Switch to ${dark ? "light" : "dark"} mode`}
      data-testid="button-theme-toggle"
    >
      {dark ? (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="5" />
          <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
        </svg>
      ) : (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      )}
    </button>
  );
}

function AppRouter() {
  return (
    <Switch>
      <Route path="/" component={Dashboard} />
      <Route path="/scores" component={BatchScores} />
      <Route path="/lookup" component={FundLookup} />
      <Route path="/lookup/:symbol" component={FundLookup} />
      <Route path="/categories" component={CategoryAnalysis} />
      <Route path="/categories/:name" component={CategoryAnalysis} />
      <Route path="/history" component={History} />
      <Route path="/monitoring" component={Monitoring} />
      <Route path="/upload" component={CsvUpload} />
      <Route component={NotFound} />
    </Switch>
  );
}

function AppLayout() {
  const style = {
    "--sidebar-width": "14rem",
    "--sidebar-width-icon": "3rem",
  };

  return (
    <SidebarProvider style={style as React.CSSProperties}>
      <div className="flex h-screen w-full overflow-hidden">
        <AppSidebar />
        <div className="flex flex-col flex-1 min-w-0">
          <header className="flex items-center justify-between px-4 py-2 border-b border-border bg-background/80 backdrop-blur-sm z-10">
            <div className="flex items-center gap-2">
              <SidebarTrigger data-testid="button-sidebar-toggle" />
              <span className="text-xs text-muted-foreground font-mono">
                $700M+ AUM
              </span>
            </div>
            <ThemeToggle />
          </header>
          <main className="flex-1 overflow-y-auto">
            <AppRouter />
          </main>
        </div>
      </div>
    </SidebarProvider>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <Router hook={useHashLocation}>
          <AppLayout />
        </Router>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}
