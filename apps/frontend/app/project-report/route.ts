import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { NextResponse } from 'next/server';

export const dynamic = 'force-static';

export async function GET() {
  const candidates = [
    path.join(process.cwd(), 'PROJECT_REPORT.md'),
    path.join(process.cwd(), '..', '..', 'PROJECT_REPORT.md'),
  ];
  for (const reportPath of candidates) {
    try {
      const report = await readFile(reportPath, 'utf8');
      return new NextResponse(report, {
        headers: {
          'Content-Type': 'text/markdown; charset=utf-8',
          'Content-Disposition': 'inline; filename="DevRelAgent-project-report.md"',
          'Cache-Control': 'public, max-age=3600',
        },
      });
    } catch {
      // Continue to the repository-root candidate (local) or bundled copy (Docker).
    }
  }
  return NextResponse.json({ error: 'Project report is not available.' }, { status: 404 });
}
