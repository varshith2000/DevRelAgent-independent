import { type Metadata } from 'next';
import '../theme.css';

export const metadata: Metadata = {
  title: 'The Deck - DevRelAgent Dashboard',
  description: 'Real-time system health monitoring dashboard',
};

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
