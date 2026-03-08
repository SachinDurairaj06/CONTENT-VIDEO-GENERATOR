/**
 * Unified Flow API Service
 * Handles communication with the local backend.
 */

export interface GenerateRequest {
    prompt: string;
    language_code?: string;
    aspect_ratio?: string;
    style?: string;
}

export interface PipelineStatus {
    status: "RUNNING" | "SUCCEEDED" | "FAILED" | "TIMED_OUT";
    output?: {
        final_video_uri?: string;
        download_url?: string;
        error?: string;
    };
}

/**
 * Calls the local Next.js API endpoint to trigger the python script.
 */
export async function startPipeline(request: GenerateRequest): Promise<string> {
    console.log("[API] Starting pipeline with request:", request);
    
    // We will wait for the whole pipeline to finish in trigger, to keep it simple locally
    const response = await fetch('/api/generate', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(request)
    });
    
    if (!response.ok) {
        let errStr = response.statusText;
        try {
            const errData = await response.json();
            if (errData.error) errStr = errData.error;
        } catch (e) {
            // response wasn't JSON
        }
        throw new Error(`API error: ${errStr}`);
    }
    
    const data = await response.json();
    if (data.error) {
        throw new Error(data.error);
    }
    
    // We get the final video url directly to keep it simple since it's local
    return data.video_url || data.local_url;
}

/**
 * Returns the completion status. Since startPipeline now blocks until completion, this just returns success.
 */
export async function waitForCompletion(
    executionArn: string, // the returned string from startPipeline is actually the video url now
    intervalMs: number = 5000,
    maxAttempts: number = 2
): Promise<PipelineStatus> {
    return { 
        status: "SUCCEEDED",
        output: {
            download_url: executionArn
        }
    };
}
