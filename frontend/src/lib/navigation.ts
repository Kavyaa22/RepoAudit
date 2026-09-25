export type NavItem = {
  label: string;
  path: string;
};

export const mainNav: NavItem[] = [
  { label: "Dashboard", path: "/dashboard" },
  { label: "Repositories", path: "/repositories" },
  { label: "Audit", path: "/audit" },
  { label: "Issue Investigator", path: "/investigation" },
];
