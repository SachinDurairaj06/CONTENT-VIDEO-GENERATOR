"use client";

import { useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
  Sparkles,
  Video,
  Settings2,
  Download,
  AlertCircle,
  Globe,
  Ratio,
  Palette,
} from "lucide-react";
import { startPipeline, waitForCompletion } from "@/lib/api";

type PipelineStage = "idle" | "scripting" | "audio" | "visual" | "composing" | "complete" | "error";

export default function Home() {
  const [prompt, setPrompt] = useState("");
  const [language, setLanguage] = useState("en-IN");
  const [aspectRatio, setAspectRatio] = useState("16:9");
  const [style, setStyle] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [stage, setStage] = useState<PipelineStage>("idle");
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleGenerate = useCallback(async () => {
    if (!prompt) return;

    setIsGenerating(true);
    setStage("scripting");
    setVideoUrl(null);
    setErrorMsg(null);

    try {
      // 1. Trigger the pipeline
      const executionArn = await startPipeline({
        prompt,
        language_code: language,
        aspect_ratio: aspectRatio,
        style,
      });

      // 2. Simulate stage progression while polling
      // (In production the status endpoint would return granular step info)
      setStage("audio");
      const result = await waitForCompletion(executionArn, 5000, 60);

      if (result.status === "SUCCEEDED" && result.output?.download_url) {
        setStage("complete");
        setVideoUrl(result.output.download_url);
      } else {
        setStage("error");
        setErrorMsg(result.output?.error || "Pipeline failed or timed out.");
      }
    } catch (err: unknown) {
      setStage("error");
      setErrorMsg(err instanceof Error ? err.message : "Unknown error occurred.");
    } finally {
      setIsGenerating(false);
    }
  }, [prompt, language, aspectRatio, style]);

  return (
    <main className="min-h-screen bg-neutral-950 text-neutral-50 px-4 py-12 md:px-12 font-sans selection:bg-purple-500/30">
      {/* Header */}
      <header className="max-w-5xl mx-auto flex items-center justify-between mb-16">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-purple-600 to-orange-500 flex items-center justify-center">
            <Video className="w-5 h-5 text-white" />
          </div>
          <h1 className="text-xl font-bold tracking-tight">Unified Flow</h1>
        </div>
        <button className="p-2 rounded-full hover:bg-neutral-800 transition-colors">
          <Settings2 className="w-5 h-5 text-neutral-400" />
        </button>
      </header>

      <div className="max-w-5xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-12">
        {/* Left Column: Input */}
        <div className="flex flex-col gap-6">
          <div>
            <h2 className="text-4xl font-semibold tracking-tight mb-3">
              The Zero-Edit Workflow for{" "}
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-orange-400 to-purple-500">
                Bharat
              </span>
            </h2>
            <p className="text-neutral-400 text-lg">
              Describe your product or promotion in natural language. We&apos;ll
              generate the script, voiceover, and visuals — all in one click.
            </p>
          </div>

          {/* Prompt Input */}
          <div className="relative group">
            <div className="absolute -inset-0.5 bg-gradient-to-r from-orange-500 to-purple-600 rounded-2xl blur opacity-20 group-hover:opacity-40 transition duration-500" />
            <textarea
              id="prompt-input"
              className="relative w-full h-48 bg-neutral-900 rounded-2xl p-6 text-lg border border-neutral-800 focus:border-neutral-600 focus:ring-0 resize-none outline-none placeholder:text-neutral-600 transition-all"
              placeholder="e.g., Promote my organic honey from Himachal Pradesh for the winter season. Emphasize purity and health."
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              maxLength={512}
              disabled={isGenerating}
            />
          </div>

          {/* Options Row */}
          <div className="flex gap-4">
            <div className="flex-1 flex items-center gap-2 bg-neutral-900 border border-neutral-800 rounded-xl px-4 py-3">
              <Globe className="w-4 h-4 text-neutral-500" />
              <select
                id="language-select"
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                className="bg-transparent text-sm flex-1 outline-none text-neutral-300"
                disabled={isGenerating}
              >
                <option value="en-IN">English (India)</option>
                <option value="hi-IN">Hindi</option>
                <option value="ta-IN">Tamil</option>
                <option value="bn-IN">Bengali</option>
                <option value="te-IN">Telugu</option>
                <option value="mr-IN">Marathi</option>
              </select>
            </div>
            <div className="flex-1 flex items-center gap-2 bg-neutral-900 border border-neutral-800 rounded-xl px-4 py-3">
              <Ratio className="w-4 h-4 text-neutral-500" />
              <select
                id="aspect-ratio-select"
                value={aspectRatio}
                onChange={(e) => setAspectRatio(e.target.value)}
                className="bg-transparent text-sm flex-1 outline-none text-neutral-300"
                disabled={isGenerating}
              >
                <option value="16:9">16:9 (YouTube)</option>
                <option value="9:16">9:16 (Reels / Shorts)</option>
                <option value="1:1">1:1 (Square)</option>
              </select>
            </div>
          </div>

          {/* Style / Template Selector */}
          <div className="flex items-center gap-2 bg-neutral-900 border border-neutral-800 rounded-xl px-4 py-3">
            <Palette className="w-4 h-4 text-neutral-500" />
            <select
              id="style-select"
              value={style}
              onChange={(e) => setStyle(e.target.value)}
              className="bg-transparent text-sm flex-1 outline-none text-neutral-300"
              disabled={isGenerating}
            >
              <option value="">No Style (Auto)</option>
              <optgroup label="🏢 Industry Templates">
                <option value="healthcare">Healthcare</option>
                <option value="fintech">Fintech</option>
                <option value="education">EdTech</option>
                <option value="agriculture">Agriculture</option>
              </optgroup>
              <optgroup label="🪔 Festivals">
                <option value="diwali">Diwali</option>
                <option value="holi">Holi</option>
                <option value="dussehra">Dussehra</option>
                <option value="eid">Eid</option>
                <option value="pongal">Pongal</option>
                <option value="christmas">Christmas</option>
              </optgroup>
              <optgroup label="🎨 Regional Art">
                <option value="warli">Warli (Maharashtra)</option>
                <option value="madhubani">Madhubani (Bihar)</option>
                <option value="kalamkari">Kalamkari (Andhra)</option>
                <option value="pattachitra">Pattachitra (Odisha)</option>
              </optgroup>
              <optgroup label="🌤 Seasons">
                <option value="winter">Winter</option>
                <option value="monsoon">Monsoon</option>
                <option value="summer">Summer</option>
              </optgroup>
            </select>
          </div>

          {/* Generate Button */}
          <button
            id="generate-button"
            onClick={handleGenerate}
            disabled={!prompt || isGenerating}
            className={`flex items-center justify-center gap-2 w-full py-4 rounded-xl font-medium text-lg transition-all ${prompt && !isGenerating
              ? "bg-white text-black hover:bg-neutral-200"
              : "bg-neutral-800 text-neutral-500 cursor-not-allowed"
              }`}
          >
            {isGenerating ? (
              <span className="animate-pulse">Generating...</span>
            ) : (
              <>
                <Sparkles className="w-5 h-5" /> Generate Complete Video
              </>
            )}
          </button>

          {/* Info Banner */}
          <div className="flex items-start gap-3 p-4 rounded-xl bg-orange-500/10 border border-orange-500/20 text-orange-200/80">
            <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
            <p className="text-sm leading-relaxed">
              Videos are generated in all three ratios automatically. Generation
              involves AI pipelines and may take 2–3 minutes.
            </p>
          </div>
        </div>

        {/* Right Column: Output & Status */}
        <div className="relative bg-neutral-900 border border-neutral-800 rounded-3xl overflow-hidden flex flex-col justify-center min-h-[500px]">
          {/* Idle */}
          {stage === "idle" && !videoUrl && (
            <div className="absolute inset-0 flex flex-col items-center justify-center text-neutral-500 gap-4 p-8 text-center">
              <Video className="w-12 h-12 opacity-20" />
              <p>Your generated masterpiece will appear here.</p>
            </div>
          )}

          {/* Generating */}
          {isGenerating && (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-neutral-900/80 backdrop-blur-sm z-10">
              <div className="w-16 h-16 border-4 border-neutral-800 border-t-purple-500 rounded-full animate-spin mb-8" />
              <div className="space-y-4 w-64">
                <StatusItem
                  active={["scripting", "audio", "visual", "composing"].includes(stage)}
                  text="Drafting Script & Prompts"
                />
                <StatusItem
                  active={["audio", "visual", "composing"].includes(stage)}
                  text="Synthesizing Neuro-Voice"
                />
                <StatusItem
                  active={["visual", "composing"].includes(stage)}
                  text="Generating Visual Assets"
                />
                <StatusItem
                  active={stage === "composing"}
                  text="Composing Final Video"
                />
              </div>
            </div>
          )}

          {/* Error */}
          {stage === "error" && errorMsg && (
            <div className="absolute inset-0 flex flex-col items-center justify-center p-8 text-center">
              <AlertCircle className="w-12 h-12 text-red-400 mb-4" />
              <p className="text-red-300">{errorMsg}</p>
            </div>
          )}

          {/* Complete */}
          {videoUrl && stage === "complete" && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="absolute inset-0 flex flex-col"
            >
              <video
                src={videoUrl}
                className="w-full h-full object-cover"
                controls
                autoPlay
                loop
              />
              <div className="absolute bottom-0 left-0 right-0 p-6 bg-gradient-to-t from-black/80 to-transparent flex justify-end">
                <a
                  href={videoUrl}
                  download
                  className="flex items-center gap-2 bg-white/10 hover:bg-white/20 backdrop-blur-md px-4 py-2 rounded-lg font-medium transition-colors"
                >
                  <Download className="w-4 h-4" /> Download MP4
                </a>
              </div>
            </motion.div>
          )}
        </div>
      </div>
    </main>
  );
}

function StatusItem({ active, text }: { active: boolean; text: string }) {
  return (
    <div
      className={`flex items-center gap-3 transition-opacity duration-300 ${active ? "opacity-100" : "opacity-30"
        }`}
    >
      <div
        className={`w-2 h-2 rounded-full ${active
          ? "bg-purple-500 shadow-[0_0_8px_rgba(168,85,247,0.8)]"
          : "bg-neutral-600"
          }`}
      />
      <span className="text-sm font-medium">{text}</span>
    </div>
  );
}
