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

        console.log(`[API] Starting video generation with prompt: "${prompt}"`);

        // Python script location relative to frontend
        const scriptDir = path.resolve(process.cwd(), '..');
        const scriptPath = path.join(scriptDir, 'run_pipeline_v2.py');

        return new Promise((resolve) => {
            const pythonProcess = spawn('python', [scriptPath, prompt], {
                cwd: scriptDir,
                env: { ...process.env, PYTHONUNBUFFERED: '1' } // Force unbuffered output
            });

            let output = '';
            let errorOutput = '';

            pythonProcess.stdout.on('data', (data) => {
                const chunk = data.toString();
                output += chunk;
                console.log(`[Python]: ${chunk.trim()}`);
            });

            pythonProcess.stderr.on('data', (data) => {
                const chunk = data.toString();
                errorOutput += chunk;
                console.error(`[Python API Error]: ${chunk.trim()}`);
            });

            pythonProcess.on('error', (err) => {
                console.error(`[Python Spawn Error]:`, err);
                resolve(NextResponse.json({ error: `Failed to start Python script: ${err.message}` }, { status: 500 }));
            });

            pythonProcess.on('close', (code) => {
                console.log(`[Python] Process exited with code ${code}`);
                
                if (code !== 0) {
                    resolve(NextResponse.json({ error: `Python script failed with code ${code}. ${errorOutput}` }, { status: 500 }));
                    return;
                }

                // Try to find the URL of the generated video
                // Look for '[APP_OUTPUT_URL]: https://...' in the output
                const urlMatch = output.match(/\[APP_OUTPUT_URL\]:\s*(https?:\/\/[^\s]+)/i);
                
                if (urlMatch && urlMatch[1]) {
                    console.log(`[API] Found video URL: ${urlMatch[1]}`);
                    resolve(NextResponse.json({ video_url: urlMatch[1] }));
                    return;
                }
                
                // Fallback to searching the output directory for a created video
                // Try to find the local fallback paths
                const localMatches = Array.from(output.matchAll(/\[APP_LOCAL_FILE\]:\s*([^\n\r]+)/gi));
                if (localMatches.length > 0) {
                    const pathsMatch = localMatches.map(m => m[1].trim());
                    // prefer 16x9 if multiple exist
                    const selectedPath = pathsMatch.find(p => p.includes('16x9')) || pathsMatch[0];
                    console.log(`[API] Found local video path: ${selectedPath}`);
                    
                    if (fs.existsSync(selectedPath)) {
                        const runIdMatch = output.match(/Run ID\s*:\s*([a-zA-Z0-9]+)/i);
                        const runId = (runIdMatch && runIdMatch[1]) ? runIdMatch[1] : 'unknown';
                        const filename = path.basename(selectedPath);
                        
                        const publicVideosDir = path.join(process.cwd(), 'public', 'videos', runId);
                        fs.mkdirSync(publicVideosDir, { recursive: true });
                        const destPath = path.join(publicVideosDir, filename);
                        fs.copyFileSync(selectedPath, destPath);
                        
                        const publicUrl = `/videos/${runId}/${filename}`;
                        console.log(`[API] Created local fallback URL: ${publicUrl}`);
                        resolve(NextResponse.json({ video_url: publicUrl }));
                        return;
                    }
                }
                
                resolve(NextResponse.json({ error: 'Video generated but could not locate the URL or output file.' }, { status: 500 }));
            });
        });
    } catch (error: any) {
        console.error('[API] Unexpected error:', error);
        return NextResponse.json({ error: error.message || 'Unknown error occurred' }, { status: 500 });
    }
}
