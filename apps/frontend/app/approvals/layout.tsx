import { type Metadata } from 'next';
import '../theme.css';

export const metadata: Metadata = {
  title: 'Approvals - DevRelAgent',
  description: 'Review and respond to human-in-the-loop approval requests',
};

export default function ApprovalsLayout({ children }: { children: React.ReactNode }) {
  return children;
}
