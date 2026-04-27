import type { LucideIcon } from "lucide-react";

export type Workspace = { id: string; name: string; description: string };
export type Team = { id: string; name: string; role: string };

export type RouteMetadata = {
  path: string;
  navLabel: string;
  title: string;
  eyebrow: string;
  icon: LucideIcon;
};
