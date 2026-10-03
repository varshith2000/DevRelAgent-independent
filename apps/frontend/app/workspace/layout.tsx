import { type Metadata } from 'next';
import '../theme.css';

export const metadata: Metadata = {
  title: 'Workspace - DevRelAgent',
  description: 'Manage projects, members and API keys for your workspace',
};

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  return children;
}
