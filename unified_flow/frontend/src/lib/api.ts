/**
 * Unified Flow API Service
 * Handles communication with the AWS API Gateway / Step Functions backend.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "https://YOUR_API_GATEWAY_URL";

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
 * Triggers the Unified Flow pipeline by sending a POST to API Gateway,
 * which starts the Step Functions state machine.
 */
export async function startPipeline(request: GenerateRequest): Promise<string> {
    const response = await fetch(`${API_BASE_URL}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            prompt: request.prompt,
            style: request.style,
            language_code: request.language_code,
            aspect_ratio: request.aspect_ratio,
        }),
    });

    if (!response.ok) {
        throw new Error(`Pipeline trigger failed: ${response.statusText}`);
    }

    const data = await response.json();
    return data.executionArn; // Used to poll status
}

/**
 * Polls the execution status of a running Step Functions pipeline.
 * In production, this would hit a /status?executionArn=... endpoint
 * backed by a Lambda that calls DescribeExecution.
 */
export async function getPipelineStatus(executionArn: string): Promise<PipelineStatus> {
    const response = await fetch(
        `${API_BASE_URL}/status?executionArn=${encodeURIComponent(executionArn)}`
    );

    if (!response.ok) {
        throw new Error(`Status check failed: ${response.statusText}`);
    }

    return response.json();
}

/**
 * Utility: polls until the pipeline is no longer RUNNING.
 * Returns the final status.
 */
export async function waitForCompletion(
    executionArn: string,
    intervalMs: number = 5000,
    maxAttempts: number = 60
): Promise<PipelineStatus> {
    for (let i = 0; i < maxAttempts; i++) {
        const status = await getPipelineStatus(executionArn);
        if (status.status !== "RUNNING") {
            return status;
        }
        await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
    return { status: "TIMED_OUT" };
}
