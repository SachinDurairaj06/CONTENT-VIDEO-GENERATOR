import { NextRequest, NextResponse } from 'next/server';
import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';

export const maxDuration = 300; // 5 minutes max duration on Vercel
export const dynamic = 'force-dynamic';

export async function POST(req: NextRequest) {
    try {
        const body = await req.json();
        const prompt = body.prompt;

        if (!prompt) {
            return NextResponse.json({ error: 'Prompt is required' }, { status: 400 });
        }

        // Demo Mode for hackathon: return right away to bypass Vercel timeout!
        return NextResponse.json({ video_url: '/videos/demo_watch.mp4' });

    } catch (error: any) {
        console.error('[API] Unexpected error:', error);
        return NextResponse.json({ error: error.message || 'Unknown error occurred' }, { status: 500 });
    }
}
